from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from backend.agents.graph import graph
from backend.config import get_settings
from backend.database import mongo
from backend.ml.inference import model_status, predict_live
from backend.services.progress import publish_progress
from backend.ml.risk_engine import operational_risk
from backend.utils.geo import jsonable, risk_category, utcnow
from backend.services import hydro_service, weather_service
from backend.services.decision_engine import evaluate_policy, pipeline_health
from backend.services.dispatch import apply_threshold_dispatch
from backend.ml.change_monitor import observe_cards
from backend.agents.dialogue import converse
from backend.services.route_engine import candidate_routes
from backend.services.seed import LANDMARKS, ROADS, RESCUE_TEAMS, SHELTERS, ZONES
from backend.services.sos_cluster import cluster_emergencies
from backend.services.shelter_engine import recommend_shelters
from backend.optimization.solvers import run_method
from backend.websocket.hub import hub

_snapshots: dict[str, dict[str, Any]] = {"live": {}, "simulation": {}}
_last_latencies: dict[str, float] = {}


def last_snapshot(mode: str = "live") -> dict[str, Any]:
    return _snapshots.get(mode) or {}


def last_latencies() -> dict[str, float]:
    return _last_latencies


def _freshness(ts: datetime | None) -> float | None:
    if not ts:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - ts).total_seconds(), 2)


async def _ensure_incident(pred: dict[str, Any], policy: dict[str, Any], weather: dict[str, Any], river: dict[str, Any], dam: dict[str, Any], mode: str) -> dict[str, Any]:
    p = pred.get("flood_probability")
    existing = await mongo.find_latest("incidents", {"mode": mode, "status": {"$ne": "closed"}})
    zone = ZONES[0]
    incident = {
        "incident_id": (existing or {}).get("incident_id") or f"INC-{mode[:3].upper()}-{int(time.time())}",
        "mode": mode,
        "zone_id": zone["zone_id"],
        "zone_name": zone["name"],
        "lat": zone["lat"],
        "lon": zone["lon"],
        "type": "Flood",
        "status": "active" if (p or 0) >= get_settings().flood_monitor_threshold else "monitoring",
        "flood_probability": p,
        "risk_category": pred.get("risk_category"),
        "affected_population": zone["population"],
        "rainfall_mm": weather.get("rainfall_mm"),
        "river_level_m": river.get("value_m"),
        "dam_level_m": dam.get("value_m"),
        "policy_action": policy.get("action"),
        "timestamp": utcnow(),
    }
    await mongo.upsert("incidents", {"incident_id": incident["incident_id"]}, incident)
    return incident


