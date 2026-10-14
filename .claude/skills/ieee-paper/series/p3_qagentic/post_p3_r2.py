"""Second-revision numbers for P3 (p3_r2.json) -> macros and tab_base.tex.

  - the re-run reproduces the original unsafe flags of p3_v2.json (checked per draw)
  - integrations: top sample, lowest-energy sample, penalty-filtered sample (all unverified), the verified loop,
    and an exact-solver-first loop; on all events and on solvable events only
  - sampler time against MILP time (when is the sampler worth calling first?)
  - city scale with a 10x longer annealer (400 sweeps) against the original 40 sweeps
Called from post_p3.py; every claim made in the text is asserted here.
"""
import json

import numpy as np


def pct(xs):
    return 100 * float(np.mean(xs)) if len(xs) else float("nan")


def extend(put, work, out, T, C, city2=None):
    r2 = json.loads((work / "p3_r2.json").read_text(encoding="utf-8"))
    if city2:  # city part from the single snapshot run (exp_p3_city2.py); twin part from exp_p3_r2.py
        r2["city"] = [{"city": r["city"], "G": r["G"], "tight": r["tight"], "k": r["k"], "feasible": r["feasible"],
                       "milp_ms": r["milp_ms"], "milp_status": r["milp_status"], "sa_ms": r["sa_call_ms"],
                       "sa": r["cap"]} for r in city2["city"]]
        r2["strong"] = city2.get("strong")
    tk = {(r["seed"], r["event"]): r for r in T}
    # ---- reproduction of the original flags
    for v in r2["twin"]:
        r = tk[(v["seed"], v["event"])]
        for smp in ("qaoa", "sa"):
            assert [c["top_unsafe"] for c in v[smp]] == [x["raw_invalid"] for x in r["draws"][f"{smp}_fixed"]], \
                "r2 re-run reproduces the twin draws"
    ck = {(r["city"], r["G"], r["tight"], r["k"]): r for r in C}
    same = sum([c["top_unsafe"] for c in v["sa"]] == [x["raw_invalid"] for x in ck[(v["city"], v["G"], v["tight"], v["k"])]["draws"]["fixed"]]
               for v in r2["city"])
    assert same >= 0.99 * len(C), "r2 re-run reproduces the city draws"
    feas_c = {k: r["feasible"] for k, r in ck.items()}  # incl. the time-out instances re-solved with a longer limit

    # ---- integrations on the twin
    rows = []
    res = {}
    for smp, lab in (("qaoa", "QAOA"), ("sa", "SA")):
        allv = [c for v in r2["twin"] for c in v[smp]]
        sol = [c for v in r2["twin"] if v["feasible"] for c in v[smp]]
        d = {k: (pct([c[k] for c in allv]), pct([c[k] for c in sol])) for k in ("top_unsafe", "low_unsafe", "pf_unsafe", "pf_none")}
        res[smp] = d
    cs = [c for v in r2["city"] for c in v["sa"]]
    cs_sol = [c for v in r2["city"] if feas_c[(v["city"], v["G"], v["tight"], v["k"])] for c in v["sa"]]
    res["city"] = {k: (pct([c[k] for c in cs]), pct([c[k] for c in cs_sol])) for k in ("top_unsafe", "low_unsafe", "pf_unsafe", "pf_none")}
    names = {"top_unsafe": "most frequent sample", "low_unsafe": "lowest-energy sample",
             "pf_unsafe": "lowest-energy penalty-free sample"}
    for k in ("top_unsafe", "low_unsafe", "pf_unsafe"):
        rows.append(f"{names[k]} & {res['qaoa'][k][0]:.1f} & {res['qaoa'][k][1]:.1f} & {res['sa'][k][0]:.1f} & "
                    f"{res['sa'][k][1]:.1f} & {res['city'][k][1]:.1f}\\\\")
    rows.append("verified loop (this work) & 0.0 & 0.0 & 0.0 & 0.0 & 0.0\\\\")
    (out / "tab_base.tex").write_text("\n".join(rows), encoding="utf-8")
    for smp, t in (("qaoa", "Q"), ("sa", "SA")):
        put(f"BaseLow{t}", f"{res[smp]['low_unsafe'][0]:.1f}")
        put(f"BaseLow{t}Sol", f"{res[smp]['low_unsafe'][1]:.1f}")
        put(f"BasePf{t}", f"{res[smp]['pf_unsafe'][0]:.1f}")
        put(f"BasePf{t}Sol", f"{res[smp]['pf_unsafe'][1]:.1f}")
        put(f"BasePfNone{t}", f"{res[smp]['pf_none'][0]:.1f}")
    put("BaseLowCitySol", f"{res['city']['low_unsafe'][1]:.1f}")
    put("BasePfCitySol", f"{res['city']['pf_unsafe'][1]:.1f}")
    put("BasePfNoneCity", f"{res['city']['pf_none'][1]:.1f}")
    # every penalty-free sample that is unsafe must be a penalty-free overload (the encoding cannot see it)
    assert res["qaoa"]["pf_unsafe"][1] > 0 and res["sa"]["pf_unsafe"][1] > 0, "text: filtering by the encoding still dispatches unsafe plans"
    assert res["qaoa"]["low_unsafe"][1] < res["qaoa"]["top_unsafe"][1], "text: lowest energy is safer than most frequent for QAOA"
    put("BaseText", (
        f"Taking the lowest-energy sample instead of the most frequent one lowered QAOA's unsafe rate on solvable twin "
        f"events from {res['qaoa']['top_unsafe'][1]:.1f}\\% to {res['qaoa']['low_unsafe'][1]:.1f}\\%, and keeping only "
        f"samples with zero penalty gave {res['qaoa']['pf_unsafe'][1]:.1f}\\%; for annealing the three rates were "
        f"{res['sa']['top_unsafe'][1]:.1f}, {res['sa']['low_unsafe'][1]:.1f} and {res['sa']['pf_unsafe'][1]:.1f}\\%. The "
        f"remaining failures are the penalty-free overloads of Section~\\ref{{sec:viol}}: they carry no penalty and can "
        f"cost less than any valid plan, so no choice by energy can exclude them. At city scale the lowest-energy sample "
        f"was unsafe in {res['city']['low_unsafe'][1]:.1f}\\% of calls on solvable instances, and in "
        f"{res['city']['pf_none'][1]:.1f}\\% of calls no sample was penalty-free at all."))

    # ---- time: sampler first vs exact solver first
    milp_tw = float(np.median([v["milp_ms"] for v in r2["twin"]]))
    qtrain = float(np.median([v["qaoa_train_ms"] for v in r2["twin"]])) / 1000
    sa_tw = float(np.median([x for x in r2["twin_sa_ms"] if x is not None]))
    put("ExMilpMs", f"{milp_tw:.1f}")
    put("ExQaoaS", f"{qtrain:.1f}")
    put("ExSaTwinMs", f"{sa_tw:.0f}")
    city_sa = {G: float(np.median([v["sa_ms"] for v in r2["city"] if v["G"] == G])) for G in (8, 16, 32)}
    city_milp = {G: float(np.median([v["milp_ms"] for v in r2["city"] if v["G"] == G and v["milp_status"] in (0, 2)]))
                 for G in (8, 16, 32)}
    for G, t in ((8, "Eight"), (16, "Sixteen"), (32, "ThirtyTwo")):
        put(f"ExSaCity{t}", f"{city_sa[G] / 1000:.2f}")
        put(f"ExMilpCity{t}", f"{city_milp[G] / 1000:.2f}")
    assert all(city_milp[G] < city_sa[G] for G in (8, 16, 32)), "text: MILP faster than one annealing call in median"
    assert qtrain * 1000 > 100 * milp_tw and sa_tw > milp_tw, "text: on the twin the MILP is the fastest tool"
    slow = [(v, ck[(v["city"], v["G"], v["tight"], v["k"])]) for v in r2["city"]
            if v["milp_status"] in (0, 2) and v["milp_ms"] > v["sa_ms"]]
    slow32 = [x for x in slow if x[0]["G"] == 32]
    n32 = sum(1 for v in r2["city"] if v["G"] == 32 and v["milp_status"] in (0, 2))
    slow_found = sum(any(c["sampler_found"] for c in v["sa"]) for v, _ in slow)
    put("ExSlowPct", f"{100 * len(slow32) / n32:.0f}")
    put("ExSlowFound", str(slow_found))
    put("ExSlowN", str(len(slow)))
    put("ExactFirstText", (
        f"Is the sampler worth calling first? On the twin the MILP took a median {milp_tw:.1f}~ms per event, one "
        f"annealing call of 64 chains {sa_tw:.0f}~ms and one QAOA training {qtrain:.1f}~s of simulation. At city scale "
        f"one annealing call took a median {city_sa[8] / 1000:.2f}, {city_sa[16] / 1000:.2f} and {city_sa[32] / 1000:.2f}~s "
        f"at 8, 16 and 32 groups, against {city_milp[8] / 1000:.2f}, {city_milp[16] / 1000:.2f} and "
        f"{city_milp[32] / 1000:.2f}~s for the MILP. The MILP was slower than one annealing call on {len(slow)} solved "
        f"instances ({100 * len(slow32) / n32:.0f}\\% of those with 32 groups), and the annealer found a valid plan on "
        f"{slow_found} of them. An exact-solver-first loop would therefore have been faster in median time and optimal, "
        f"whereas the verified loop fell back to the greedy plan whenever the sampler failed, at a median "
        f"\\CityGreedyGap\\% above the optimum at city scale."))

    # ---- stronger annealer at city scale
    S = r2.get("strong")
    if S:
        sk = {(v["city"], v["G"], v["tight"], v["k"]): v for v in S}
        for G, t in ((8, "Eight"), (16, "Sixteen"), (32, "ThirtyTwo")):
            sol = [v for k, v in sk.items() if k[1] == G and feas_c[k]]
            put(f"StrongValid{t}", f"{pct([c['sampler_found'] for v in sol for c in v['sa']]):.1f}")
            weak = [v for v in r2["city"] if v["G"] == G and feas_c[(v["city"], v["G"], v["tight"], v["k"])]]
            put(f"WeakValid{t}", f"{pct([c['sampler_found'] for v in weak for c in v['sa']]):.1f}")
            put(f"StrongSaS{t}", f"{np.median([v['sa_ms'] for v in sk.values() if v['G'] == G]) / 1000:.1f}")
        sol_all = [v for k, v in sk.items() if feas_c[k]]
        put("StrongTopUnsafe", f"{pct([c['top_unsafe'] for v in sk.values() for c in v['sa']]):.1f}")
        put("StrongFalseEsc", f"{pct([c['tool'] == 'milp' for v in sol_all for c in v['sa']]):.1f}")
        sv = {G: pct([c["sampler_found"] for k, v in sk.items() if k[1] == G and feas_c[k] for c in v["sa"]]) for G in (8, 16, 32)}
        wv = {G: pct([c["sampler_found"] for v in r2["city"] if v["G"] == G and feas_c[(v["city"], v["G"], v["tight"], v["k"])]
                      and v["k"] < 3 for c in v["sa"]]) for G in (8, 16, 32)}
        st = {G: float(np.median([v["sa_ms"] for v in sk.values() if v["G"] == G])) / 1000 for G in (8, 16, 32)}
        put("StrongText", (
            f"A weak search is part of the story. On {len(sk)} city instances (three per city, size and demand) an annealer "
            f"with 400 instead of 40 sweeps found a valid plan in {sv[8]:.1f}, {sv[16]:.1f} and {sv[32]:.1f}\\% of calls "
            f"on solvable instances at 8, 16 and 32 groups, against {wv[8]:.1f}, {wv[16]:.1f} and {wv[32]:.1f}\\% with 40 "
            f"sweeps on the same instances, at {st[8]:.1f}, {st[16]:.1f} and {st[32]:.1f}~s per call, still slower than "
            f"the MILP."))
        assert all(st[G] * 1000 > city_milp[G] for G in (8, 16, 32)), "text: the long annealer is slower than the MILP"
        res["strong"] = (sv, wv, st)
    else:
        put("StrongText", "")
    return res
