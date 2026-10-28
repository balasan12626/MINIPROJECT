"""F6 — measured route-choice benchmark on the live road graph.

Compares, for the SAME Yen candidate set the live app builds
(person_ops.route_candidates):

  * dijkstra    — candidate 0, the shortest weighted path
  * qaoa        — the live choice: classically SIMULATED QAOA over the
                  candidates (optimization/qaoa_route.py), cache cleared per trip
  * exhaustive  — the lowest QUBO cost among the same candidates (the best any
                  chooser over these candidates can do)
  * direct      — straight line, REFERENCE ONLY (not a drivable route)

across flood-blockage levels, using the engine's own rule
(road blocked when flood_exposure >= 0.85 - blockage).

Trips are SYNTHETIC: seeded random SOS-like origins around seed.ZONES and
destinations drawn from the allocatable shelters. QAOA chooses among the same k
candidates, so it can at best equal exhaustive search over them; nothing here
measures or claims a quantum speed-up.

Writes models/route_benchmark_v1.json (deterministic for a fixed seed) and
models/route_benchmark_v1.timing.json (solver wall times — vary run to run).

    python scripts/bench_routes.py --trips 200 --seed 42 --blockage 0,0.1,0.2,0.3
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.optimization import qaoa_route  # noqa: E402
from backend.optimization.qaoa_route import candidate_costs, qaoa_choose  # noqa: E402
from backend.services import person_ops  # noqa: E402
from backend.services.route_engine import travel_minutes  # noqa: E402
from backend.services import seed as seed_mod  # noqa: E402
from backend.services.seed import ROADS, ZONES  # noqa: E402  (same objects; contents follow the active city)
from backend.utils.geo import haversine_km  # noqa: E402

BLOCK_BASE = 0.85  # engine rule: blocked when flood_exposure >= 0.85 - blockage
METHODS = ("dijkstra", "qaoa", "exhaustive", "direct")
DEFAULT_OUT = ROOT / "models" / "route_benchmark_v1.json"


def roads_at(blockage: float) -> list[dict[str, Any]]:
    out = []
    for r in ROADS:
        x = dict(r)
        x["blocked"] = float(x.get("flood_exposure") or 0) >= BLOCK_BASE - blockage
        x["accessible"] = not x["blocked"]
        out.append(x)
    return out


def make_trips(n: int, seed: int) -> list[dict[str, Any]]:
    """Synthetic trips: SOS-like origin near a flood zone → an allocatable shelter."""
    rng = random.Random(seed)
    reg = person_ops.shelter_registry()
    shelters = [reg[s] for s in person_ops.SHELTER_POOL if s in reg]
    trips = []
    for i in range(n):
        z = rng.choice(ZONES)
        s = rng.choice(shelters)
        trips.append(
            {
                "trip": i,
                "zone": z.get("name"),
                "origin": [round(float(z["lat"]) + rng.gauss(0, 0.008), 5), round(float(z["lon"]) + rng.gauss(0, 0.008), 5)],
                "shelter": s["name"],
                "destination": [s["lat"], s["lon"]],
            }
        )
    return trips


def _metrics(c: dict[str, Any], cost: float) -> dict[str, Any]:
    return {
        "travel_min": round(travel_minutes(c["weighted_km"]), 3),
        "hazard": round(c["hazard_km"], 4),
        "worst_exposure": round(c["hazard"], 4),
        "cost": round(cost, 5),
        "km": round(c["km"], 3),
        "road_ids": c["road_ids"],
    }


def run_trip(trip: dict[str, Any], roads: list[dict[str, Any]]) -> tuple[dict[str, Any], float | None]:
    a, b = tuple(trip["origin"]), tuple(trip["destination"])
    straight = haversine_km(a[0], a[1], b[0], b[1])
    rec: dict[str, Any] = {
        "trip": trip["trip"],
        "direct": {"travel_min": round(travel_minutes(straight), 3), "km": round(straight, 3), "reference_only": True},
    }
    found = person_ops.route_candidates(a, b, roads)
    cands = found["cands"]
    if not cands:
        # no_open_road: every road between the two junctions is closed.
        # Otherwise both ends snap to the same junction — no road trip to choose.
        rec["unreachable"] = True
        rec["no_open_road"] = found["no_open_road"]
        return rec, None
    costs = candidate_costs(cands)
    best = min(range(len(cands)), key=lambda i: costs[i])
    qaoa_time = None
    if len(cands) > 1:
        qaoa_route._solve.cache_clear()  # time a cold solve, as for a new trip
        t0 = time.perf_counter()
        q = qaoa_choose(costs)
        qaoa_time = (time.perf_counter() - t0) * 1000.0
        pick = q["chosen"]
        rec["qaoa_chosen_probability"] = q["chosen_probability"]
        rec["qaoa_matches_exhaustive"] = bool(q["matches_exhaustive"])
    else:
        pick = 0  # one candidate: nothing to choose (the live app skips QAOA too)
        rec["qaoa_chosen_probability"] = None
        rec["qaoa_matches_exhaustive"] = True
    rec["candidates"] = len(cands)
    rec["dijkstra"] = _metrics(cands[0], costs[0])
    rec["qaoa"] = {**_metrics(cands[pick], costs[pick]), "index": pick}
    rec["exhaustive"] = {**_metrics(cands[best], costs[best]), "index": best}
    rec["qaoa_equals_dijkstra"] = pick == 0
    rec["exhaustive_equals_dijkstra"] = best == 0
    return rec, qaoa_time


def _stats(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0, "mean": None, "median": None, "p95": None}
    s = sorted(xs)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return {"n": len(s), "mean": round(statistics.fmean(s), 3), "median": round(statistics.median(s), 3), "p95": round(p95, 3)}


def summarise(blockage: float, recs: list[dict[str, Any]], roads: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in recs if not r.get("unreachable")]
    multi = [r for r in ok if r["candidates"] > 1]
    pct = lambda n, d: round(100.0 * n / d, 2) if d else None  # noqa: E731
    out: dict[str, Any] = {
        "blockage": blockage,
        "roads_closed": sorted(r["road_id"] for r in roads if r["blocked"]),
        "trips": len(recs),
        "routed": len(ok),
        "no_open_road": sum(1 for r in recs if r.get("no_open_road")),
        "same_junction": sum(1 for r in recs if r.get("unreachable") and not r.get("no_open_road")),
        "single_candidate_trips": len(ok) - len(multi),
        "qaoa_equals_exhaustive_pct": pct(sum(r["qaoa_matches_exhaustive"] for r in multi), len(multi)),
        "qaoa_equals_dijkstra_pct": pct(sum(r["qaoa_equals_dijkstra"] for r in multi), len(multi)),
        "exhaustive_equals_dijkstra_pct": pct(sum(r["exhaustive_equals_dijkstra"] for r in multi), len(multi)),
        "methods": {},
    }
    for m in METHODS:
        rows = [r[m] for r in ok]
        out["methods"][m] = {
            "travel_min": _stats([x["travel_min"] for x in rows]),
            "km": _stats([x["km"] for x in rows]),
            **(
                {}
                if m == "direct"
                else {"hazard": _stats([x["hazard"] for x in rows]), "cost": _stats([x["cost"] for x in rows])}
            ),
        }
    return out


def _git() -> dict[str, Any]:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = bool(
            subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
        )
        return {"commit": sha or None, "dirty_worktree": dirty}
    except Exception:  # noqa: BLE001
        return {"commit": None, "dirty_worktree": None}


def run(
    trips: int = 200, seed: int = 42, levels: list[float] | None = None, city: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    from backend.geo import cities

    cities.activate(city or cities.LEGACY)  # F7: the road graph of this city
    levels = levels if levels is not None else [0.0, 0.1, 0.2, 0.3]
    trip_list = make_trips(trips, seed)
    result: dict[str, Any] = {
        "benchmark": "route_choice_v1",
        "description": (
            "Route choice on the live Delhi road graph: Dijkstra (shortest), QAOA choice (classically simulated "
            "statevector QAOA over the same Yen candidates), exhaustive best over those candidates, and the straight "
            "line as a reference only. Trips are synthetic."
        ),
        "synthetic_trips": True,
        "city": cities.active_id(),
        "graph": {"junctions": len(seed_mod.GRAPH_NODES), "road_segments": len(seed_mod.GRAPH_EDGES), "roads": len(ROADS)},
        "settings": {
            "trips": trips,
            "seed": seed,
            "blockage_levels": levels,
            "blockage_rule": f"road blocked when flood_exposure >= {BLOCK_BASE} - blockage (same as the engine)",
            "candidates_k": person_ops.QAOA_CANDIDATES,
            "qaoa_layers": qaoa_route.LAYERS,
            "qaoa_shots": qaoa_route.SHOTS,
            "qaoa_penalty": qaoa_route.PENALTY,
            "qaoa_hazard_weight": qaoa_route.HAZARD_WEIGHT,
            "qaoa_seed": 7,
            "cost_formula": "travel/max_travel + hazard_weight * worst_edge_exposure (optimization/qaoa_route.candidate_costs)",
            "hazard_metric": "sum over edges of flood_exposure * edge length (km)",
            "speed_kmh": person_ops.RESCUE_SPEED_KMH,
        },
        "code": _git(),
        "levels": [],
        "trips": trip_list,
    }
    timing: dict[str, Any] = {"benchmark": "route_choice_v1", "note": "wall time of one cold qaoa_choose per trip, ms", "levels": []}
    for b in levels:
        roads = roads_at(b)
        recs, times = [], []
        for t in trip_list:
            rec, ms = run_trip(t, roads)
            recs.append(rec)
            if ms is not None:
                times.append(ms)
        result["levels"].append({**summarise(b, recs, roads), "per_trip": recs})
        timing["levels"].append({"blockage": b, "qaoa_ms": _stats(times)})
    return result, timing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trips", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--blockage", default="0,0.1,0.2,0.3", help="comma-separated blockage levels")
    ap.add_argument("--out", default=None, help="default models/route_benchmark_v1[_<city>].json")
    ap.add_argument("--city", default=None, help="city id (backend/data/cities); default the demo network")
    args = ap.parse_args(argv)
    levels = [float(x) for x in args.blockage.split(",") if x.strip()]
    result, timing = run(args.trips, args.seed, levels, args.city)
    out = Path(args.out) if args.out else (
        DEFAULT_OUT if not args.city or args.city == "delhi_seed" else DEFAULT_OUT.with_name(f"route_benchmark_v1_{args.city}.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=False), encoding="utf-8")
    out.with_suffix(".timing.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")
    for lv, tm in zip(result["levels"], timing["levels"]):
        m = lv["methods"]
        print(
            f"blockage {lv['blockage']:.2f}: routed {lv['routed']}/{lv['trips']} "
            f"(no open road {lv['no_open_road']}, same junction {lv['same_junction']}, "
            f"1 candidate {lv['single_candidate_trips']}), "
            f"Dijkstra {m['dijkstra']['travel_min']['mean']} min, QAOA {m['qaoa']['travel_min']['mean']} min, "
            f"exhaustive {m['exhaustive']['travel_min']['mean']} min · QAOA = exhaustive {lv['qaoa_equals_exhaustive_pct']}% "
            f"· QAOA {tm['qaoa_ms']['mean']} ms"
        )
    print(f"wrote {out} and {out.with_suffix('.timing.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
