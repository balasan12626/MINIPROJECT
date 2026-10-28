"""Second-revision numbers for P1 (p1_r2.json + existing runs) -> macros and tab_strong.tex.

  - XY vs Grover: paired bootstrap CI of the mean P_opt difference (non-significance is not equivalence)
  - offline cost of the fixed angles and the break-even number of disruptions
  - feasible-subspace Grover mixer (capacity preserved by construction) against XY on the development set
  - transfer with the energy scaling switched off or replaced (does the shared scale matter?)
  - stronger per-instance baselines on the held-out instances: best of 5 seeds, warm start with the full
    budget, L-BFGS-B
Called from post_p1.py after post_p1_v2.extend; every claim made in the text is asserted here.
"""
import json

import numpy as np
from scipy.stats import wilcoxon
from post_p1_v2 import sci


def extend(put, work, out):
    v2 = json.loads((work / "p1_v2.json").read_text(encoding="utf-8"))
    ho = json.loads((work / "p1_holdout.json").read_text(encoding="utf-8"))
    r2 = json.loads((work / "p1_r2.json").read_text(encoding="utf-8"))
    R = [r for r in v2["results"] if r["feasible_instance"]]
    rng = np.random.default_rng(11)

    def runs(task):
        return {r["i"]: {x["p"]: x for x in r["runs"]} for r in R if r["task"] == task}

    xy, gm = runs("seed:xy:1.0:0"), runs("grover:1.0")
    ids = sorted(xy)
    # ---- XY vs Grover: paired bootstrap of the mean difference
    lo_hi = {}
    for p in (1, 2, 3, 4):
        d = np.array([xy[i][p]["popt"] - gm[i][p]["popt"] for i in ids])
        bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(5000)]
        lo_hi[p] = (d.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5))
    m, lo, hi = lo_hi[4]
    put("GmDiffFour", f"{m:.3f}")
    put("GmDiffLo", f"{lo:.3f}")
    put("GmDiffHi", f"{hi:.3f}")
    d4 = np.array([xy[i][4]["popt"] - gm[i][4]["popt"] for i in ids])
    put("GmWinsFour", str(int((d4 > 0).sum())))
    put("GmRawP", sci(wilcoxon(d4).pvalue))
    put("GmMedFour", f"{np.median(d4):.3f}")
    assert lo > 0 and wilcoxon(d4).pvalue < 0.05, "text: at p=4 the mean difference favours XY (unadjusted)"
    assert all(lo_hi[p][1] < 0 for p in (2, 3)), "text: at p=2 and 3 the interval includes zero"

    # ---- offline cost of fixed angles and break-even
    dev_train = sum(sum(xy[i][q]["nfev"] for q in (1, 2, 3, 4)) for i in ids)
    cross = len(ids) * len(ids) * 4  # eq. (6): every trained set evaluated on every development instance, 4 depths
    per_inst = float(np.mean([r["trained_cum_nfev"] for r in ho["rows"]
                              if r["kind"] == "xy" and r["alpha"] == 1.0 and r["p"] == 4]))
    put("OffTrain", f"{dev_train:,}")
    put("OffCross", f"{cross:,}")
    put("OffTotal", f"{dev_train + cross:,}")
    put("OffBreakEven", f"{(dev_train + cross) / per_inst:.0f}")

    # ---- feasible-subspace Grover mixer (development set, seed 0, mean objective)
    fg = {r["i"]: {x["p"]: x for x in r["runs"]} for r in r2["rows"] if r["task"] == "feasgm"}
    assert sorted(fg) == ids
    fgp = {p: np.array([fg[i][p]["popt"] for i in ids]) for p in (1, 2, 3, 4)}
    xyp = {p: np.array([xy[i][p]["popt"] for i in ids]) for p in (1, 2, 3, 4)}
    put("FgFour", f"{fgp[4].mean():.3f}")
    put("FgOne", f"{fgp[1].mean():.3f}")
    put("FgWinsFour", str(int((fgp[4] > xyp[4]).sum())))
    put("FgPFour", sci(wilcoxon(fgp[4], xyp[4]).pvalue))
    put("FgFeas", f"{np.mean([fg[i][4]['pfeas'] for i in ids]):.3f}")
    put("FgEvals", f"{np.mean([sum(fg[i][q]['nfev'] for q in (1, 2, 3, 4)) for i in ids]):,.0f}")
    assert abs(np.mean([fg[i][4]["pfeas"] for i in ids]) - 1.0) < 1e-6, "text: feasible-subspace mixer keeps P_feas = 1"
    fg_better = fgp[4].mean() > xyp[4].mean()
    put("FgCompare", "above" if fg_better else "below")

    # ---- transfer under other energy normalisations (held-out instances)
    nt = r2["norm_transfer"]
    H = [r for r in ho["rows"] if r["kind"] == "xy" and r["alpha"] == 1.0 and r["p"] == 4]
    dep_fixed = float(np.mean([r["fixed"] for r in H]))
    dep_trained = float(np.mean([r["trained"] for r in H]))
    for mode, tag in (("none", "None"), ("std", "Std")):
        v = nt[f"{mode}:4"]
        put(f"Norm{tag}Fixed", f"{np.mean(v['new_fixed']):.3f}")
        put(f"Norm{tag}DevTrained", f"{v['dev_trained']:.3f}")
    put("NormDepFixed", f"{dep_fixed:.3f}")
    nf, sf = np.mean(nt["none:4"]["new_fixed"]), np.mean(nt["std:4"]["new_fixed"])
    rows = [f"shift and scale by $\\Delta$ (ours) & {dep_fixed:.3f}\\\\",
            f"shift, no scaling & {nf:.3f}\\\\", f"shift, scale by s.d.\\ of plan energies & {sf:.3f}\\\\"]

    # ---- stronger per-instance baselines on the held-out instances (p = 4)
    def strong(task):
        out_ = {}
        for r in r2["rows"]:
            if r["task"] != task:
                continue
            if task == "cobyla5":
                best = max(r["runs"], key=lambda rr: rr[3]["popt"])
                out_[r["i"]] = (best[3]["popt"], sum(x["nfev"] for rr in r["runs"] for x in rr))
            else:
                out_[r["i"]] = (r["runs"][3]["popt"], sum(x["nfev"] for x in r["runs"]))
        return out_
    hid = sorted({r["i"] for r in H})
    fixed = {r["i"]: r["fixed"] for r in H}
    trained = {r["i"]: r["trained"] for r in H}
    srows = []
    sv = {}
    for task, lab in (("cobyla5", "COBYLA, best of 5 seeds"), ("lbfgs", "L-BFGS-B, 3 starts"),
                      ("warm250", "COBYLA from fixed angles, 250/depth")):
        s = strong(task)
        assert sorted(s) == hid
        pv = np.array([s[i][0] for i in hid])
        ev = np.mean([s[i][1] for i in hid])
        p_ = wilcoxon(pv, np.array([fixed[i] for i in hid])).pvalue
        sv[task] = (pv.mean(), ev, p_, int((pv > np.array([fixed[i] for i in hid])).sum()))
        srows.append(f"{lab} & {pv.mean():.3f} & {ev:,.0f}\\\\")
    put("StrBestFive", f"{sv['cobyla5'][0]:.3f}")
    put("StrBestFiveEv", f"{sv['cobyla5'][1]:,.0f}")
    put("StrBestFiveP", sci(sv["cobyla5"][2]))
    put("StrLbfgs", f"{sv['lbfgs'][0]:.3f}")
    put("StrLbfgsEv", f"{sv['lbfgs'][1]:,.0f}")
    put("StrWarm", f"{sv['warm250'][0]:.3f}")
    put("StrWarmEv", f"{sv['warm250'][1]:,.0f}")
    put("StrWarmP", sci(sv["warm250"][2]))
    put("StrWarmWins", str(sv["warm250"][3]))
    tab = [f"per-instance COBYLA (main study) & {dep_trained:.3f} & {np.mean([r['trained_cum_nfev'] for r in H]):,.0f}\\\\"]
    tab += srows
    tab.append(f"fixed angles (transfer) & {dep_fixed:.3f} & 0\\\\")
    (out / "tab_strong.tex").write_text("\n".join(tab), encoding="utf-8")
    (out / "tab_norm.tex").write_text("\n".join(rows), encoding="utf-8")
    return {"fg": fgp, "xy": xyp, "norm": (dep_fixed, nf, sf), "strong": sv, "dep_trained": dep_trained}
