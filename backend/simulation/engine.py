from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any, Optional

from backend.database import mongo
from backend.services.pipeline import run_pipeline
from backend.utils.geo import jsonable, utcnow
from backend.websocket.hub import hub

SCENARIOS = {
    "heavy_rainfall": {
        "title": "Heavy Rainfall",
        "story": "Extreme rainfall is increasing runoff across the Yamuna floodplain. River levels are rising, road accessibility is decreasing, and shelter demand is increasing.",
        "defaults": {
            "rainfall_intensity": 72,
            "dam_level": 199.2,
            "river_level": 204.6,
            "road_blockage": 0.22,
            "population": 14000,
            "shelter_capacity_factor": 1.0,
            "traffic": 0.55,
            "sos_count": 10,
            "ticks": 24,
            "tick_seconds": 2,
        },
    },
    "dam_overflow": {
        "title": "Dam Overflow",
        "story": "Hathnikund / upstream barrage storage is approaching danger level. Releases raise Delhi river stage even if local rainfall is moderate.",
        "defaults": {
            "rainfall_intensity": 38,
            "dam_level": 206.5,
            "river_level": 205.2,
            "road_blockage": 0.18,
            "population": 15000,
            "shelter_capacity_factor": 0.95,
            "traffic": 0.5,
            "sos_count": 10,
            "ticks": 24,
            "tick_seconds": 2,
        },
    },
    "river_rise": {
        "title": "River Rise",
        "story": "Yamuna stage at ITO is climbing toward the danger mark. Low-lying pushta and east-bank colonies face expanding inundation.",
        "defaults": {
            "rainfall_intensity": 48,
            "dam_level": 201.0,
            "river_level": 205.6,
            "road_blockage": 0.2,
            "population": 13000,
            "shelter_capacity_factor": 1.0,
            "traffic": 0.52,
            "sos_count": 10,
            "ticks": 24,
            "tick_seconds": 2,
        },
    },
    "road_blockage": {
        "title": "Road Blockage",
        "story": "Key floodplain corridors (Yamuna Bank Road, Vikas Marg) lose accessibility as water covers carriageways and traffic diverts inland.",
        "defaults": {
            "rainfall_intensity": 50,
            "dam_level": 199.5,
            "river_level": 204.8,
            "road_blockage": 0.55,
            "population": 12000,
            "shelter_capacity_factor": 1.0,
            "traffic": 0.72,
            "sos_count": 8,
            "ticks": 24,
            "tick_seconds": 2,
        },
    },
    "shelter_congestion": {
        "title": "Shelter Congestion",
        "story": "East-bank shelters fill first. Remaining capacity inland must absorb displaced population under rising occupancy pressure.",
        "defaults": {
            "rainfall_intensity": 52,
            "dam_level": 200.0,
            "river_level": 204.9,
            "road_blockage": 0.25,
            "population": 18000,
            "shelter_capacity_factor": 0.55,
            "traffic": 0.6,
            "sos_count": 12,
            "ticks": 24,
            "tick_seconds": 2,
        },
    },
    "mass_evacuation": {
        "title": "Mass Evacuation",
        "story": "Multiple zones require concurrent assignment to shelters. Optimization must respect capacity, travel time, and flood exposure.",
        "defaults": {
            "rainfall_intensity": 65,
            "dam_level": 202.0,
            "river_level": 205.4,
            "road_blockage": 0.35,
            "population": 22000,
            "shelter_capacity_factor": 0.8,
            "traffic": 0.68,
            "sos_count": 14,
            "ticks": 28,
            "tick_seconds": 2,
        },
    },
    "multiple_sos": {
        "title": "Multiple SOS",
        "story": "Citizen emergency requests spike as water enters residential pockets. Rescue teams are staged against growing demand.",
        "defaults": {
            "rainfall_intensity": 55,
            "dam_level": 199.0,
            "river_level": 204.2,
            "road_blockage": 0.15,
            "population": 12000,
            "shelter_capacity_factor": 1.0,
            "traffic": 0.45,
            "sos_count": 10,
            "ticks": 24,
            "tick_seconds": 2,
        },
    },
}

DEFAULT_FEATURES = {
    "explainable_ai": True,
    "agent_talk": True,
    "vulnerable_first": True,
    "model_disagreement": True,
    "counterfactual": True,
    "contact_log": True,
    "run_replay": True,
    "citizen_status_board": True,
    "disagreement_debate": True,
    "voice_radio": False,
    "ask_agent": True,
    "after_action_summary": True,
    "sos_heatmap": True,
    "person_card": True,
    "team_paths": True,
    "before_after_radius": True,
    "theme_toggle": True,
    "shelter_board": True,
    "eta_board": True,
    "medical_triage": True,
    "bilingual_radio": True,
    "scenario_compare": True,
    "confidence_band": True,
    "false_alarm_drill": True,
    "road_blockage_impact": True,
    "operator_checklist": True,
    "jury_mode": True,
    "transfer_warning": True,
    "api_health": True,
    "latency_meter": True,
    "whatif_rain": True,
    "algorithm_arena": True,
}