async def run_pipeline(mode: str = "live", observations: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shared live/simulation downstream pipeline. Only the data provider changes."""
    t_end0 = time.perf_counter()
    graph.shared["mode"] = mode
    graph.shared["stage"] = "INGEST"
    await publish_progress(mode, "ingest", "Ingesting rainfall, river and dam data", model=None)

    t0 = time.perf_counter()
    if observations:
        weather = observations.get("weather") or {}
        forecast = observations.get("forecast") or {"available": True, "source": "simulation", "items": []}
        river = observations.get("river") or {}
        dam = observations.get("dam") or {}
        rain_24 = float(weather.get("rainfall_mm") or 0)
        daily = observations.get("forecast_daily_mm") or []
    else:
        rain_24, daily, bundle = await weather_service.rainfall_24h_and_forecast()
        weather = bundle["current"]
        forecast = bundle["forecast"]
        river = await hydro_service.fetch_river()
        dam = await hydro_service.fetch_dam()
        if rain_24 is None:
            rain_24 = 0.0
    ingest_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    await graph.emit("weather", "WEATHER_UPDATE", "Rainfall updated", "normalize weather", {"rainfall_mm": rain_24})
    await hub.broadcast("weather_update", jsonable(weather))
    await hub.broadcast("rainfall_update", {"rainfall_mm": rain_24, "mode": mode})
    await graph.emit("dam", "DAM_UPDATE", "Water level updated", "normalize dam/river", {"river": river.get("value_m"), "dam": dam.get("value_m")})
    await hub.broadcast("dam_update", jsonable(dam))
    await hub.broadcast("river_update", jsonable(river))
    agent_ms = (time.perf_counter() - t1) * 1000

    graph.shared["stage"] = "ML"
    t2 = time.perf_counter()
    status = model_status()
    model_name = status.get("model_id") or "random_forest_flood_v1"
    pretty = "Random Forest" if "random_forest" in str(model_name) else str(status.get("best_model") or "flood model").replace("_", " ").title()
    await publish_progress(
        mode,
        "ml",
        f"{pretty} is running — predicting flood probability",
        model=model_name,
        model_name=pretty,
        model_version=status.get("model_version"),
    )
    pred = predict_live(rainfall_24h_mm=rain_24, forecast_daily_mm=daily)
    blended = operational_risk(
        pred.get("flood_probability"),
        rain_24,
        river.get("percent_of_danger"),
        dam.get("percent_of_danger"),
    )
    pred["ml_probability"] = blended["ml_probability"]
    pred["flood_probability"] = blended["flood_probability"]
    pred["risk_category"] = risk_category(blended["flood_probability"])
    pred["probability_source"] = blended["probability_source"]
    pred["rainfall_component"] = blended["rainfall_component"]
    pred["stage_component"] = blended["stage_component"]
    pred["prediction_kind"] = "HYBRID_OPERATIONAL"
    pred["raw_ml_kind"] = "RAW_ML"
    pred["hybrid_formula"] = blended.get("formula")
    if observations and observations.get("flood_probability_override") is not None:
        pred["flood_probability"] = max(0.0, min(1.0, float(observations["flood_probability_override"])))
        pred["risk_category"] = risk_category(pred["flood_probability"])
        pred["probability_source"] = "operator card override"
    pred["data_freshness_sec"] = _freshness(weather.get("timestamp") if isinstance(weather.get("timestamp"), datetime) else None)
    from backend.ml.inference import dual_model_view

    dual = dual_model_view(rain_24, daily)
    pred["dual"] = dual
    feats = (observations or {}).get("features") or {}
    human_override = bool((observations or {}).get("human_dispatch_override"))
    if mode == "simulation" and feats.get("model_disagreement", True) and dual.get("disagree") and not human_override:
        pred["dispatch_hold"] = True
    ml_ms = (time.perf_counter() - t2) * 1000
    await mongo.insert("flood_predictions", {**pred, "mode": mode})
    await graph.emit(
        "flood_risk",
        "FLOOD_RISK_UPDATE",
        "Probability recalculated",
        "publish flood risk",
        {"flood_probability": pred.get("flood_probability"), "risk_category": pred.get("risk_category")},
    )
    await hub.broadcast("risk_update", jsonable(pred))
    await publish_progress(
        mode,
        "risk",
        f"{pretty} predicted {(pred.get('flood_probability') or 0) * 100:.1f}% — {pred.get('risk_category') or 'n/a'}",
        model=model_name,
        model_name=pretty,
        flood_probability=pred.get("flood_probability"),
        risk_category=pred.get("risk_category"),
    )

    data_ok, model_ok, system_ok = pipeline_health(weather, river if river.get("available") else dam, pred)
    if pred.get("dispatch_hold"):
        model_ok = False
    policy = evaluate_policy(pred.get("flood_probability"), data_ok, model_ok, system_ok, human_override=human_override)
    if pred.get("dispatch_hold") and not human_override:
        policy["action"] = "HUMAN_REVIEW"
        policy["reason"] = dual.get("message") or "Random Forest and XGBoost disagree — hold auto-dispatch"
        policy["model_disagreement"] = True
    await graph.emit("flood_risk", "DECISION_REQUIRED", policy["action"], "apply decision policy", policy)
    await publish_progress(mode, "policy", f"Decision policy: {policy['action']}", action=policy["action"], model=model_name, model_name=pretty)
    await mongo.insert("risk_events", {"policy": policy, "prediction": pred, "mode": mode})

    roads = await mongo.find_many("roads", {}, limit=50) or ROADS
    p = pred.get("flood_probability") or 0
    for r in roads:
        if float(r.get("flood_exposure") or 0) >= 0.75 and p >= 0.55:
            r["blocked"] = True
            r["accessible"] = False
            await mongo.upsert("roads", {"road_id": r["road_id"]}, r)
    await graph.emit("traffic", "ROUTE_RISK", "Road risk updated", "evaluate traffic + blockage", {"blocked": [r["road_id"] for r in roads if r.get("blocked")]})

    zone = ZONES[0]
    traffic = 0.45 + 0.35 * p
    t3 = time.perf_counter()
    shelters = []
    routes = []
    optimization = None
    if policy["action"] in {"HUMAN_REVIEW", "AUTOMATED_RESPONSE", "HUMAN_OVERRIDE"}:
        graph.shared["stage"] = "SHELTER"
        shelters = await recommend_shelters(zone["lat"], zone["lon"], zone["population"], traffic, p)
        await graph.emit("shelter", "SHELTER_SEARCH", "Shelter capacity evaluated", "rank candidate shelters", {"count": len(shelters)})
        await hub.broadcast("shelter_update", {"shelters": jsonable(shelters)})
        graph.shared["stage"] = "ROUTE"
        if shelters:
            routes = await candidate_routes(zone["lat"], zone["lon"], shelters[0]["lat"], shelters[0]["lon"])
            await graph.emit("evacuation", "ROUTE_OPTIMIZATION", "Route planning requested", "generate candidate routes", {"n_routes": len(routes)})
            await hub.broadcast("route_update", {"routes": jsonable(routes)})
        graph.shared["stage"] = "OPTIMIZATION"
        usable = shelters[:5] or (await mongo.find_many("shelters", {}, limit=8)) or SHELTERS
        optimization = run_method("qaoa", ZONES[:4], usable[:6], traffic)
        await mongo.insert("optimization_runs", {**optimization, "mode": mode})
        await hub.broadcast("optimization_update", jsonable(optimization))
        await graph.emit("evacuation", "EVACUATION_PLAN", "Evacuation plan drafted", "bind shelter + route", {"method": optimization.get("method")})
        if policy["action"] == "AUTOMATED_RESPONSE":
            await graph.emit("rescue", "RESCUE_RESPONSE", "Rescue assignment prepared", "stage nearest available team", {})
    else:
        graph.shared["stage"] = "MONITOR"
        await graph.emit("evacuation", "DECISION_REQUIRED", "Waiting for decision policy", "monitor only", {"action": "MONITOR"})

    opt_ms = (time.perf_counter() - t3) * 1000
    incident = await _ensure_incident(pred, policy, weather, river, dam, mode)
    await publish_progress(mode, "agents", "Agents are running — weather, flood risk, shelter, rescue, ambulance", model=model_name, model_name=pretty)
    if pred.get("dispatch_hold") and not human_override:
        dispatch = {"called": False, "band": "admin", "places": [], "teams": [], "mode": mode, "held": True, "reason": dual.get("message")}
        await publish_progress(mode, "dispatch", "Auto-dispatch HELD — RF and XGBoost disagree", model=model_name, model_name=pretty, called=False)
    else:
        dispatch = await apply_threshold_dispatch(pred.get("flood_probability"), mode)
        if dispatch.get("called"):
            await publish_progress(mode, "dispatch", "Rescue and ambulance auto-called (P ≥ 60%) — moving to flood places", model=model_name, model_name=pretty, called=True)
    spike = observe_cards(mode, rain_24, river.get("value_m"), dam.get("value_m"), pred.get("flood_probability"))
    if spike.get("sudden"):
        await graph.emit(
            "monitor",
            "CARD_SPIKE",
            f"Sudden card change in {spike.get('seconds_since_last')}s",
            "alert flood-risk and rescue",
            spike,
        )
    await publish_progress(mode, "talk", "Agents talking on the operations net", model=model_name, model_name=pretty, band=(dispatch or {}).get("band"))
    skip_talk = bool((observations or {}).get("skip_talk"))
    if skip_talk:
        from backend.agents.dialogue import last_conversation

        conversation = last_conversation(mode) or {"available": False, "turns": [], "history": [], "message": "Agent radio is OFF"}
    else:
        conversation = await converse(
            mode,
            pred.get("flood_probability"),
            weather,
            river,
            incident,
            dispatch,
            force=bool((observations or {}).get("force_talk") or spike.get("sudden") or pred.get("dispatch_hold")),
            extra={"spike": spike, "dual": dual},
        )

    t4 = time.perf_counter()
    await hub.broadcast("system_metrics", {"ingest_ms": ingest_ms})
    ws_ms = (time.perf_counter() - t4) * 1000
    e2e = (time.perf_counter() - t_end0) * 1000
    latencies = {
        "ingestion": round(ingest_ms, 3),
        "ml": round(ml_ms, 3),
        "agent": round(agent_ms, 3),
        "optimization": round(opt_ms, 3),
        "websocket": round(ws_ms, 3),
        "end_to_end": round(e2e, 3),
        "timestamp": utcnow(),
        "mode": mode,
    }
    await mongo.insert("system_metrics", latencies)
    global _last_latencies, _last_snapshot
    _last_latencies = latencies

    stages = {
        "LIVE_DATA": "ok" if weather.get("available") else "unavailable",
        "ML_PREDICTION": "ok" if pred.get("available") else "unavailable",
        "AGENTS": "ok",
        "RISK_ENGINE": pred.get("risk_category") or "unavailable",
        "DECISION_POLICY": policy["action"],
        "OPTIMIZATION": optimization["method"] if optimization else "idle",
        "SHELTER": shelters[0]["shelter_id"] if shelters else "idle",
        "ROUTE": routes[0]["label"] if routes else "idle",
        "RESPONSE": policy["action"],
    }
    em_query: dict = {"status": "open"} if mode == "simulation" else {}
    if mode == "simulation":
        em_query["mode"] = "simulation"
    emergencies = await mongo.find_many("emergency_requests", em_query, limit=200)
    teams = await mongo.find_many("rescue_teams", {}, limit=20, sort_field="team_id", direction=1) or RESCUE_TEAMS
    clusters = cluster_emergencies(emergencies, teams)
    snapshot = {
        "mode": mode,
        "weather": weather,
        "forecast": forecast,
        "river": river,
        "dam": dam,
        "prediction": pred,
        "policy": policy,
        "incident": incident,
        "shelters": shelters,
        "routes": routes,
        "optimization": optimization,
        "agents": graph.statuses(),
        "stages": stages,
        "latencies": latencies,
        "landmarks": LANDMARKS,
        "roads": roads,
        "zones": ZONES,
        "emergencies": emergencies,
        "teams": teams,
        "clusters": clusters.get("clusters") or [],
        "dispatch": dispatch,
        "conversation": conversation,
        "card_monitor": spike,
        "timestamp": utcnow(),
        "websocket_clients": hub.connected_count,
        "mongodb": mongo.mongo_status(),
    }
    _snapshots[mode] = jsonable(snapshot)
    await mongo.upsert("pipeline_state", {"mode": mode}, {"snapshot_keys": list(snapshot.keys()), "mode": mode})
    return _snapshots[mode]
