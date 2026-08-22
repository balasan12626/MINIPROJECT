"""Algorithm Arena — flood-aware paths, policy engine, physics+ML twin, autonomy gates."""

from __future__ import annotations

import math
from typing import Any

import networkx as nx

from backend.ml.inference import dual_model_view, predict_live
from backend.services.route_engine import _nearest_node, build_graph, path_payload
from backend.services.seed import GRAPH_NODES, ROADS, SHELTERS
from backend.utils.geo import haversine_km, jsonable


# —— Policy rules (explainable decision table) ————————————————————————————————

POLICY_RULES = [
    {
        "id": "R1_MODEL_DISAGREE",
        "when": "RF–XGBoost gap ≥ 15%",
        "then": "HOLD auto-dispatch",
        "severity": "critical",
    },
    {
        "id": "R2_PHYSICS_ML_DIVERGE",
        "when": "Physics twin vs ML gap ≥ 20%",
        "then": "HOLD + transfer warning",
        "severity": "critical",
    },
    {
        "id": "R3_CHILD_OR_CHEST",
        "when": "age < 12 OR water = chest-deep",
        "then": "PRIORITY rescue",
        "severity": "high",
    },
    {
        "id": "R4_SHELTER_FULL",
        "when": "shelter free seats < people",
        "then": "REROUTE to next shelter",
        "severity": "high",
    },
    {
        "id": "R5_HIGH_CONFIDENCE",
        "when": "P ≥ 0.60 and models agree and physics aligned",
        "then": "FULL_AUTO allowed",
        "severity": "info",
    },
    {
        "id": "R6_MEDIUM_BAND",
        "when": "0.35 ≤ P < 0.60",
        "then": "PROPOSE only — human confirm",
        "severity": "medium",
    },
]


def physics_twin(
    rainfall_mm: float,
    river_level: float = 204.2,
    dam_level: float = 199.0,
) -> dict[str, Any]:
    """Lite hydrology: rainfall + barrage/river → inundation radius + physics flood P."""
    rain = max(0.0, float(rainfall_mm or 0))
    river = float(river_level or 204.2)
    dam = float(dam_level or 199.0)
    # Yamuna bank ~204 m; excess water + rain expands inundation
    river_excess = max(0.0, river - 204.0)
    dam_stress = max(0.0, dam - 198.5)
    inundation_km = round(river_excess * 0.42 + rain * 0.012 + dam_stress * 0.15, 3)
    # Logistic map into [0,1]
    logit = -2.2 + 0.035 * rain + 1.1 * river_excess + 0.55 * dam_stress
    physics_p = 1.0 / (1.0 + math.exp(-logit))
    physics_p = round(min(0.99, max(0.01, physics_p)), 4)
    return {
        "available": True,
        "method": "yamuna_water_balance_v1",
        "rainfall_mm": rain,
        "river_level_m": river,
        "dam_level_m": dam,
        "river_excess_m": round(river_excess, 3),
        "inundation_radius_km": inundation_km,
        "flood_probability": physics_p,
        "message": (
            f"Physics twin: rain {rain:.1f} mm + river excess {river_excess:.2f} m "
            f"→ ~{inundation_km:.2f} km inundation, P={physics_p:.1%}"
        ),
    }


def _depth_penalty(note: str | None) -> float:
    n = (note or "").lower()
    if "chest" in n:
        return 0.45
    if "waist" in n:
        return 0.28
    if "knee" in n:
        return 0.15
    if "ankle" in n:
        return 0.05
    return 0.1


def _build_graphs(roads: list[dict[str, Any]], flood_boost: float = 1.0) -> tuple[nx.Graph, nx.Graph]:
    """Distance-only graph vs flood-aware weighted graph."""
    g_flood = build_graph(roads)
    if flood_boost != 1.0:
        for u, v, data in list(g_flood.edges(data=True)):
            dist = float(data.get("distance_km") or 0.1)
            w = float(data.get("weight") or dist)
            g_flood[u][v]["weight"] = dist + max(0.0, w - dist) * flood_boost

    g_dist = nx.Graph()
    for node, (lat, lon) in GRAPH_NODES.items():
        g_dist.add_node(node, lat=lat, lon=lon)
    for u, v, data in g_flood.edges(data=True):
        dist = float(data.get("distance_km") or 0.1)
        g_dist.add_edge(u, v, weight=dist, road_id=data.get("road_id"), distance_km=dist)
    return g_dist, g_flood


