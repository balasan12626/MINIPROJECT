"""F12 — headless Monte-Carlo evaluation of the whole rescue operation.

    python scripts/monte_carlo_ops.py --city delhi --runs 60 --seed 1
    → models/ops_montecarlo_v1_<city>.json

Each run is one SYNTHETIC flood operation on a city's real road network,
played by the live stage machine (backend/services/person_ops.py) on a virtual
clock — no UI, no ML pipeline, no LLM:

* SOS callers: seeded, placed around the city's OSM flood zones; ages and water
  depths drawn so ~half need an ambulance; a second SURGE arrives mid-run;
* roads close over time by the engine's own rule (flood_exposure >= 0.85 -
  blockage(t)), blockage growing from a random start, with live re-routing;
* one random shelter is closed mid-run (F2 re-allocation);
* EVERY policy replays the SAME instance (paired comparison): nearest_depot
  (original rule), greedy, optimal, and optimal + pre-positioning (F9).

Routes use the shortest weighted road path (person_ops.ROUTE_CHOOSER =
"dijkstra"); the QAOA route choice is measured separately (F6). Reported:
time to pickup and time to safety (simulated minutes) — mean / p50 / p90 — per
policy, per vulnerability, plus paired per-run differences vs the original rule.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.geo import cities  # noqa: E402
from backend.services import person_ops as po  # noqa: E402
from backend.services import seed  # noqa: E402
from backend.utils.geo import haversine_km  # noqa: E402

from backend.services.ops_sim import (  # noqa: E402,F401 — the ONE simulator core (F16 shares it)
    HORIZON_S,
    POLICIES,
    STEP_S,
    TICKS,
    WATER,
    blockage_at,
    make_instance,
    paired,
    play,
    roads_at,
    stats,
    summarise,
)


def _git() -> dict[str, Any]:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip())
        return {"commit": sha or None, "dirty_worktree": dirty}
    except Exception:  # noqa: BLE001
        return {"commit": None, "dirty_worktree": None}


def run(city: str, runs: int, seed_: int, n_sos: int, surge: int, policies: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    cities.activate(city)
    po.ROUTE_CHOOSER = "dijkstra"
    try:
        per_policy: dict[str, list[dict[str, Any]]] = {p: [] for p in policies}
        timing: dict[str, float] = {p: 0.0 for p in policies}
        for i in range(runs):
            inst = make_instance(random.Random(seed_ * 1000 + i), n_sos, surge)
            for name in policies:
                t0 = time.perf_counter()
                per_policy[name].append(play(inst, POLICIES[name]))
                timing[name] += time.perf_counter() - t0
            print(f"  run {i + 1}/{runs} done", flush=True)
    finally:
        po.ROUTE_CHOOSER = "qaoa"
    result = {
        "benchmark": "ops_montecarlo_v1",
        "city": city,
        "synthetic": True,
        "description": __doc__.split("\n\n")[1].strip(),
        "settings": {
            "runs": runs, "seed": seed_, "initial_sos": n_sos, "surge_sos": surge, "policies": policies,
            "step_wall_s": STEP_S, "ticks_with_flood_growth": TICKS, "horizon_wall_s": HORIZON_S,
            "time_scale": po.TIME_SCALE, "ambulances": len(po.AMBULANCE_POOL), "route_chooser": "dijkstra (shortest weighted path)",
            "blockage_start_range": [0.05, 0.25], "shelter_closed_per_run": 1,
        },
        "graph": {"junctions": len(seed.GRAPH_NODES), "roads": len(seed.ROADS), "shelters": len(po.SHELTER_POOL),
                  "depots": len(seed.RESCUE_TEAMS)},
        "code": _git(),
        "summary": summarise(per_policy),
        # Fair baseline = first_free (same position-aware world); the idealised
        # original rule is listed in `summary` only.
        "paired_vs_first_free": paired(per_policy, "first_free") if "first_free" in policies else {},
        "notes": [
            "nearest_depot is idealised (an ambulance is launched from the depot nearest the caller wherever it really is); "
            "it is reported for reference and is not a fair comparison for the position-aware policies.",
            "Pre-positioning uses a fixed flood probability of 0.7 for hotspot weights (no ML model runs in the batch).",
            "All callers, ages, depths, arrival times, closures and the closed shelter are synthetic (seeded).",
        ],
    }
    return result, {"benchmark": "ops_montecarlo_v1", "seconds_per_policy": {k: round(v, 1) for k, v in timing.items()}}


def warning_sweep(city: str, runs: int, seed_: int, n_sos: int, surge: int, levels: list[float],
                  policy: str = "optimal", lead_min: float = 30.0) -> dict[str, Any]:
    """F23: same instances, one policy, early-warning compliance swept. The
    compliance share is ASSUMED — the curve is the result, not any one point."""
    from backend.services.ops_sim import play as _play

    cities.activate(city)
    po.ROUTE_CHOOSER = "dijkstra"
    try:
        per: dict[str, list[dict[str, Any]]] = {f"{c:g}": [] for c in levels}
        for i in range(runs):
            inst = make_instance(random.Random(seed_ * 1000 + i), n_sos, surge)
            for c in levels:
                per[f"{c:g}"].append(_play(inst, POLICIES[policy], compliance=c, lead_min=lead_min))
            print(f"  run {i + 1}/{runs} done", flush=True)
    finally:
        po.ROUTE_CHOOSER = "qaoa"
    summary = summarise(per)
    base = per[f"{levels[0]:g}"]
    curve = []
    for c in levels:
        k = f"{c:g}"
        s = summary[k]
        curve.append({
            "compliance": c,
            "sos_avoided_per_run": round(sum(r.get("sos_avoided", 0) for r in per[k]) / max(1, runs), 2),
            "people_called_per_run": round(s["people"] / max(1, runs), 2),
            "time_to_safety_min": s["time_to_safety_min"],
            "served": s["served"], "censored": s["censored"],
            "total_wait_min_per_run": round(sum(p["safe_min"] if p["safe_min"] is not None else HORIZON_S * po.TIME_SCALE / 60
                                                for r in per[k] for p in r["people"]) / max(1, runs), 1),
        })
    return {
        "benchmark": "ops_warning_sweep_v1", "city": city, "synthetic": True,
        "settings": {"runs": runs, "seed": seed_, "initial_sos": n_sos, "surge_sos": surge, "policy": policy,
                     "warning_lead_sim_min": lead_min, "zone_road_km": 1.5, "compliance_levels": levels},
        "compliance_source": "assumed — not measured; swept so no conclusion rests on one value",
        "curve": curve, "code": _git(),
        "notes": ["Only late (surge) callers can be avoided; the first callers are already in the queue when the warning goes out.",
                  "A caller is 'warned' if a zone within 1.5 km had its warning before the caller's arrival.",
                  "All callers, arrival times and closures are synthetic (seeded)."],
    }


def long_run(city: str, runs: int, seed_: int, hours: float = 72.0, per_hour: float = 6.0,
             policy: str = "optimal") -> dict[str, Any]:
    """F25: a 72 h operation, crew rules ON vs OFF on the same instances. The
    rules (shift / rest / range / refuel) are ASSUMED and labelled."""
    from backend.services.ops_sim import make_long_instance
    from backend.services.ops_sim import play as _play

    cities.activate(city)
    po.ROUTE_CHOOSER = "dijkstra"
    horizon = (hours + 24.0) * 3600.0 / po.TIME_SCALE  # +24 h to finish the last calls
    crew = {"on": True, **po.CREW_DEFAULTS}
    try:
        per: dict[str, list[dict[str, Any]]] = {"crew_rules_off": [], "crew_rules_on": []}
        for i in range(runs):
            inst = make_long_instance(random.Random(seed_ * 1000 + i), hours, per_hour)
            per["crew_rules_off"].append(_play(inst, POLICIES[policy], horizon_s=horizon))
            per["crew_rules_on"].append(_play(inst, POLICIES[policy], crew=crew, horizon_s=horizon))
            print(f"  run {i + 1}/{runs} done ({len(inst['callers'])} SOS)", flush=True)
    finally:
        po.ROUTE_CHOOSER = "qaoa"
    return {
        "benchmark": "ops_long_v1", "city": city, "synthetic": True,
        "settings": {"runs": runs, "seed": seed_, "hours": hours, "sos_per_hour": per_hour, "policy": policy,
                     "ambulances": len(po.AMBULANCE_POOL), "horizon_hours": hours + 24.0},
        "crew_rules": crew, "crew_rules_source": po.CREW_SOURCE,
        "summary": summarise(per),
        "paired_on_vs_off": paired(per, "crew_rules_off"),
        "code": _git(),
        "notes": ["SOS arrive all through the operation (Poisson); all synthetic and seeded.",
                  "Crew rules are assumed parameters, not a measured rota."],
    }


def _worst_group_median(run: dict[str, Any]) -> float | None:
    groups: dict[str, list[float]] = {}
    for p in run["people"]:
        if p["safe_min"] is not None:
            groups.setdefault(p["vulnerability"] or "standard", []).append(p["safe_min"])
    meds = [statistics.median(v) for v in groups.values() if len(v) >= 2]
    return max(meds) if meds else None


def _mean_ci(xs: list[float]) -> dict[str, Any]:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0, "mean": None, "ci95": None}
    m = statistics.fmean(xs)
    h = 1.96 * (statistics.pstdev(xs) if len(xs) > 1 else 0.0) / math.sqrt(len(xs))
    return {"n": len(xs), "mean": round(m, 2), "ci95": [round(m - h, 2), round(m + h, 2)]}


def fairness_sweep(city: str, runs: int, seed_: int, n_sos: int, surge: int, lambdas: list[float]) -> dict[str, Any]:
    """F32: the measured fair-vs-fast curve. Same instances for every point;
    first_free and optimal are the reference policies; fair(λ) for each λ."""
    from backend.services.ops_sim import play as _play

    cities.activate(city)
    po.ROUTE_CHOOSER = "dijkstra"
    points = [("first_free", POLICIES["first_free"]), ("optimal", POLICIES["optimal"])] + [
        (f"fair λ={lam:g}", {"dispatch_policy": "fair", "preposition": False, "fair_lambda": lam}) for lam in lambdas]
    try:
        per: dict[str, list[dict[str, Any]]] = {name: [] for name, _ in points}
        for i in range(runs):
            inst = make_instance(random.Random(seed_ * 1000 + i), n_sos, surge)
            for name, pol in points:
                per[name].append(_play(inst, pol))
            print(f"  run {i + 1}/{runs} done", flush=True)
    finally:
        po.ROUTE_CHOOSER = "qaoa"
    summary = summarise(per)
    curve = []
    for name, pol in points:
        runs_ = per[name]
        means = [statistics.fmean([p["safe_min"] for p in r["people"] if p["safe_min"] is not None])
                 for r in runs_ if any(p["safe_min"] is not None for p in r["people"])]
        curve.append({"point": name, "lambda": pol.get("fair_lambda"), "policy": pol["dispatch_policy"],
                      "mean_time_to_safety_min": _mean_ci(means),
                      "worst_group_median_min": _mean_ci([_worst_group_median(r) for r in runs_]),
                      "served": summary[name]["served"], "people": summary[name]["people"]})
    return {
        "benchmark": "ops_fairness_v1", "city": city, "synthetic": True,
        "settings": {"runs": runs, "seed": seed_, "initial_sos": n_sos, "surge_sos": surge, "lambdas": lambdas,
                     "groups": "vulnerability classes (F14)", "worst_group": "per run, the largest median time to safety "
                     "among groups with >= 2 served people; mean over runs with 95% CI"},
        "curve": curve, "summary": summary, "paired_vs_optimal": paired(per, "optimal"), "code": _git(),
        "notes": ["fair λ=0 is the optimal policy by construction.",
                  "Reported as measured; a larger λ is not guaranteed to lower the worst group's wait on every instance."],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Monte-Carlo evaluation of the rescue operation")
    ap.add_argument("--city", default="delhi")
    ap.add_argument("--runs", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sos", type=int, default=30)
    ap.add_argument("--surge", type=int, default=15)
    ap.add_argument("--policies", default=",".join(POLICIES))
    ap.add_argument("--out", default=None)
    ap.add_argument("--compliance", default=None,
                    help="F23: e.g. 0,0.2,0.4,0.6 → models/ops_warning_sweep_v1_<city>.json (policy: optimal)")
    ap.add_argument("--lead-min", type=float, default=30.0, help="F23 warning lead time, simulated minutes")
    ap.add_argument("--fair-lambdas", default=None, help="F32: e.g. 0,0.5,1,2,4 → models/ops_fairness_v1_<city>.json")
    ap.add_argument("--long", action="store_true", help="F25: 72 h operation, crew rules on vs off → ops_long_v1_<city>.json")
    ap.add_argument("--hours", type=float, default=72.0)
    ap.add_argument("--per-hour", type=float, default=6.0)
    args = ap.parse_args(argv)
    if args.fair_lambdas:
        lams = [float(x) for x in args.fair_lambdas.split(",")]
        res = fairness_sweep(args.city, args.runs if args.runs != 60 else 20, args.seed, args.sos, args.surge, lams)
        out = Path(args.out) if args.out else ROOT / "models" / f"ops_fairness_v1_{args.city}.json"
        out.write_text(json.dumps(res, indent=2), encoding="utf-8")
        for p in res["curve"]:
            print(f"{p['point']:14s} mean {p['mean_time_to_safety_min']['mean']}  worst-group median {p['worst_group_median_min']['mean']}")
        print(f"wrote {out}")
        cities.activate(cities.LEGACY)
        return 0
    if args.long:
        res = long_run(args.city, args.runs if args.runs != 60 else 10, args.seed, args.hours, args.per_hour)
        out = Path(args.out) if args.out else ROOT / "models" / f"ops_long_v1_{args.city}.json"
        out.write_text(json.dumps(res, indent=2), encoding="utf-8")
        for name, s in res["summary"].items():
            print(f"{name:16s} served {s['served']}/{s['people']}  time-to-safety mean {s['time_to_safety_min']['mean']} p90 {s['time_to_safety_min']['p90']}")
        print(f"wrote {out}")
        cities.activate(cities.LEGACY)
        return 0
    if args.compliance:
        levels = [float(x) for x in args.compliance.split(",")]
        res = warning_sweep(args.city, args.runs, args.seed, args.sos, args.surge, levels, lead_min=args.lead_min)
        out = Path(args.out) if args.out else ROOT / "models" / f"ops_warning_sweep_v1_{args.city}.json"
        out.write_text(json.dumps(res, indent=2), encoding="utf-8")
        for p in res["curve"]:
            print(f"compliance {p['compliance']:.1f}: avoided {p['sos_avoided_per_run']}/run, "
                  f"time-to-safety mean {p['time_to_safety_min']['mean']} min")
        print(f"wrote {out}")
        cities.activate(cities.LEGACY)
        return 0
    policies = [p for p in args.policies.split(",") if p in POLICIES]
    result, timing = run(args.city, args.runs, args.seed, args.sos, args.surge, policies)
    out = Path(args.out) if args.out else ROOT / "models" / f"ops_montecarlo_v1_{args.city}.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    out.with_suffix(".timing.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")
    for name, s in result["summary"].items():
        tts = s["time_to_safety_min"]
        print(f"{name:16s} served {s['served']}/{s['people']}  time-to-safety mean {tts['mean']} p90 {tts['p90']} min")
    for name, d in result["paired_vs_first_free"].items():
        print(f"  {name:16s} vs first_free: {d['mean_diff_min']:+} min (95% CI {d['ci95_min']}), faster in {d['faster_in_pct_of_runs']}% of runs")
    print(f"wrote {out}")
    cities.activate(cities.LEGACY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
