"""F5 — save every run so it can be replayed, and keep the playbook across restarts.

Frames are COMPACT snapshots of the one authoritative state (engine +
person_ops), written once per tick and once per operator action:

    simulation_frames {run_id, seq, tick, at, cause, probability, tier, rain,
                       river, dam, citizens[...], fleet_board, shelter_allocation,
                       roads_closed, counts}
    mas_messages      {run_id, id, at, severity, kind, title, text, from, to}
    simulation_runs   {run_id, scenario, started_at, status, ticks, sos,
                       rescued, peak_probability, frames}   (summary upsert)
    settings          {_id: "playbook", data}

Nothing here simulates anything: a frame is a copy of what state() already
served. When Mongo is down the LAST run is kept in memory (≤ RING_FRAMES
frames) and every response says `persisted: false`.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from backend.database import mongo
from backend.utils.geo import jsonable, utcnow

RING_FRAMES = 400
RING_MESSAGES = 600
KEEP_RUNS = 50
ACTIVE = ("assigned", "en_route", "to_shelter")

ROW_KEYS = (
    "citizen_name",
    "age",
    "people",
    "lat",
    "lon",
    "water_level_note",
    "vulnerability",
    "cluster_id",
    "ops_status",
    "ops_stage_at",
    "ops_stage_seconds",
    "ops_wait_reason",
    "unit_name",
    "unit_role",
    "unit_base",
    "unit_base_name",
    "shelter_name",
    "shelter_lat",
    "shelter_lon",
    "eta_min",
    "eta_to_shelter_min",
    "timestamps",
    "driver_accepted",
    "accepted_at",
    "source",
    "route_alert",
    "shelter_wait",
    "rescue_order",
    "person_index",
    "medical",
    "destination_kind",
    "merged_into",
)


def _leg(route: dict[str, Any] | None) -> dict[str, Any] | None:
    if not route:
        return None
    return {
        "points": [[round(float(p[0]), 5), round(float(p[1]), 5)] for p in route.get("points") or []],
        "km": route.get("km"),
        "sim_minutes": route.get("sim_minutes"),
        "method": route.get("method"),
    }


def _city_id() -> str | None:
    try:
        from backend.geo.cities import active_id

        return active_id()
    except Exception:  # noqa: BLE001
        return None


def make_frame(eng: Any, seq: int, cause: str) -> dict[str, Any]:
    """Compact copy of the engine's current state — never the full state()."""
    from backend.services.person_ops import fleet_board, shelter_allocation_board

    last = eng.history[-1] if eng.history else {}
    citizens = []
    counts: dict[str, int] = {}
    for r in eng.contact_log:
        st = r.get("ops_status") or "queued"
        counts[st] = counts.get(st, 0) + 1
        row = {k: r.get(k) for k in ROW_KEYS if r.get(k) is not None}
        if st in ACTIVE:  # route lines only while someone drives them
            row["route_to_person"] = _leg(r.get("route_to_person"))
            row["route_to_shelter"] = _leg(r.get("route_to_shelter"))
        citizens.append(row)
    return jsonable(
        {
            "run_id": eng.run_id,
            "seq": seq,
            "tick": eng.tick,
            "at": utcnow().isoformat(),
            "cause": cause,
            "status": eng.status,
            "scenario": eng.params.get("scenario"),
            "city": _city_id(),
            "probability": last.get("flood_probability"),
            "risk_category": last.get("risk_category"),
            "tier": eng.mas.tier,
            "rainfall_mm": last.get("rainfall_mm"),
            "river_m": last.get("river_m"),
            "dam_m": last.get("dam_m"),
            "citizens": citizens,
            "fleet_board": fleet_board(eng.contact_log),
            "shelter_allocation": shelter_allocation_board(eng.contact_log, eng.shelter_overrides),
            "shelter_overrides": eng.shelter_overrides,
            "roads_closed": sorted(r["road_id"] for r in eng.roads_now() if r.get("blocked")),
            "accept_mode": getattr(eng, "accept_mode", "auto"),
            # F34: what a hindsight replay needs to reproduce the run's own choices.
            "dispatch_policy": (eng.params or {}).get("dispatch_policy") or "nearest_depot",
            "fair_lambda": (eng.params or {}).get("fair_lambda"),
            "preposition": bool((eng.params or {}).get("preposition")),
            "counts": counts,
        }
    )