def _astar_path(g: nx.Graph, src: str, dst: str) -> list[str] | None:
    if src not in g or dst not in g or not nx.has_path(g, src, dst):
        return None

    def heuristic(a: str, b: str) -> float:
        la, loa = GRAPH_NODES[a]
        lb, lob = GRAPH_NODES[b]
        return haversine_km(la, loa, lb, lob)

    try:
        return nx.astar_path(g, src, dst, heuristic=heuristic, weight="weight")
    except Exception:  # noqa: BLE001
        try:
            return nx.shortest_path(g, src, dst, weight="weight")
        except Exception:  # noqa: BLE001
            return None


def _dijkstra_path(g: nx.Graph, src: str, dst: str) -> list[str] | None:
    if src not in g or dst not in g or not nx.has_path(g, src, dst):
        return None
    try:
        return nx.shortest_path(g, src, dst, weight="weight")
    except Exception:  # noqa: BLE001
        return None


def _path_entry(g: nx.Graph, nodes: list[str] | None, method: str, label: str) -> dict[str, Any] | None:
    if not nodes or len(nodes) < 2:
        return None
    payload = path_payload(g, nodes)
    payload["method"] = method
    payload["label"] = label
    return payload


def _pick_shelter(citizen: dict, shelters: list[dict]) -> dict | None:
    if not shelters:
        return None
    lat = float(citizen.get("lat") or 28.61)
    lon = float(citizen.get("lon") or 77.21)
    people = int(citizen.get("people") or 1)
    usable = [
        s
        for s in shelters
        if max(0, int(s.get("capacity") or 0) - int(s.get("occupancy") or 0)) >= people
    ] or list(shelters)
    return min(
        usable,
        key=lambda s: haversine_km(lat, lon, float(s.get("lat") or lat), float(s.get("lon") or lon)),
    )


def _lives_score(people: int, eta_min: float, depth_note: str | None, shelter: dict | None) -> float:
    if eta_min <= 0:
        eta_min = 0.5
    free = 0
    if shelter:
        free = max(0, int(shelter.get("capacity") or 0) - int(shelter.get("occupancy") or 0))
    seat_pen = 0.35 if free < people else 0.0
    return round(people / eta_min * (1.0 - _depth_penalty(depth_note) - seat_pen), 4)


def evaluate_policies(
    *,
    dual: dict,
    physics: dict,
    ml_p: float | None,
    citizens: list[dict],
    shelters: list[dict],
) -> dict[str, Any]:
    rf = dual.get("random_forest")
    xgb = dual.get("xgboost")
    gap = abs(float(rf) - float(xgb)) if rf is not None and xgb is not None else 0.0
    phys_p = float(physics.get("flood_probability") or 0)
    ml = float(ml_p) if ml_p is not None else (float(rf) if rf is not None else phys_p)
    phys_gap = abs(phys_p - ml)

    fired: list[dict[str, Any]] = []
    hold = False
    priority_names: list[str] = []
    reroutes: list[str] = []

    if gap >= 0.15:
        hold = True
        fired.append({**POLICY_RULES[0], "fired": True, "detail": f"gap={gap:.1%}"})
    else:
        fired.append({**POLICY_RULES[0], "fired": False, "detail": f"gap={gap:.1%}"})

    if phys_gap >= 0.20:
        hold = True
        fired.append({**POLICY_RULES[1], "fired": True, "detail": f"|physics−ML|={phys_gap:.1%}"})
    else:
        fired.append({**POLICY_RULES[1], "fired": False, "detail": f"|physics−ML|={phys_gap:.1%}"})

    child_or_chest = False
    for c in citizens:
        age = c.get("age")
        note = str(c.get("water_level_note") or "")
        if (age is not None and int(age) < 12) or "chest" in note.lower():
            child_or_chest = True
            priority_names.append(c.get("citizen_name") or "?")
    fired.append(
        {
            **POLICY_RULES[2],
            "fired": child_or_chest,
            "detail": ", ".join(priority_names[:5]) or "none",
        }
    )

    shelter_issue = False
    for c in citizens:
        people = int(c.get("people") or 1)
        sh = _pick_shelter(c, shelters)
        if not sh:
            continue
        free = max(0, int(sh.get("capacity") or 0) - int(sh.get("occupancy") or 0))
        if free < people:
            shelter_issue = True
            reroutes.append(c.get("citizen_name") or "?")
    fired.append(
        {
            **POLICY_RULES[3],
            "fired": shelter_issue,
            "detail": ", ".join(reroutes[:5]) or "ok",
        }
    )

    agree = gap < 0.15 and phys_gap < 0.20
    high = ml >= 0.60 and agree and not hold
    fired.append(
        {
            **POLICY_RULES[4],
            "fired": high,
            "detail": f"ML P={ml:.1%} agree={agree}",
        }
    )
    medium = 0.35 <= ml < 0.60
    fired.append(
        {
            **POLICY_RULES[5],
            "fired": medium and not high,
            "detail": f"ML P={ml:.1%}",
        }
    )

    if hold or ml < 0.35:
        autonomy = "MANUAL_ONLY"
        autonomy_note = "Low confidence or policy HOLD — operator must approve."
    elif medium and not high:
        autonomy = "PROPOSE_CONFIRM"
        autonomy_note = "Medium band — agents propose, human confirms."
    else:
        autonomy = "FULL_AUTO"
        autonomy_note = "High confidence — automated response allowed."

    return {
        "rules": fired,
        "hold_auto_dispatch": hold,
        "priority_citizens": priority_names,
        "reroute_citizens": reroutes,
        "autonomy_level": autonomy,
        "autonomy_note": autonomy_note,
        "model_gap": round(gap, 4),
        "physics_ml_gap": round(phys_gap, 4),
        "ml_probability": round(ml, 4),
        "physics_probability": phys_p,
    }


