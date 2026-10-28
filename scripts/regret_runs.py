"""F34 — hindsight check of past runs (regret).

    python scripts/regret_runs.py [--limit 20] [--api http://localhost:8000]
    → models/ops_regret_v1.json

For each stored run (F5 frames, read through the backend API):
* rebuild its SOS arrivals, road closures and shelter changes (`ops_sim.from_frames`);
* replay it on the shared simulator under every dispatch policy;
* compute a per-person HINDSIGHT BOUND (knows every arrival in advance, ignores
  queueing — a lower bound, NOT achievable live; `ops_sim.hindsight_bound`);
* regret = mean time to safety − mean hindsight bound, per policy and as recorded.
Fidelity: the run replayed with its OWN policy vs the recorded times (mean
absolute difference), so a reader can see how faithful the replay is. Runs
recorded before the policy was stored in frames say "policy unknown".
Replays use shortest-path routes (the live run used the QAOA chooser).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.geo import cities  # noqa: E402
from backend.services import ops_sim  # noqa: E402
from backend.services import person_ops as po  # noqa: E402

REPLAY_POLICIES = ["first_free", "greedy", "optimal"]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 2) if xs else None


def fetch_frames(api: str, run_id: str, client: httpx.Client) -> list[dict[str, Any]]:
    out, start = [], 1
    while True:
        page = client.get(f"{api}/api/simulation/runs/{run_id}/frames", params={"start": start, "limit": 200}).json()
        frames = page.get("frames") or []
        out += frames
        if len(frames) < 200:
            return out
        start += 200


def regret_of(inst: dict[str, Any]) -> dict[str, Any]:
    lb = ops_sim.hindsight_bound(inst)
    names_lb = {n for n, v in lb.items() if v is not None}
    res: dict[str, Any] = {"people": len(inst["callers"]), "hindsight_bound_mean_min": _mean([lb[n] for n in names_lb])}
    rec = inst.get("recorded_safe_min") or {}
    common_rec = [n for n in names_lb if rec.get(n) is not None]
    res["recorded"] = {"mean_min": _mean([rec[n] for n in common_rec]), "served": len(common_rec),
                       "regret_min": _mean([rec[n] - lb[n] for n in common_rec])}
    res["replayed"] = {}
    for p in REPLAY_POLICIES + (["own"] if inst.get("policy") else []):
        pol = inst["policy"] if p == "own" else ops_sim.POLICIES[p]
        run = ops_sim.play(inst, pol)
        by = {x["citizen_name"]: x["safe_min"] for x in run["people"]}
        common = [n for n in names_lb if by.get(n) is not None]
        res["replayed"][p] = {"mean_min": _mean([by[n] for n in common]), "served": len(common),
                              "regret_min": _mean([by[n] - lb[n] for n in common])}
        if p == "own":
            both = [n for n in common if rec.get(n) is not None]
            res["fidelity"] = {"policy": inst["policy"]["dispatch_policy"], "people_compared": len(both),
                               "mean_abs_diff_min": _mean([abs(by[n] - rec[n]) for n in both])}
    if "fidelity" not in res:
        res["fidelity"] = {"policy": "unknown (run recorded before F34 stored the policy)", "people_compared": 0,
                           "mean_abs_diff_min": None}
    best = min((v["mean_min"], k) for k, v in res["replayed"].items() if v["mean_min"] is not None and k != "own") \
        if any(v["mean_min"] is not None for k, v in res["replayed"].items() if k != "own") else (None, None)
    res["best_policy_in_hindsight"] = best[1]
    return res


def run(api: str, limit: int) -> dict[str, Any]:
    out = []
    po.ROUTE_CHOOSER = "dijkstra"
    try:
        with httpx.Client(timeout=60) as c:
            runs = (c.get(f"{api}/api/simulation/runs", params={"limit": limit}).json() or {}).get("runs") or []
            for r in runs:
                frames = fetch_frames(api, r["run_id"], c)
                if len(frames) < 2:
                    continue
                inst = ops_sim.from_frames(frames)
                cities.activate(inst.get("city") or cities.LEGACY)
                print(f"  {r['run_id']} ({inst.get('city')}, {len(inst['callers'])} SOS)", flush=True)
                out.append({"run_id": r["run_id"], "city": inst.get("city"), "scenario": r.get("scenario"),
                            "started_at": r.get("started_at"), "frames": len(frames), **regret_of(inst)})
    finally:
        po.ROUTE_CHOOSER = "qaoa"
        cities.activate(cities.LEGACY)
    return {
        "benchmark": "ops_regret_v1", "runs": out,
        "hindsight_bound": "per person: first dispatch slot + roll-out + shortest open road from the nearest depot or "
                           "shelter + shortest open road to the nearest shelter; no queueing. A LOWER BOUND, not achievable live.",
        "notes": ["Replays use shortest-path routes; the live runs used the QAOA route chooser.",
                  "Regret = mean time to safety − mean hindsight bound over the people the bound can reach."],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hindsight regret of stored runs")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    res = run(args.api, args.limit)
    out = Path(args.out) if args.out else ROOT / "models" / "ops_regret_v1.json"
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    for r in res["runs"]:
        print(f"{r['run_id']}: bound {r['hindsight_bound_mean_min']} · recorded {r['recorded']['mean_min']} "
              f"(regret {r['recorded']['regret_min']}) · best replay {r['best_policy_in_hindsight']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