class ReplayStore:
    def __init__(self) -> None:
        self.run_id: str | None = None
        self.seq = 0
        self.frames: deque[dict[str, Any]] = deque(maxlen=RING_FRAMES)
        self.messages: deque[dict[str, Any]] = deque(maxlen=RING_MESSAGES)
        self.summary: dict[str, Any] = {}

    def _switch(self, run_id: str) -> None:
        self.__init__()
        self.run_id = run_id

    async def record(self, eng: Any, cause: str) -> dict[str, Any] | None:
        """Save one frame + every MAS message posted since the last frame."""
        if not eng.run_id:
            return None
        if eng.run_id != self.run_id:
            self._switch(eng.run_id)
        self.seq += 1
        frame = make_frame(eng, self.seq, cause)
        self.frames.append(frame)
        await mongo.insert("simulation_frames", dict(frame))
        for m in eng.mas.drain_outbox():
            msg = jsonable({**m, "run_id": eng.run_id})
            self.messages.append(msg)
            await mongo.insert("mas_messages", dict(msg))
        probs = [h.get("flood_probability") for h in eng.history if h.get("flood_probability") is not None]
        self.summary = {
            "run_id": eng.run_id,
            "scenario": eng.params.get("scenario"),
            "city": _city_id(),
            "started_at": eng.started_at.isoformat() if eng.started_at else None,
            "status": eng.status,
            "ticks": eng.tick,
            "sos": len(eng.contact_log),
            "rescued": sum(1 for r in eng.contact_log if r.get("ops_status") == "rescued"),
            "people_rescued": sum(int(r.get("people") or 1) for r in eng.contact_log if r.get("ops_status") == "rescued"),
            "peak_probability": max(probs) if probs else None,
            "frames": self.seq,
            "last_frame_at": frame["at"],
        }
        await mongo.upsert("simulation_runs", {"run_id": eng.run_id}, dict(self.summary))
        return frame

    # ---- reads ---------------------------------------------------------------
    def _ring_run(self) -> dict[str, Any] | None:
        return {**self.summary, "persisted": False} if self.summary else None

    async def list_runs(self, limit: int = 20) -> dict[str, Any]:
        persisted = mongo.is_connected()
        runs = []
        if persisted:
            docs = await mongo.find_page("simulation_runs", {"frames": {"$gt": 0}}, [("created_at", -1)], limit=limit)
            runs = [{**_run_fields(d), "persisted": True} for d in docs]
        ring = self._ring_run()
        if ring and not any(r["run_id"] == ring["run_id"] for r in runs):
            runs.insert(0, ring)
        return {"runs": runs[:limit], "persisted": persisted}

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        if mongo.is_connected():
            doc = await mongo.find_latest("simulation_runs", {"run_id": run_id})
            if doc:
                return {**_run_fields(doc), "params": doc.get("params"), "before": doc.get("before"),
                        "after": doc.get("after"), "persisted": True}
        if run_id == self.run_id and self.summary:
            return self._ring_run()
        return None

    async def frames_page(self, run_id: str, frm: int = 1, to: int | None = None, limit: int = 100) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200))
        frm = max(1, int(frm))
        hi = to if to is not None else 10**9
        if mongo.is_connected() and await mongo.count("simulation_frames", {"run_id": run_id}):
            q = {"run_id": run_id, "seq": {"$gte": frm, "$lte": hi}}
            docs = await mongo.find_page("simulation_frames", q, [("seq", 1)], limit=limit)
            total = await mongo.count("simulation_frames", {"run_id": run_id})
            for d in docs:
                for k in ("_id", "created_at", "updated_at", "timestamp"):
                    d.pop(k, None)
            return {"run_id": run_id, "frames": jsonable(docs), "total": total, "persisted": True}
        if run_id == self.run_id:
            sel = [f for f in self.frames if frm <= f["seq"] <= hi][:limit]
            return {"run_id": run_id, "frames": sel, "total": len(self.frames), "persisted": False}
        return {"run_id": run_id, "frames": [], "total": 0, "persisted": mongo.is_connected()}

    async def messages_of(self, run_id: str, limit: int = 1000) -> dict[str, Any]:
        if mongo.is_connected() and await mongo.count("mas_messages", {"run_id": run_id}):
            docs = await mongo.find_page("mas_messages", {"run_id": run_id}, [("id", 1)], limit=limit)
            for d in docs:
                for k in ("_id", "created_at", "updated_at", "timestamp"):
                    d.pop(k, None)
            return {"run_id": run_id, "messages": jsonable(docs), "persisted": True}
        if run_id == self.run_id:
            return {"run_id": run_id, "messages": list(self.messages)[-limit:], "persisted": False}
        return {"run_id": run_id, "messages": [], "persisted": mongo.is_connected()}

    async def report_state(self, run_id: str) -> dict[str, Any] | None:
        """A state-shaped dict for services/report.build_report_pdf from stored data."""
        run = await self.get_run(run_id)
        if not run:
            return None
        page = await self.frames_page(run_id, 1, None, 200)
        frames = page["frames"]
        total = page["total"]
        if total > len(frames):  # make sure the LAST frame is included
            tail = await self.frames_page(run_id, total, total, 1)
            frames = frames + tail["frames"]
        if not frames:
            return None
        last = frames[-1]
        history = [{"tick": f.get("tick"), "flood_probability": f.get("probability")} for f in frames if f.get("cause") == "tick"]
        probs = [h["flood_probability"] for h in history if h["flood_probability"] is not None]
        return {
            "run_id": run_id,
            "scenario": run.get("scenario"),
            "started_at": run.get("started_at"),
            "history": history,
            "citizens": last.get("citizens") or [],
            "current": {"flood_probability": last.get("probability"), "peak_flood_probability": max(probs) if probs else None},
            "after": run.get("after") or {},
            "after_action_summary": [
                f"Replayed from {total} stored frames ({'MongoDB' if page['persisted'] else 'memory, not persisted'}).",
                f"{run.get('rescued') or 0} of {run.get('sos') or 0} SOS delivered to a shelter by the last frame.",
            ],
        }

    async def retention(self, keep: int = KEEP_RUNS) -> dict[str, int]:
        """Delete everything stored for runs older than the newest `keep`."""
        if not mongo.is_connected():
            return {"runs": 0, "frames": 0, "messages": 0}
        old = await mongo.find_page("simulation_runs", {}, [("created_at", -1)], skip=keep, limit=100000, projection={"run_id": 1})
        ids = [d.get("run_id") for d in old if d.get("run_id")]
        if not ids:
            return {"runs": 0, "frames": 0, "messages": 0}
        q = {"run_id": {"$in": ids}}
        out = {
            "frames": await mongo.delete_many("simulation_frames", q),
            "messages": await mongo.delete_many("mas_messages", q),
            "events": await mongo.delete_many("simulation_events", q),
            "runs": await mongo.delete_many("simulation_runs", q),
        }
        return out


def _run_fields(d: dict[str, Any]) -> dict[str, Any]:
    return jsonable({k: d.get(k) for k in ("run_id", "scenario", "city", "started_at", "status", "ticks", "sos", "rescued",
                                           "people_rescued", "peak_probability", "frames", "last_frame_at")})


# ---- playbook persistence ---------------------------------------------------------


async def save_playbook(data: dict[str, Any] | None) -> bool:
    """Store the edited playbook; None (reset) deletes the stored copy."""
    if data is None:
        return bool(await mongo.delete_many("settings", {"_id": "playbook"}))
    return await mongo.upsert("settings", {"_id": "playbook"}, {"data": jsonable(data)})


async def load_playbook() -> bool:
    """On startup: put the stored playbook (if any) into the agents."""
    from backend.agents.mas import load_playbook as _load

    doc = await mongo.find_latest("settings", {"_id": "playbook"})
    if doc and isinstance(doc.get("data"), dict):
        _load(doc["data"])
        return True
    return False


store = ReplayStore()