class SimulationEngine:
    def __init__(self) -> None:
        self.run_id: Optional[str] = None
        self.status: str = "idle"
        self.params: dict[str, Any] = {}
        self.tick: int = 0
        self.sim_time_sec: float = 0.0
        self.task: Optional[asyncio.Task] = None
        self.events: list[dict[str, Any]] = []
        self.history: list[dict[str, Any]] = []
        self.before: dict[str, Any] | None = None
        self.after: dict[str, Any] | None = None
        self.started_at: Optional[datetime] = None
        self.last_obs: dict[str, Any] | None = None
        self.overrides: dict[str, Any] = {}
        self.citizens: list[dict[str, Any]] = []
        self.contact_log: list[dict[str, Any]] = []
        self.human_dispatch_override: bool = False
        self.checklist: list[dict[str, Any]] = []
        self.false_alarm: dict[str, Any] | None = None
        self._teams_cache: list[dict[str, Any]] = []

    def features(self) -> dict[str, bool]:
        merged = dict(DEFAULT_FEATURES)
        extra = self.params.get("features") or {}
        for k, v in extra.items():
            if k in merged:
                merged[k] = bool(v)
        return merged

    def _demo_payload(self, snap: dict[str, Any] | None = None) -> dict[str, Any]:
        from backend.services.demo_extras import (
            after_action_bullets,
            build_eta_board,
            build_status_board,
            confidence_band,
            disagreement_debate,
            team_paths,
        )
        from backend.services.seed import RESCUE_TEAMS, SHELTERS

        snap = snap or {}
        pred = snap.get("prediction") or {}
        dual = pred.get("dual") or {}
        teams = self._teams_cache or snap.get("teams") or list(RESCUE_TEAMS)
        shelters = snap.get("shelters") or snap.get("all_shelters") or list(SHELTERS)
        board = build_status_board(self.contact_log, int(self.tick or 0))
        for row in board:
            for c in self.citizens:
                if c.get("citizen_name") == row.get("citizen_name"):
                    c["live_status"] = row.get("status")
                    c["triage"] = row.get("triage")
        etas = build_eta_board(self.citizens, teams)
        paths = team_paths(self.citizens, teams)
        roads = snap.get("roads") or []
        blocked = [r for r in roads if r.get("blocked")]
        before_p = (self.before or {}).get("flood_probability")
        after_p = (self.after or {}).get("flood_probability") or pred.get("flood_probability")
        shelter_board = []
        for s in shelters[:8]:
            cap = int(s.get("capacity") or 0)
            occ = int(s.get("occupancy") or 0)
            left = max(0, cap - occ)
            shelter_board.append(
                {
                    "shelter_id": s.get("shelter_id"),
                    "name": s.get("name"),
                    "capacity": cap,
                    "occupancy": occ,
                    "seats_left": left,
                    "full": left <= 0,
                }
            )
        st_partial = {
            "history": self.history,
            "citizens": self.citizens,
            "contact_log": self.contact_log,
            "after": self.after,
            "pipeline": snap,
            "tick": self.tick,
            "status_board": board,
            "eta_board": etas,
            "shelter_board": shelter_board,
            "false_alarm": self.false_alarm,
            "scenario": self.params.get("scenario"),
            "status": self.status,
        }
        return {
            "status_board": board,
            "eta_board": etas,
            "team_paths": paths,
            "shelter_board": shelter_board,
            "disagreement_debate": disagreement_debate(dual) if dual else [],
            "confidence": confidence_band(dual, pred.get("flood_probability")),
            "after_action_summary": after_action_bullets(st_partial),
            "blocked_roads": [
                {"road_id": r.get("road_id"), "name": r.get("name"), "reason": "flood exposure / blockage"}
                for r in blocked
            ],
            "before_flood_p": before_p,
            "after_flood_p": after_p,
            "checklist": self.checklist,
            "false_alarm": self.false_alarm,
            "transfer_warning": "Model trained on INDOFLOODS (Indonesia catchments), applied to Delhi Yamuna floodplain — transfer risk.",
        }

    def state(self) -> dict[str, Any]:
        from backend.agents.dialogue import last_conversation
        from backend.services.progress import last_progress
        from backend.services.pipeline import last_snapshot
        from backend.services.person_ops import advance_all, sync_citizen_from_log

        # Every poll / tick: advance SOS people every 12s (queued → assigned → … → rescued)
        if self.contact_log:
            advance_all(self.contact_log)
            by_name = {c.get("citizen_name"): c for c in self.citizens}
            for row in self.contact_log:
                src = by_name.get(row.get("citizen_name"))
                if src:
                    sync_citizen_from_log(src, row)

        snap = last_snapshot("simulation")
        demo = self._demo_payload(snap)
        return jsonable(
            {
                "run_id": self.run_id,
                "status": self.status,
                "scenario": self.params.get("scenario"),
                "tick": self.tick,
                "sim_time_sec": round(self.sim_time_sec, 1),
                "params": self.params,
                "events": self.events[-40:],
                "history": self.history[-120:],
                "before": self.before,
                "after": self.after,
                "started_at": self.started_at,
                "story": SCENARIOS.get(self.params.get("scenario") or "", {}).get("story"),
                "conversation": last_conversation("simulation"),
                "progress": last_progress("simulation"),
                "overrides": self.overrides,
                "citizens": self.citizens,
                "contact_log": self.contact_log,
                "features": self.features(),
                "human_dispatch_override": self.human_dispatch_override,
                "pipeline": snap,
                **demo,
            }
        )

    async def _log(self, message: str, extra: dict[str, Any] | None = None) -> None:
        item = {
            "run_id": self.run_id,
            "sim_time_sec": round(self.sim_time_sec, 1),
            "message": message,
            "timestamp": utcnow(),
            "extra": extra or {},
        }
        self.events.append(item)
        await mongo.insert("simulation_events", item)
        await hub.broadcast("simulation_event", item)

    def _evolve(self) -> dict[str, Any]:
        p = self.params
        t = self.tick
        scenario = p.get("scenario")
        rain0 = float(p.get("rainfall_intensity") or 20)
        dam0 = float(p.get("dam_level") or 198)
        river0 = float(p.get("river_level") or 204)
        traffic0 = float(p.get("traffic") or 0.4)
        sos0 = int(p.get("sos_count") or 0)
        blockage0 = float(p.get("road_blockage") or 0.1)

        growth = 1 - math.exp(-t / 8.0)
        rain = rain0 * (0.35 + 1.4 * growth)
        if scenario == "heavy_rainfall":
            rain *= 1.35
        river = river0 + 0.12 * rain * growth
        dam = dam0 + 0.08 * rain * growth
        if scenario in {"dam_overflow", "river_rise"}:
            dam += 4.0 * growth
            river += 3.2 * growth
        traffic = min(0.95, traffic0 + 0.4 * growth)
        blockage = min(0.95, blockage0 + 0.5 * growth if scenario == "road_blockage" else blockage0 + 0.25 * growth)
        sos = int(sos0 + growth * (18 if scenario == "multiple_sos" else 8))
        occ_factor = 1.0 + (0.8 if scenario == "shelter_congestion" else 0.35) * growth
        daily = [rain * 0.9, rain * 0.7, rain * 0.5]
        weather = {
            "available": True,
            "source": "simulation",
            "temperature_c": 29.0 - 0.4 * growth,
            "rainfall_mm": rain,
            "rainfall_1h_mm": rain / 6.0,
            "humidity_pct": 70 + 20 * growth,
            "wind_mps": 3.5,
            "pressure_hpa": 1004 - 4 * growth,
            "description": "synthetic monsoon pulse",
            "lat": 28.6139,
            "lon": 77.2090,
            "timestamp": utcnow(),
            "mode": "simulation",
        }
        river_doc = {
            "available": True,
            "source": "simulation",
            "kind": "river",
            "value_m": round(river, 3),
            "danger_level_m": 205.8,
            "percent_of_danger": round(100 * river / 205.8, 2),
            "station": "Yamuna at ITO / Delhi",
            "lat": 28.6284,
            "lon": 77.2410,
            "timestamp": utcnow(),
        }
        dam_doc = {
            "available": True,
            "source": "simulation",
            "kind": "dam",
            "value_m": round(dam, 3),
            "danger_level_m": 205.8,
            "percent_of_danger": round(100 * dam / 205.8, 2),
            "station": "Hathnikund Barrage",
            "lat": 30.3139,
            "lon": 77.5886,
            "timestamp": utcnow(),
        }
        return {
            "weather": weather,
            "forecast": {"available": True, "source": "simulation", "items": []},
            "forecast_daily_mm": daily,
            "river": river_doc,
            "dam": dam_doc,
            "traffic": traffic,
            "blockage": blockage,
            "sos": sos,
            "occupancy_factor": occ_factor,
            "features": self.features(),
            "human_dispatch_override": self.human_dispatch_override,
            "skip_talk": not self.features().get("agent_talk", True),
        }

    async def _loop(self) -> None:
        assert self.run_id
        ticks = int(self.params.get("ticks") or 36)
        delay = float(self.params.get("tick_seconds") or 2.0)
        await self._log("Scenario started", {"scenario": self.params.get("scenario")})
        from backend.services.progress import publish_progress

        await publish_progress("simulation", "scenario", "Scenario running — digital twin started", scenario=self.params.get("scenario"))
        await self._ingest_citizens()
        try:
            while self.status == "running" and self.tick < ticks:
                obs = self._apply_overrides(self._evolve())
                self.last_obs = obs
                if self.tick == 1:
                    await self._log("Rainfall increasing", {"rainfall_mm": obs["weather"]["rainfall_mm"]})
                if self.tick == 4:
                    await self._log("Water level rising", {"river_m": obs["river"]["value_m"]})
                from backend.database import mongo as db
                from backend.services.seed import ROADS, SHELTERS
                roads = await db.find_many("roads", {}, limit=50) or [dict(r) for r in ROADS]
                for r in roads:
                    if float(r.get("flood_exposure") or 0) >= (0.85 - obs["blockage"]):
                        r["blocked"] = True
                        r["accessible"] = False
                    await db.upsert("roads", {"road_id": r["road_id"]}, r)
                shelters = await db.find_many("shelters", {}, limit=50) or [dict(s) for s in SHELTERS]
                for s in shelters:
                    occ = min(int(s.get("capacity") or 0), int((s.get("occupancy") or 0) * obs["occupancy_factor"] + 8))
                    s["occupancy"] = occ
                    if occ >= int(s.get("capacity") or 0):
                        s["status"] = "full"
                    await db.upsert("shelters", {"shelter_id": s["shelter_id"]}, s)
                snap = await run_pipeline(mode="simulation", observations=obs)
                p = (snap.get("prediction") or {}).get("flood_probability")
                action = (snap.get("policy") or {}).get("action")
                if p is not None:
                    await self._log(f"Flood probability {round(p * 100)}%", {"p": p, "action": action})
                if action == "HUMAN_REVIEW":
                    await self._log("Human review required", {"action": action})
                if action == "AUTOMATED_RESPONSE":
                    await self._log("Automated response active", {"action": action})
                dispatch = snap.get("dispatch") or {}
                if dispatch.get("called"):
                    await self._log("Rescue and ambulance auto-called (P≥60%)", {"places": [p.get("name") for p in dispatch.get("places") or []]})
                    self._tick_checklist("boats", True)
                    self._tick_checklist("medical", True)
                if action == "AUTOMATED_RESPONSE":
                    self._tick_checklist("alert", True)
                    self._tick_checklist("shelters", True)
                if self.features().get("false_alarm_drill") and p is not None:
                    peak_so_far = max(
                        [h.get("flood_probability") for h in self.history if h.get("flood_probability") is not None] + ([p] if p is not None else []),
                        default=0,
                    )
                    if peak_so_far >= 0.55 and p < 0.40 and not self.false_alarm:
                        self.false_alarm = {
                            "active": True,
                            "message": f"False-alarm drill: peak was {round(peak_so_far * 100, 1)}% then P fell to {round(p * 100, 1)}% (<40%). Cancel full rescue and stand down.",
                        }
                        await self._log(self.false_alarm["message"], {"p": p, "peak": peak_so_far})
                talk = snap.get("conversation") or {}
                if talk.get("turns"):
                    await self._log(f"Agents talking ({talk.get('band')} / {talk.get('source')})", {"speakers": talk.get("speakers")})
                if snap.get("optimization") and not self.after:
                    await self._log("Optimization requested", {"method": snap["optimization"].get("method")})
                    if snap.get("shelters"):
                        await self._log("Shelter selected", {"shelter": snap["shelters"][0].get("shelter_id")})
                    if snap.get("routes"):
                        await self._log("Route generated", {"route": snap["routes"][0].get("label")})
                rec = {
                    "tick": self.tick,
                    "sim_time_sec": self.sim_time_sec,
                    "rainfall_mm": obs["weather"]["rainfall_mm"],
                    "river_m": obs["river"]["value_m"],
                    "dam_m": obs["dam"]["value_m"],
                    "flood_probability": p,
                    "risk_category": (snap.get("prediction") or {}).get("risk_category"),
                    "action": action,
                }
                self.history.append(rec)
                if self.tick == 0:
                    self.before = {
                        "flood_probability": p,
                        "optimization": snap.get("optimization"),
                        "risk_category": rec["risk_category"],
                    }
                self.after = {
                    "flood_probability": p,
                    "peak_risk": rec["risk_category"],
                    "optimization": snap.get("optimization"),
                    "shelters": snap.get("shelters"),
                    "routes": snap.get("routes"),
                    "affected_population": (snap.get("incident") or {}).get("affected_population"),
                    "decision_latency_ms": (snap.get("latencies") or {}).get("end_to_end"),
                }
                await hub.broadcast("simulation_state", self.state())
                self.tick += 1
                self.sim_time_sec += delay
                await asyncio.sleep(delay)
            self.status = "completed"
            await self._log("Scenario completed", {"ticks": self.tick})
            await mongo.upsert("simulation_runs", {"run_id": self.run_id}, {"status": self.status, "after": self.after, "before": self.before})
            await hub.broadcast("simulation_state", self.state())
        except asyncio.CancelledError:
            self.status = "paused"
            await hub.broadcast("simulation_state", self.state())
            raise

    async def start(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.task and not self.task.done():
            self.task.cancel()
        self.params = params
        self.tick = 0
        self.sim_time_sec = 0.0
        self.events = []
        self.history = []
        self.before = None
        self.after = None
        self.last_obs = None
        self.overrides = {}
        self.started_at = datetime.now(timezone.utc)
        self.run_id = f"SIM-{int(self.started_at.timestamp())}"
        self.status = "running"
        from backend.agents.dialogue import reset_conversation
        from backend.services.progress import reset_progress, publish_progress

        reset_conversation("simulation")
        reset_progress("simulation")
        from backend.ml.change_monitor import reset_monitor

        reset_monitor("simulation")
        self.citizens = []
        self.contact_log = []
        self.human_dispatch_override = False
        from backend.services.demo_extras import DEFAULT_CHECKLIST

        self.checklist = [dict(x) for x in DEFAULT_CHECKLIST]
        self.false_alarm = None
        self._teams_cache = []
        await mongo.insert("simulation_runs", {"run_id": self.run_id, "params": params, "status": self.status})
        await publish_progress("simulation", "scenario", "Launching scenario — waiting for first model tick", scenario=params.get("scenario"))
        self.task = asyncio.create_task(self._loop())
        return self.state()

    async def pause(self) -> dict[str, Any]:
        if self.task and not self.task.done():
            self.task.cancel()
        self.status = "paused"
        return self.state()

    async def resume(self) -> dict[str, Any]:
        if self.status == "paused":
            self.status = "running"
            self.task = asyncio.create_task(self._loop())
        return self.state()

    async def reset(self) -> dict[str, Any]:
        if self.task and not self.task.done():
            self.task.cancel()
        from backend.agents.dialogue import reset_conversation
        from backend.services.progress import reset_progress

        reset_conversation("simulation")
        reset_progress("simulation")
        from backend.ml.change_monitor import reset_monitor

        reset_monitor("simulation")
        self.__init__()
        return self.state()

    def _apply_overrides(self, obs: dict[str, Any]) -> dict[str, Any]:
        o = self.overrides or {}
        if o.get("rainfall_mm") is not None:
            obs["weather"]["rainfall_mm"] = float(o["rainfall_mm"])
            obs["weather"]["source"] = "simulation+operator"
        if o.get("river_m") is not None:
            river = obs["river"]
            river["value_m"] = float(o["river_m"])
            river["percent_of_danger"] = round(100 * river["value_m"] / float(river.get("danger_level_m") or 205.8), 2)
            river["source"] = "simulation+operator"
        if o.get("dam_m") is not None:
            dam = obs["dam"]
            dam["value_m"] = float(o["dam_m"])
            dam["percent_of_danger"] = round(100 * dam["value_m"] / float(dam.get("danger_level_m") or 205.8), 2)
            dam["source"] = "simulation+operator"
        if o.get("flood_probability") is not None:
            obs["flood_probability_override"] = float(o["flood_probability"])
        return obs

    async def apply_override(self, fields: dict[str, Any]) -> dict[str, Any]:
        allowed = {"rainfall_mm", "river_m", "dam_m", "flood_probability"}
        for key, val in fields.items():
            if key in allowed and val is not None:
                self.overrides[key] = float(val)
        if not self.params:
            self.params = {"scenario": "heavy_rainfall", "ticks": 24, "tick_seconds": 2}
        obs = self._apply_overrides(self.last_obs or self._evolve())
        obs["force_talk"] = True
        self.last_obs = obs
        self.sim_time_sec = round(float(self.sim_time_sec or 0) + 1.0, 1)
        self.tick = int(self.tick or 0) + 1
        snap = await run_pipeline(mode="simulation", observations=obs)
        p = (snap.get("prediction") or {}).get("flood_probability")
        rec = {
            "tick": self.tick,
            "sim_time_sec": self.sim_time_sec,
            "rainfall_mm": obs["weather"]["rainfall_mm"],
            "river_m": obs["river"]["value_m"],
            "dam_m": obs["dam"]["value_m"],
            "flood_probability": p,
            "risk_category": (snap.get("prediction") or {}).get("risk_category"),
            "action": (snap.get("policy") or {}).get("action"),
            "source": "operator_edit",
        }
        self.history.append(rec)
        self.after = {**(self.after or {}), "flood_probability": p, "peak_risk": rec["risk_category"]}
        await self._log("Operator edited live cards — agents recalculating", rec)
        monitor = snap.get("card_monitor") or {}
        if monitor.get("sudden"):
            await self._log(
                f"Card monitor: sudden change in {monitor.get('seconds_since_last')}s",
                {"alerts": monitor.get("alerts")},
            )
        await hub.broadcast("simulation_state", self.state())
        return self.state()

    async def _ingest_citizens(self) -> None:
        from backend.agents.dialogue import talk_with_queue
        from backend.services.citizens import roster
        from backend.services.seed import RESCUE_TEAMS
        from backend.services.sos_cluster import cluster_emergencies
        from backend.utils.geo import utcnow

        raw = self.params.get("citizens") or []
        if "sos_count" in (self.params or {}):
            n = max(0, int(self.params.get("sos_count") or 0))
        else:
            n = len(raw) if raw else 10
        citizens = list(raw) if raw else roster(n)
        if raw and n is not None and len(citizens) != n:
            if n < len(citizens):
                citizens = citizens[:n]
            else:
                citizens = (citizens + roster(n))[:n]
        await mongo.update_many("emergency_requests", {"mode": "simulation", "status": "open"}, {"status": "closed"})
        stored = []
        for c in citizens:
            doc = {
                "citizen_name": c.get("citizen_name") or c.get("name") or "Citizen",
                "age": c.get("age"),
                "lat": float(c.get("lat") or 28.65),
                "lon": float(c.get("lon") or 77.26),
                "people": int(c.get("people") or 1),
                "water_level_note": c.get("water_level_note") or c.get("water_depth") or "unknown",
                "emergency_type": "flood_sos",
                "status": "open",
                "mode": "simulation",
                "run_id": self.run_id,
                "timestamp": utcnow(),
            }
            await mongo.insert("emergency_requests", doc)
            stored.append(doc)
        teams = await mongo.find_many("rescue_teams", {}, limit=20, sort_field="team_id", direction=1) or RESCUE_TEAMS
        self.citizens = stored
        self._teams_cache = list(teams)
        clusters = cluster_emergencies(stored, teams)
        by_name = {c.get("citizen_name"): c for c in stored}
        for row in clusters.get("priority_global") or []:
            src = by_name.get(row.get("citizen_name"))
            if src:
                src["rescue_order"] = row.get("rescue_order")
                src["vulnerability"] = row.get("vulnerability")
                src["cluster_id"] = row.get("cluster_id")
                src["assigned_team"] = row.get("assigned_team")
                src["assigned_team_name"] = row.get("assigned_team_name")
        now = utcnow().isoformat()
        from backend.services.person_ops import ensure_ops

        self.contact_log = []
        for row in clusters.get("priority_global") or []:
            entry = {
                "person_index": row.get("rescue_order"),
                "citizen_name": row.get("citizen_name"),
                "age": row.get("age"),
                "water_level_note": row.get("water_level_note"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "people": row.get("people"),
                "vulnerability": row.get("vulnerability"),
                "cluster_id": row.get("cluster_id"),
                "assigned_team": row.get("assigned_team_name") or row.get("assigned_team"),
                "assigned_team_name": row.get("assigned_team_name") or row.get("assigned_team"),
                "called_at": now,
                "answered": True,
                "status": "queued",
                "rescued": None,
            }
            ensure_ops(entry, int(row.get("rescue_order") or len(self.contact_log) + 1))
            # Stagger start so Person 1 advances first, then 2… (still ~12s per stage)
            stagger = max(0, (int(row.get("rescue_order") or 1) - 1) * 2)
            if stagger:
                from datetime import datetime, timezone, timedelta

                entry["ops_stage_at"] = (datetime.now(timezone.utc) - timedelta(seconds=stagger)).isoformat()
            self.contact_log.append(entry)
        weather = (self.last_obs or {}).get("weather") or {}
        rain = float(weather.get("rainfall_mm") or self.params.get("rainfall_intensity") or 55)
        dual = None
        if self.features().get("model_disagreement"):
            from backend.ml.inference import dual_model_view

            dual = dual_model_view(rain)
        first = (clusters.get("priority_global") or [{}])[0]
        second = (clusters.get("priority_global") or [{}, {}])[1] if len(clusters.get("priority_global") or []) > 1 else {}
        await self._log(
            f"Loaded {len(stored)} SOS. Vulnerable-first: {first.get('citizen_name')} age {first.get('age')} first"
            + (f"; {second.get('citizen_name')} {second.get('age')} second" if second else ""),
            {"n_clusters": clusters.get("n_clusters")},
        )
        if self.features().get("agent_talk"):
            await talk_with_queue(
                "simulation",
                stored,
                clusters,
                weather,
                dual=dual,
                bilingual=bool(self.features().get("bilingual_radio")),
            )
            await self._log("Agents asking each person their live status on the radio", {"queue": len(self.contact_log)})
        else:
            await self._log("Agent radio is OFF for this run", {})

    def _tick_checklist(self, item_id: str, done: bool = True) -> None:
        for row in self.checklist:
            if row.get("id") == item_id:
                row["done"] = bool(done)

    async def add_citizen_sos(self, body: dict[str, Any]) -> dict[str, Any]:
        """Add one SOS mid-run: re-cluster, queue at queued, advance every 12s with others."""
        from backend.agents.dialogue import talk_with_citizen
        from backend.services.person_ops import ensure_ops
        from backend.services.seed import RESCUE_TEAMS
        from backend.services.sos_cluster import cluster_emergencies
        from backend.utils.geo import utcnow

        citizen = {
            "citizen_name": str(body.get("citizen_name") or "Citizen").strip() or "Citizen",
            "age": body.get("age"),
            "lat": float(body.get("lat") or 28.65),
            "lon": float(body.get("lon") or 77.26),
            "people": int(body.get("people") or 1),
            "water_level_note": body.get("water_level_note") or "flood water",
            "emergency_type": "flood_sos",
            "status": "queued",
            "live_status": "queued",
            "ops_status": "queued",
            "mode": body.get("mode") or "simulation",
            "run_id": self.run_id,
            "timestamp": utcnow(),
        }
        await mongo.insert("emergency_requests", citizen)
        self.citizens.append(citizen)

        teams = self._teams_cache or await mongo.find_many("rescue_teams", {}, limit=20, sort_field="team_id", direction=1) or list(RESCUE_TEAMS)
        self._teams_cache = list(teams)
        clusters = cluster_emergencies(self.citizens, teams)
        by_name = {c.get("citizen_name"): c for c in self.citizens}
        for row in clusters.get("priority_global") or []:
            src = by_name.get(row.get("citizen_name"))
            if src:
                src["rescue_order"] = row.get("rescue_order")
                src["vulnerability"] = row.get("vulnerability")
                src["cluster_id"] = row.get("cluster_id")
                src["assigned_team"] = row.get("assigned_team")
                src["assigned_team_name"] = row.get("assigned_team_name")

        # Rebuild contact_log preserving ops progress for existing; new person starts queued
        existing_ops = {r.get("citizen_name"): r for r in self.contact_log}
        new_log = []
        for row in clusters.get("priority_global") or []:
            name = row.get("citizen_name")
            prev = existing_ops.get(name)
            if prev and name != citizen["citizen_name"]:
                prev["person_index"] = row.get("rescue_order")
                prev["cluster_id"] = row.get("cluster_id") or prev.get("cluster_id")
                prev["vulnerability"] = row.get("vulnerability") or prev.get("vulnerability")
                prev["assigned_team"] = row.get("assigned_team_name") or row.get("assigned_team") or prev.get("assigned_team")
                new_log.append(prev)
            else:
                entry = {
                    "person_index": row.get("rescue_order"),
                    "citizen_name": name,
                    "age": row.get("age") or citizen.get("age"),
                    "water_level_note": row.get("water_level_note") or citizen.get("water_level_note"),
                    "lat": row.get("lat"),
                    "lon": row.get("lon"),
                    "people": row.get("people"),
                    "vulnerability": row.get("vulnerability"),
                    "cluster_id": row.get("cluster_id"),
                    "assigned_team": row.get("assigned_team_name") or row.get("assigned_team"),
                    "assigned_team_name": row.get("assigned_team_name") or row.get("assigned_team"),
                    "called_at": utcnow().isoformat(),
                    "answered": True,
                    "status": "queued",
                    "rescued": None,
                }
                ensure_ops(entry, int(row.get("rescue_order") or len(new_log) + 1))
                new_log.append(entry)
        self.contact_log = new_log

        weather = ((self.last_obs or {}).get("weather")) or {}
        talk = await talk_with_citizen(citizen.get("mode") or "simulation", citizen, weather)

        # Attach ML snapshot on the new person's journey
        pred = {}
        try:
            from backend.ml.inference import predict_flood, dual_model_view

            rain = float(weather.get("rainfall_mm") or self.params.get("rainfall_intensity") or 55)
            pred = predict_flood(rain) or {}
            dual = dual_model_view(rain) if self.features().get("model_disagreement") else {}
        except Exception:  # noqa: BLE001
            dual = {}
        for row in self.contact_log:
            if row.get("citizen_name") == citizen["citizen_name"]:
                row["flood_probability"] = pred.get("flood_probability")
                row["model_id"] = pred.get("model_id") or "random_forest"
                row["dual"] = dual
                row["journey"].append(
                    {
                        "at": utcnow().isoformat(),
                        "event": "SOS_INGEST",
                        "detail": (
                            f"New SOS ingested · K-means {row.get('cluster_id')} · "
                            f"team {row.get('assigned_team')} · "
                            f"ML P={None if pred.get('flood_probability') is None else round(pred['flood_probability']*100,1)}%"
                        ),
                        "agent": "Administrator Agent",
                        "status": "queued",
                    }
                )
                citizen.update(
                    {
                        "cluster_id": row.get("cluster_id"),
                        "rescue_order": row.get("person_index"),
                        "vulnerability": row.get("vulnerability"),
                        "assigned_team": row.get("assigned_team"),
                        "ops_status": "queued",
                        "live_status": "queued",
                        "flood_probability": row.get("flood_probability"),
                        "model_id": row.get("model_id"),
                    }
                )

        # Push into rescue desk (1-at-a-time queue there too)
        try:
            from backend.services.rescue_desk import desk

            desk.ingest_sos(
                {
                    **citizen,
                    "flood_probability": pred.get("flood_probability"),
                    "model_id": pred.get("model_id"),
                    "cluster_id": citizen.get("cluster_id"),
                }
            )
        except Exception:  # noqa: BLE001
            pass

        await self._log(
            f"New SOS from {citizen['citizen_name']} — queued (advances every 12s: assigned → en route → shelter → rescued)",
            {"citizen": citizen["citizen_name"], "cluster": citizen.get("cluster_id")},
        )
        snap = await run_pipeline(mode="simulation", observations=self._apply_overrides(self.last_obs or self._evolve()))
        if snap:
            snap["emergencies"] = jsonable(self.citizens)
            snap["clusters"] = clusters.get("clusters") or []
            snap["conversation"] = talk
        await hub.broadcast("emergency_update", jsonable(citizen))
        st = self.state()
        st["pipeline"] = snap
        st["conversation"] = talk
        await hub.broadcast("simulation_state", st)
        return st

    def person_detail(self, citizen_name: str) -> dict[str, Any]:
        from backend.services.pipeline import last_snapshot
        from backend.services.person_ops import ensure_ops

        name = (citizen_name or "").strip()
        name_l = name.lower()
        log = next((r for r in self.contact_log if str(r.get("citizen_name") or "").strip().lower() == name_l), None)
        cit = next((c for c in self.citizens if str(c.get("citizen_name") or "").strip().lower() == name_l), None)
        if not log and not cit:
            # partial match fallback
            log = next((r for r in self.contact_log if name_l in str(r.get("citizen_name") or "").lower()), None)
            cit = next((c for c in self.citizens if name_l in str(c.get("citizen_name") or "").lower()), None)
        if not log and not cit:
            return {"available": False, "message": f"Person not found: {name}"}
        if log:
            ensure_ops(log, int(log.get("person_index") or 1))
        merged = {**(cit or {}), **(log or {})}
        snap = last_snapshot("simulation") or {}
        pred = snap.get("prediction") or {}
        dual = pred.get("dual") or {}
        weather = snap.get("weather") or {}
        river = snap.get("river") or {}
        dam = snap.get("dam") or {}
        hist = (self.history or [])[-1] if self.history else {}
        rainfall = hist.get("rainfall_mm")
        if rainfall is None:
            rainfall = weather.get("rainfall_mm")
        river_m = hist.get("river_m")
        if river_m is None:
            river_m = river.get("value_m")
        dam_m = hist.get("dam_m")
        if dam_m is None:
            dam_m = dam.get("value_m")
        flood_p = merged.get("flood_probability")
        if flood_p is None:
            flood_p = hist.get("flood_probability")
        if flood_p is None:
            flood_p = pred.get("flood_probability")

        return {
            "available": True,
            "case": {
                "case_id": merged.get("case_id") or f"SIM-{merged.get('citizen_name') or name}",
                "citizen_name": merged.get("citizen_name") or name,
                "age": merged.get("age"),
                "lat": merged.get("lat"),
                "lon": merged.get("lon"),
                "people": merged.get("people"),
                "water_level_note": merged.get("water_level_note"),
                "status": merged.get("ops_status") or merged.get("live_status") or merged.get("status") or "queued",
                "ambulance_name": merged.get("ambulance_name"),
                "shelter_name": merged.get("shelter_name"),
                "cluster_id": merged.get("cluster_id"),
                "model_id": merged.get("model_id") or pred.get("model_id") or "random_forest",
                "flood_probability": flood_p,
                "journey": merged.get("journey") or [],
                "timestamps": merged.get("timestamps") or {},
                "rescued": merged.get("rescued"),
                "vulnerability": merged.get("vulnerability"),
                "triage": merged.get("triage"),
                "assigned_team": merged.get("assigned_team_name") or merged.get("assigned_team"),
                "scenario": self.params.get("scenario"),
            },
            "environment": {
                "scenario": self.params.get("scenario"),
                "run_id": self.run_id,
                "rainfall_mm": rainfall,
                "river_m": river_m,
                "dam_m": dam_m,
                "flood_probability": flood_p,
                "risk_category": hist.get("risk_category") or pred.get("risk_category"),
                "model_id": pred.get("model_id") or "random_forest",
                "rf": dual.get("random_forest"),
                "xgb": dual.get("xgboost"),
            },
            "message_counts": {},
            "ambulances_free": None,
            "vacant_total": None,
        }

    async def set_checklist(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        if items:
            self.checklist = list(items)
        await hub.broadcast("simulation_state", self.state())
        return self.state()

    async def ask_agent(self, question: str) -> dict[str, Any]:
        from backend.services.demo_extras import answer_ask_agent

        return answer_ask_agent(question, self.state())

    async def set_features(self, features: dict[str, Any]) -> dict[str, Any]:
        current = self.features()
        current.update({k: bool(v) for k, v in (features or {}).items() if k in DEFAULT_FEATURES})
        self.params["features"] = current
        await hub.broadcast("simulation_state", self.state())
        return self.state()

    async def force_dispatch(self) -> dict[str, Any]:
        self.human_dispatch_override = True
        await self._log("Operator override — auto-dispatch allowed despite model disagreement", {})
        obs = self._apply_overrides(self.last_obs or self._evolve())
        obs["human_dispatch_override"] = True
        obs["force_talk"] = True
        self.last_obs = obs
        snap = await run_pipeline(mode="simulation", observations=obs)
        await hub.broadcast("simulation_state", self.state())
        st = self.state()
        st["pipeline"] = snap
        return st


engine = SimulationEngine()