def run_path_algorithms(
    citizen: dict,
    shelter: dict,
    roads: list[dict],
    flood_boost: float = 1.0,
) -> dict[str, Any]:
    lat = float(citizen.get("lat") or 28.61)
    lon = float(citizen.get("lon") or 77.21)
    slat = float(shelter.get("lat") or lat)
    slon = float(shelter.get("lon") or lon)
    src = _nearest_node(lat, lon)
    dst = _nearest_node(slat, slon)
    g_dist, g_flood = _build_graphs(roads, flood_boost=flood_boost)

    before = _path_entry(g_dist, _dijkstra_path(g_dist, src, dst), "dijkstra-distance", "Before flood (shortest km)")
    after_d = _path_entry(g_flood, _dijkstra_path(g_flood, src, dst), "dijkstra-flood", "After flood (Dijkstra)")
    after_a = _path_entry(g_flood, _astar_path(g_flood, src, dst), "astar-flood", "After flood (A*)")

    # Greedy: ignore graph, straight-line proxy
    greedy_km = haversine_km(lat, lon, slat, slon)
    greedy = {
        "method": "greedy-straight",
        "label": "Greedy straight-line",
        "nodes": [src, dst],
        "coordinates": [
            {"node": src, "lat": GRAPH_NODES[src][0], "lon": GRAPH_NODES[src][1]},
            {"node": dst, "lat": GRAPH_NODES[dst][0], "lon": GRAPH_NODES[dst][1]},
        ],
        "distance_km": round(greedy_km, 3),
        "cost": round(greedy_km, 4),
        "travel_time_min": round(greedy_km / 0.35 * 6, 2),
        "roads": [],
    }

    people = int(citizen.get("people") or 1)
    note = citizen.get("water_level_note")
    scored = []
    for route in (before, after_d, after_a, greedy):
        if not route:
            continue
        eta = float(route.get("travel_time_min") or 1)
        score = _lives_score(people, eta, note, shelter)
        entry = {**route, "lives_per_minute": score, "people": people}
        scored.append(entry)

    # Best by lives/min among flood-aware routes
    flood_routes = [r for r in scored if r.get("method") in ("dijkstra-flood", "astar-flood")]
    winner = max(flood_routes, key=lambda r: r["lives_per_minute"]) if flood_routes else (scored[0] if scored else None)

    return {
        "citizen_name": citizen.get("citizen_name"),
        "shelter_id": shelter.get("shelter_id") or shelter.get("name"),
        "shelter_name": shelter.get("name"),
        "source_node": src,
        "dest_node": dst,
        "before_path": before,
        "after_dijkstra": after_d,
        "after_astar": after_a,
        "greedy": greedy,
        "contenders": scored,
        "winner": winner,
    }


