"""F33 — which assumptions matter? Sensitivity of time-to-safety to every
labelled assumption of the operations model.

    python scripts/sensitivity_ops.py --city delhi [--runs 10] [--sobol 8]
    → models/ops_sensitivity_v1_<city>.json   (tornado data + optional Sobol indices)

* One-at-a-time (OAT): each assumption is set to the low and the high end of a
  STATED range (with the reason for the range), everything else at its default;
  the same seeded synthetic operations are replayed for every setting (paired).
* Optional variance-based design (`--sobol N`): Saltelli A/B/AB_i matrices,
  first-order (Saltelli 2010) and total-order (Jansen) estimators in plain numpy —
  no new dependency. With small N the indices are noisy; the bootstrap CI says so.
* Output metric: mean time to safety (simulated minutes) under the `optimal`
  policy, plus the share of people served within the horizon.
Synthetic instances only (make_instance); nothing here is a field measurement.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.geo import cities  # noqa: E402
from backend.services import ops_sim  # noqa: E402
from backend.services import person_ops as po  # noqa: E402
from backend.services import route_engine, seed  # noqa: E402

_spec = importlib.util.spec_from_file_location("mc", ROOT / "scripts" / "monte_carlo_ops.py")
mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mc)

# name: (default, low, high, reason for the range)
PARAMS: dict[str, tuple[float, float, float, str]] = {
    "ambulances": (10, 6, 14, "fleet size is assumed (no ambulance depot list exists); ±40 % around the 10-unit pool"),
    "speed_kmh": (25.0, 18.0, 32.0, "rescue vehicle speed on flooded urban roads is assumed; ±~28 % around 25 km/h"),
    "shelter_capacity_factor": (1.0, 0.5, 1.5, "shelter capacities are assumed by type or Sphere-derived with an assumed usable share; ×0.5–×1.5"),
    "mobilise_s": (po.MOBILISE_SECONDS, 1.0, 4.0, "crew roll-out time is assumed; 1–4 wall s = 2–8 sim min"),
    "warning_compliance": (0.0, 0.0, 0.6, "early-warning compliance is assumed (F23); 0–60 %"),
    "blockage_shift": (0.0, -0.05, 0.10, "starting road blockage is drawn from an assumed range; shifted −0.05 / +0.10"),
}
NOT_VARIED = {
    "accept_timeout_s": "only acts in manual accept mode; the stress test uses simulated crews that accept (zero effect by construction)",
    "boat_fleet": "boats (F22) default to 0; varied only once boats are enabled in a run",
    "crew_rules": "act only over long operations; measured separately by the F25 long run (ops_long_v1)",
    "medical_weights": "the synthetic instances carry no medical flags; triage weights cannot act here",
}


@contextlib.contextmanager
def applied(x: dict[str, float]):
    """Set the assumptions for one play (script process only), then restore."""
    old_speed, old_mob = route_engine.RESCUE_SPEED_KMH, po.MOBILISE_SECONDS
    old_caps = [s.get("capacity") for s in seed.SHELTERS]
    route_engine.RESCUE_SPEED_KMH = float(x["speed_kmh"])
    po.MOBILISE_SECONDS = float(x["mobilise_s"])
    for s, c in zip(seed.SHELTERS, old_caps):
        s["capacity"] = int(round(int(c or 0) * float(x["shelter_capacity_factor"])))
    pool = [f"Ambulance Unit {i}" for i in range(1, int(round(x["ambulances"])) + 1)]
    try:
        with po.isolated(pool=pool):
            yield
    finally:
        route_engine.RESCUE_SPEED_KMH, po.MOBILISE_SECONDS = old_speed, old_mob
        for s, c in zip(seed.SHELTERS, old_caps):
            s["capacity"] = c


def evaluate(x: dict[str, float], instances: list[dict[str, Any]]) -> dict[str, float]:
    means, served, total = [], 0, 0
    with applied(x):
        for inst in instances:
            inst2 = {**inst, "blockage0": min(0.95, max(0.0, inst["blockage0"] + float(x["blockage_shift"])))}
            run = ops_sim.play(inst2, ops_sim.POLICIES["optimal"], compliance=float(x["warning_compliance"]))
            xs = [p["safe_min"] for p in run["people"] if p["safe_min"] is not None]
            if xs:
                means.append(statistics.fmean(xs))
            served += len(xs)
            total += len(run["people"])
    return {"mean_time_to_safety_min": round(statistics.fmean(means), 3) if means else None,
            "served_share": round(served / total, 4) if total else None}


def oat(instances, names=None) -> dict[str, Any]:
    base_x = {k: v[0] for k, v in PARAMS.items()}
    base = evaluate(base_x, instances)
    rows = []
    for k in names or PARAMS:
        d, lo, hi, why = PARAMS[k]
        r_lo = evaluate({**base_x, k: lo}, instances)
        r_hi = evaluate({**base_x, k: hi}, instances)
        b = base["mean_time_to_safety_min"]
        rows.append({
            "parameter": k, "default": d, "low": lo, "high": hi, "reason": why,
            "at_low": r_lo, "at_high": r_hi,
            "effect_low_min": None if b is None or r_lo["mean_time_to_safety_min"] is None else round(r_lo["mean_time_to_safety_min"] - b, 3),
            "effect_high_min": None if b is None or r_hi["mean_time_to_safety_min"] is None else round(r_hi["mean_time_to_safety_min"] - b, 3),
        })
        print(f"  OAT {k}: low {rows[-1]['effect_low_min']} / high {rows[-1]['effect_high_min']} min", flush=True)
    rows.sort(key=lambda r: -max(abs(r["effect_low_min"] or 0), abs(r["effect_high_min"] or 0)))
    return {"baseline": base, "tornado": rows}


def sobol(instances, n: int, seed_: int) -> dict[str, Any]:
    """Saltelli design over the uniform ranges; first-order S1 (Saltelli 2010) and
    total ST (Jansen), with a bootstrap 95 % CI over the N base rows."""
    import numpy as np

    names = list(PARAMS)
    k = len(names)
    rng = np.random.default_rng(seed_)
    lo = np.array([PARAMS[p][1] for p in names], dtype=float)
    hi = np.array([PARAMS[p][2] for p in names], dtype=float)
    A = lo + rng.random((n, k)) * (hi - lo)
    B = lo + rng.random((n, k)) * (hi - lo)

    def f(row):
        return evaluate(dict(zip(names, row)), instances)["mean_time_to_safety_min"] or 0.0

    fA = np.array([f(r) for r in A])
    fB = np.array([f(r) for r in B])
    fAB = np.zeros((k, n))
    for i in range(k):
        ABi = A.copy()
        ABi[:, i] = B[:, i]
        fAB[i] = [f(r) for r in ABi]
        print(f"  Sobol column {i + 1}/{k} done", flush=True)

    def indices(idx):
        var = np.var(np.concatenate([fA[idx], fB[idx]]))
        if var <= 0:
            return np.zeros(k), np.zeros(k)
        s1 = np.array([np.mean(fB[idx] * (fAB[i][idx] - fA[idx])) / var for i in range(k)])
        st = np.array([0.5 * np.mean((fA[idx] - fAB[i][idx]) ** 2) / var for i in range(k)])
        return s1, st

    s1, st = indices(np.arange(n))
    boot = [indices(rng.integers(0, n, n)) for _ in range(200)]
    b1 = np.array([b[0] for b in boot])
    bt = np.array([b[1] for b in boot])
    return {
        "n_base": n, "evaluations": n * (k + 2), "method": "Saltelli A/B/AB_i; S1 Saltelli 2010, ST Jansen 1999; bootstrap 200",
        "indices": [{"parameter": p, "S1": round(float(s1[i]), 3), "S1_ci95": [round(float(np.percentile(b1[:, i], 2.5)), 3), round(float(np.percentile(b1[:, i], 97.5)), 3)],
                     "ST": round(float(st[i]), 3), "ST_ci95": [round(float(np.percentile(bt[:, i], 2.5)), 3), round(float(np.percentile(bt[:, i], 97.5)), 3)]}
                    for i, p in enumerate(names)],
        "note": "Small N: treat as indicative; a CI that spans 0 means the effect is not resolved at this budget.",
    }


def run(city: str, runs: int, seed_: int, n_sos: int, surge: int, sobol_n: int = 0, names=None) -> dict[str, Any]:
    cities.activate(city)
    po.ROUTE_CHOOSER = "dijkstra"
    try:
        instances = [ops_sim.make_instance(random.Random(seed_ * 1000 + i), n_sos, surge) for i in range(runs)]
        out = {
            "benchmark": "ops_sensitivity_v1", "city": city, "synthetic": True,
            "settings": {"runs": runs, "seed": seed_, "initial_sos": n_sos, "surge_sos": surge, "policy": "optimal",
                         "metric": "mean time to safety (simulated minutes), paired over the same operations"},
            "ranges": {k: {"default": v[0], "low": v[1], "high": v[2], "reason": v[3]} for k, v in PARAMS.items()},
            "not_varied": NOT_VARIED,
            **oat(instances, names),
            "code": mc._git(),
        }
        if sobol_n:
            out["sobol"] = sobol(instances, sobol_n, seed_)
        return out
    finally:
        po.ROUTE_CHOOSER = "qaoa"
        cities.activate(cities.LEGACY)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sensitivity of the rescue operation to its assumptions")
    ap.add_argument("--city", default="delhi")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sos", type=int, default=30)
    ap.add_argument("--surge", type=int, default=15)
    ap.add_argument("--sobol", type=int, default=0, help="N base rows for the variance-based design (0 = OAT only)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    res = run(args.city, args.runs, args.seed, args.sos, args.surge, args.sobol)
    out = Path(args.out) if args.out else ROOT / "models" / f"ops_sensitivity_v1_{args.city}.json"
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    for r in res["tornado"]:
        print(f"{r['parameter']:26s} low {r['effect_low_min']:+} high {r['effect_high_min']:+} min")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
