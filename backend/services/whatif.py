"""F16 — what-if planner jobs on the live run.

One job at a time, results kept in memory for the current run only. The
snapshot is taken on the event loop (a consistent copy of the live state);
the plays run in a worker thread (`asyncio.to_thread`) on deep copies, so the
live run is never touched. Every option replays the SAME synthetic arrivals
per run seed (paired comparison against the "no change" baseline).
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from typing import Any

from backend.services import ops_sim

STALE_TICKS = 5
LABEL = "Simulated from the live state — not a forecast of the real world."


class JobBusy(Exception):
    pass


class WhatIfJobs:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.running: str | None = None
        self.last_done: dict[str, Any] | None = None

    def reset(self) -> None:
        """A new run starts: old results describe another run, and a job in
        flight is cancelled (the new run may swap the city's road lists)."""
        for j in self.jobs.values():
            if j["status"] in ("queued", "running"):
                j["cancelled"] = True
        self.jobs = {k: v for k, v in self.jobs.items() if v["status"] in ("queued", "running")}
        self.last_done = None

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.jobs.get(job_id)

    async def submit(self, engine, options: list[dict[str, Any]], horizon_min: float, runs: int,
                     arrivals: bool = True) -> dict[str, Any]:
        if self.running:
            raise JobBusy(self.running)
        if engine.status not in ("running", "paused", "completed") or not engine.contact_log:
            raise ValueError("start a scenario first — the what-if copies the live run")
        for o in options:
            bad = ops_sim.validate_option(o)
            if bad:
                raise ValueError(bad)
        opts = [{"kind": "baseline"}] + [o for o in options if o.get("kind") != "baseline"]
        snap = ops_sim.snapshot(engine)  # on the loop: consistent copy, before any await
        job_id = uuid.uuid4().hex[:12]
        job = {
            "job_id": job_id, "status": "queued", "progress": 0.0,
            "run_id": snap["run_id"], "tick": snap["tick"], "city": snap["city"],
            "snapshot_at": snap["taken_at"].isoformat(), "horizon_min": horizon_min, "runs": runs,
            "options": [{"key": f"o{i}", "label": ops_sim.option_label(o), **o} for i, o in enumerate(opts)],
            "arrival_rate_per_sim_hour": round(snap["arrival_rate_per_wall_s"] * 3600 / ops_sim.po.TIME_SCALE, 2)
            if arrivals else 0.0,
            "synthetic_arrivals": bool(arrivals and snap["arrival_rate_per_wall_s"] > 0),
            "label": LABEL, "accept_mode_note": "simulated crews accept every job (a what-if cannot know a driver's answer)"
            if snap["accept_mode"] == "manual" else None,
            "results": None, "error": None,
        }
        self.jobs[job_id] = job
        self.running = job_id
        asyncio.get_running_loop().create_task(self._run(job, snap, opts, horizon_min, runs, arrivals))
        return job

    async def _run(self, job, snap, opts, horizon_min, runs, arrivals) -> None:
        job["status"] = "running"
        t0 = time.perf_counter()
        try:
            job["results"] = await asyncio.to_thread(self._compute, job, snap, opts, horizon_min, runs, arrivals)
            job["status"] = "done"
            job["seconds"] = round(time.perf_counter() - t0, 1)
            self.last_done = job
        except Exception as e:  # noqa: BLE001 — a failed job reports itself, never the live run
            job["status"], job["error"] = "failed", str(e)[:300]
        finally:
            self.running = None

    @staticmethod
    def _compute(job, snap, opts, horizon_min, runs, arrivals) -> dict[str, Any]:
        per: dict[str, list[dict[str, Any]]] = {}
        total = len(opts) * runs
        done = 0
        keys = [o["key"] for o in job["options"]]
        for key, opt in zip(keys, opts):
            per[key] = []
            for i in range(runs):
                if job.get("cancelled"):
                    raise RuntimeError("cancelled — a new run was started")
                per[key].append(ops_sim.play_whatif(snap, opt, horizon_min, random.Random(1000 + i), arrivals))
                done += 1
                job["progress"] = round(done / total, 3)
        summary = ops_sim.whatif_summary({("baseline" if k == "o0" else k): v for k, v in per.items()})
        out = []
        for o in job["options"]:
            s = summary["baseline" if o["key"] == "o0" else o["key"]]
            out.append({"key": o["key"], "label": o["label"], "option": {k: v for k, v in o.items() if k not in ("key", "label")}, **s})
        return {"options": out}


jobs = WhatIfJobs()


def facts(current_tick: int | None = None) -> dict[str, Any] | None:
    """The last finished what-if, compact, for the AI Assistant's facts."""
    j = jobs.last_done
    if not j or not j.get("results"):
        return None
    rows = []
    for o in j["results"]["options"]:
        t = o["time_to_safe_censored_min"]
        rows.append({"option": o["label"], "mean_min_to_safe": t["mean"], "p90_min_to_safe": t["p90"],
                     "still_waiting_per_run": o["still_waiting_per_run"],
                     "diff_vs_no_change_min": (o.get("vs_baseline") or {}).get("mean_diff_min")})
    return {"taken_at_tick": j["tick"], "runs": j["runs"], "horizon_min": j["horizon_min"],
            "stale": current_tick is not None and current_tick - j["tick"] >= STALE_TICKS,
            "label": LABEL, "options": rows}