def run_algorithm_arena(sim_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full arena: twin models + policy + path algorithms + scoreboard."""
    st = sim_state or {}
    pipe = st.get("pipeline") or {}
    params = st.get("params") or {}
    hist = st.get("history") or []
    last = hist[-1] if hist else {}

    rain = float(
        last.get("rainfall_intensity")
        or params.get("rainfall_intensity")
        or pipe.get("weather", {}).get("rainfall_24h_mm")
        or 55
    )
    river = float(last.get("river_level") or params.get("river_level") or pipe.get("river", {}).get("level_m") or 204.2)
    dam = float(last.get("dam_level") or params.get("dam_level") or pipe.get("dam", {}).get("level_m") or 199.0)

    ml = predict_live(rain)
    dual = dual_model_view(rain)
    physics = physics_twin(rain, river_level=river, dam_level=dam)

    ml_p = ml.get("flood_probability")
    if ml_p is None and dual.get("random_forest") is not None:
        ml_p = dual["random_forest"]

    twin_diverge = abs(float(physics["flood_probability"]) - float(ml_p or 0)) >= 0.20

    citizens = list(st.get("citizens") or [])
    if not citizens:
        citizens = [
            {
                "citizen_name": "Demo Citizen",
                "lat": 28.651,
                "lon": 77.262,
                "people": 3,
                "age": 29,
                "water_level_note": "knee-deep",
            }
        ]
    shelters = list(pipe.get("shelters") or SHELTERS)
    roads = list(pipe.get("roads") or ROADS)

    # Boost flood edge costs when physics says large inundation
    boost = 1.0 + min(2.0, float(physics["inundation_radius_km"]) * 0.35)

    policy = evaluate_policies(
        dual=dual,
        physics=physics,
        ml_p=ml_p,
        citizens=citizens,
        shelters=shelters,
    )

    # Run path contest for top-priority / first citizens (cap 5 for speed)
    ordered = sorted(
        citizens,
        key=lambda c: (
            0 if (c.get("age") is not None and int(c.get("age")) < 12) else 1,
            0 if "chest" in str(c.get("water_level_note") or "").lower() else 1,
            -int(c.get("people") or 1),
        ),
    )[:5]

    path_runs = []
    for c in ordered:
        sh = _pick_shelter(c, shelters)
        if not sh:
            continue
        path_runs.append(run_path_algorithms(c, sh, roads, flood_boost=boost))

    # Aggregate scoreboard
    methods = {
        "dijkstra-distance": {"label": "Dijkstra (km only)", "etas": [], "scores": [], "blocked_hits": 0},
        "dijkstra-flood": {"label": "Dijkstra (flood-aware)", "etas": [], "scores": [], "blocked_hits": 0},
        "astar-flood": {"label": "A* (flood-aware)", "etas": [], "scores": [], "blocked_hits": 0},
        "greedy-straight": {"label": "Greedy straight-line", "etas": [], "scores": [], "blocked_hits": 0},
    }
    blocked_ids = {r["road_id"] for r in roads if r.get("blocked")}
    for run in path_runs:
        for route in run.get("contenders") or []:
            m = route.get("method")
            if m not in methods:
                continue
            methods[m]["etas"].append(float(route.get("travel_time_min") or 0))
            methods[m]["scores"].append(float(route.get("lives_per_minute") or 0))
            roads_used = set(route.get("roads") or [])
            methods[m]["blocked_hits"] += len(roads_used & blocked_ids)

    scoreboard = []
    for mid, row in methods.items():
        if not row["etas"]:
            continue
        avg_eta = sum(row["etas"]) / len(row["etas"])
        avg_score = sum(row["scores"]) / len(row["scores"])
        scoreboard.append(
            {
                "method": mid,
                "label": row["label"],
                "avg_eta_min": round(avg_eta, 2),
                "avg_lives_per_min": round(avg_score, 4),
                "blocked_roads_used": row["blocked_hits"],
                "assignments": len(row["etas"]),
            }
        )
    scoreboard.sort(key=lambda x: (-x["avg_lives_per_min"], x["avg_eta_min"]))

    # Map polylines: primary citizen before (blue) vs after A* (red)
    primary = path_runs[0] if path_runs else None
    map_paths = {
        "before": primary.get("before_path") if primary else None,
        "after": (primary.get("after_astar") or primary.get("after_dijkstra")) if primary else None,
    }

    agent_verdict = {
        "flood_risk_agent": f"ML P={float(ml_p or 0):.1%} ({ml.get('model_id') or 'rf'})",
        "physics_agent": physics["message"],
        "rescue_agent": (
            f"Winner route: {(primary or {}).get('winner', {}).get('label') or 'n/a'} "
            f"→ {(primary or {}).get('shelter_name') or 'shelter'}"
        ),
        "shelter_agent": f"{len(shelters)} shelters in play; reroutes={policy['reroute_citizens'] or 'none'}",
        "administrator_agent": (
            f"Verdict: {policy['autonomy_level']} — {policy['autonomy_note']}"
            + (" | HOLD dispatch" if policy["hold_auto_dispatch"] else "")
        ),
    }

    return jsonable(
        {
            "available": True,
            "title": "Algorithm Arena",
            "tick": st.get("tick"),
            "rainfall_mm": rain,
            "river_level_m": river,
            "dam_level_m": dam,
            "ml": {
                "flood_probability": ml_p,
                "model_id": ml.get("model_id"),
                "risk_category": ml.get("risk_category"),
                "dual": dual,
            },
            "physics": physics,
            "twin_diverge": twin_diverge,
            "policy": policy,
            "path_runs": path_runs,
            "scoreboard": scoreboard,
            "map_paths": map_paths,
            "agent_verdict": agent_verdict,
            "pitch": (
                "Flood-aware pathfinder + RF/XGB + physics twin + policy engine "
                "decide when agents may act."
            ),
        }
    )
