"""Revision numbers for P1: p1_v2.json, p1_transfer.json, p1_holdout.json -> macros, tables, figures.

Called from post_p1.py (extend) before nums.tex is written. Every qualitative claim the revised text
makes about these experiments is asserted here, so the build fails if the data stop supporting it.
"""
import json
import math

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import wilcoxon

LAB = {("x", 1.0): "X, mean", ("x", 0.1): "X, CVaR", ("xy", 1.0): "XY, mean", ("xy", 0.1): "XY, CVaR",
       ("grover", 1.0): "Grover, mean", ("grover", 0.1): "Grover, CVaR"}


def sci(x):
    """p-value as LaTeX math, e.g. 8.0\\times10^{-6}."""
    if x >= 0.1:
        return f"{x:.2f}"
    if x >= 0.01:
        return f"{x:.3f}"
    e = math.floor(math.log10(x))
    return f"{x / 10 ** e:.1f}\\times10^{{{e}}}"


def holm(ps):
    order = np.argsort(ps)
    adj, run = np.empty(len(ps)), 0.0
    for r, k in enumerate(order):
        run = max(run, min(1.0, (len(ps) - r) * ps[k]))
        adj[k] = run
    return adj


def boot_ci(x, rng, n=10000):
    m = rng.choice(np.asarray(x), size=(n, len(x)), replace=True).mean(axis=1)
    return np.percentile(m, [2.5, 97.5])


def extend(put, work, out, j):
    v2 = json.loads((work / "p1_v2.json").read_text(encoding="utf-8"))
    tr = json.loads((work / "p1_transfer.json").read_text(encoding="utf-8"))
    ho = json.loads((work / "p1_holdout.json").read_text(encoding="utf-8"))
    R = [r for r in v2["results"] if r["feasible_instance"]]
    rng = np.random.default_rng(7)

    def runs(task):
        return {r["i"]: {x["p"]: x for x in r["runs"]} for r in R if r["task"] == task}

    # seed 0 of the revision run reproduces the published p1.json numbers exactly
    old = {(x["i"], x["kind"], x["alpha"], x["p"]): x["popt"] for x in j["rows"]}
    for k, a in (("x", 1.0), ("xy", 1.0), ("xy", 0.1)):
        for i, rr in runs(f"seed:{k}:{a}:0").items():
            for p, x in rr.items():
                assert abs(x["popt"] - old[(i, k, a, p)]) < 1e-9, "seed 0 reproduces p1.json"

    S = v2["seeds"]
    var = {("x", 1.0): [runs(f"seed:x:1.0:{s}") for s in range(S)],
           ("xy", 1.0): [runs(f"seed:xy:1.0:{s}") for s in range(S)],
           ("xy", 0.1): [runs(f"seed:xy:0.1:{s}") for s in range(S)],
           ("grover", 1.0): [runs("grover:1.0")], ("grover", 0.1): [runs("grover:0.1")]}
    ids = sorted(var[("xy", 1.0)][0])
    pop, feas, nfev = {}, {}, {}
    for key, seeds in var.items():
        for p in (1, 2, 3, 4):
            pop[(key, p)] = np.array([[s[i][p]["popt"] for i in ids] for s in seeds])
            feas[(key, p)] = np.array([[s[i][p]["pfeas"] for i in ids] for s in seeds])
            nfev[(key, p)] = np.array([[sum(s[i][q]["nfev"] for q in range(1, p + 1)) for i in ids] for s in seeds])
    put("NSeeds", str(S))
    put("NPaired", str(len(ids)))

    # Table: mixers and objectives at p = 4
    rows = []
    for key in (("x", 1.0), ("xy", 1.0), ("xy", 0.1), ("grover", 1.0), ("grover", 0.1)):
        P = pop[(key, 4)]
        lo, hi = boot_ci(P[0], rng)
        seed_mean = P.mean(axis=1)
        sm = f"{seed_mean.mean():.3f} $\\pm$ {seed_mean.std(ddof=1):.3f}" if P.shape[0] > 1 else "--"
        succ = 100 * np.mean(1 - (1 - P[0]) ** 32)
        rows.append(f"{LAB[key]} & {P[0].mean():.3f} & {lo:.3f}--{hi:.3f} & {sm} & {feas[(key, 4)][0].mean():.3f} & "
                    f"{succ:.1f} & {nfev[(key, 4)][0].mean():.0f}\\\\")
    (out / "tab_mixers.tex").write_text("\n".join(rows), encoding="utf-8")
    xs = pop[(("xy", 1.0), 4)].mean(axis=1)
    put("SeedXYMean", f"{xs.mean():.3f}")
    put("SeedXYSd", f"{xs.std(ddof=1):.3f}")
    put("SeedXYMin", f"{xs.min():.3f}")
    put("SeedXYMax", f"{xs.max():.3f}")
    xx = pop[(("x", 1.0), 4)].mean(axis=1)
    put("SeedXMin", f"{xx.min():.3f}")
    put("SeedXMax", f"{xx.max():.3f}")
    put("GMMeanFour", f"{pop[(('grover', 1.0), 4)][0].mean():.3f}")
    put("GMCvarFour", f"{pop[(('grover', 0.1), 4)][0].mean():.3f}")
    put("GMFeasFour", f"{feas[(('grover', 1.0), 4)][0].mean():.3f}")
    for p in (1, 2, 3, 4):
        assert all(pop[(("xy", 1.0), p)][s].mean() > pop[(("x", 1.0), p)][s].mean() for s in range(S)), \
            "text: XY ahead of X for every optimiser seed and depth"

    # paired Wilcoxon signed-rank tests on the published (seed 0) runs, Holm over the four depths
    tests = {}
    for name, A, B in (("XYvX", ("xy", 1.0), ("x", 1.0)), ("XYvGM", ("xy", 1.0), ("grover", 1.0))):
        ps = np.array([wilcoxon(pop[(A, p)][0], pop[(B, p)][0]).pvalue for p in (1, 2, 3, 4)])
        wins = [int(np.sum(pop[(A, p)][0] > pop[(B, p)][0])) for p in (1, 2, 3, 4)]
        tests[name] = (holm(ps), wins)
        put(f"St{name}MaxP", sci(holm(ps).max()))
        put(f"St{name}MinP", sci(holm(ps).min()))
        put(f"St{name}WinsMin", str(min(wins)))
        put(f"St{name}WinsMax", str(max(wins)))
    assert tests["XYvX"][0].max() < 1e-4 and min(tests["XYvX"][1]) >= 25, "text: XY beats X at every depth"
    assert tests["XYvGM"][0].min() > 0.05, "text: XY vs Grover not significant at any depth after Holm"
    assert pop[(("xy", 1.0), 4)][0].mean() > pop[(("grover", 1.0), 4)][0].mean(), "text: XY mean above Grover"
    succ = lambda key: np.mean(1 - (1 - pop[(key, 4)][0]) ** 32)
    assert succ(("grover", 1.0)) > succ(("xy", 1.0)), "text: Grover success@32 above XY/mean"
    assert pop[(("grover", 1.0), 4)][0].min() > pop[(("xy", 1.0), 4)][0].min() and \
        pop[(("grover", 1.0), 4)][0].std() < pop[(("xy", 1.0), 4)][0].std(), "text: Grover spreads more evenly"

    # penalty sweep for the X mixer (lambda = 1 is the main run)
    prow, pen = [], {}
    exact_main = 100 * np.mean([r["qubo_exact"] for r in R if r["task"] == "exact"])
    for lam in (0.25, 0.5, 1.0, 2.0):
        rr = var[("x", 1.0)][0] if lam == 1.0 else runs(f"penalty:{lam}")
        po = np.mean([rr[i][4]["popt"] for i in ids])
        pf = np.mean([rr[i][4]["pfeas"] for i in ids])
        pen[lam] = (po, pf)
        prow.append(f"{lam:g} & {po:.3f} & {pf:.3f}\\\\")
    (out / "tab_penalty.tex").write_text("\n".join(prow), encoding="utf-8")
    best_lam = max(pen, key=lambda k: pen[k][0])
    put("PenBestLam", f"{best_lam:g}")
    put("PenBestPopt", f"{pen[best_lam][0]:.3f}")
    put("PenBestFeas", f"{pen[best_lam][1]:.3f}")
    put("PenGain", f"{pen[best_lam][0] / pen[1.0][0]:.1f}")
    assert best_lam < 1.0, "text: a smaller penalty helps the X mixer"
    assert pen[best_lam][0] < 0.6 * pop[(("xy", 1.0), 4)][0].mean(), "text: tuned X stays well below XY"
    assert all(abs(100 * np.mean([r["qubo_exact"] for r in R if r["task"] == f"penalty:{l}"]) - exact_main) < 1e-9
               for l in (0.25, 0.5, 2.0)), "text: the minimiser does not depend on the penalty weight here"

    # tuned simulated annealing; encoding exactness
    sa = [r for r in R if r["task"] == "sa"]
    put("SATunedOpt", f"{100 * np.mean([r['sa_opt'] for r in sa]):.1f}")
    put("SATunedFeas", f"{100 * np.mean([r['sa_feas'] for r in sa]):.1f}")
    put("SATunedMs", f"{np.mean([r['sa_ms'] for r in sa]):.0f}")
    ex = [r for r in R if r["task"] == "exact"]
    assert not any(r["zero_eq_feas"] for r in ex), "text: every instance has an infeasible zero-penalty plan"
    put("ZeroPenInfeasAll", str(len(ex)))

    # leave-one-out transfer on the development instances
    T = tr["rows"]
    tf = {}
    for k, a in (("xy", 1.0), ("xy", 0.1), ("x", 1.0)):
        for p in (1, 2, 3, 4):
            rr = [r for r in T if r["kind"] == k and r["alpha"] == a and r["p"] == p]
            tf[(k, a, p)] = {f: float(np.mean([r[f] for r in rr])) for f in ("trained", "donor", "median", "ft")}
            tf[(k, a, p)]["donors"] = sorted({r["donor_id"] for r in rr})
    best5 = np.max(pop[(("xy", 1.0), 4)], axis=0)
    cum5 = nfev[(("xy", 1.0), 4)].sum(axis=0)
    put("LooDonorFour", f"{tf[('xy', 1.0, 4)]['donor']:.3f}")
    put("LooTrainedFour", f"{tf[('xy', 1.0, 4)]['trained']:.3f}")
    put("LooMedianFour", f"{tf[('xy', 1.0, 4)]['median']:.3f}")
    put("LooNDonors", str(len(tf[("xy", 1.0, 4)]["donors"])))
    put("BestFiveFour", f"{best5.mean():.3f}")
    put("BestFiveEvals", f"{cum5.mean():,.0f}")
    assert tf[("xy", 1.0, 4)]["median"] < 0.01, "text: median angles fail"
    assert abs(tf[("xy", 1.0, 4)]["donor"] - best5.mean()) < 0.02, "text: LOO transfer matches best-of-5 training"

    # held-out test on 30 new instances
    H = ho["rows"]
    hrow, hv = [], {}
    for k, a in (("xy", 1.0), ("xy", 0.1), ("x", 1.0)):
        for p in (1, 2, 3, 4):
            rr = [r for r in H if r["kind"] == k and r["alpha"] == a and r["p"] == p]
            f = np.array([r["fixed"] for r in rr])
            t = np.array([r["trained"] for r in rr])
            v = {"trained": t.mean(), "fixed": f.mean(), "ft": np.mean([r["ft"] for r in rr]),
                 "cum": np.mean([r["trained_cum_nfev"] for r in rr]), "wins": int(np.sum(f > t)),
                 "p": wilcoxon(f, t).pvalue, "succ_f": 100 * np.mean(1 - (1 - f) ** 32),
                 "succ_t": 100 * np.mean(1 - (1 - t) ** 32), "n": len(rr)}
            hv[(k, a, p)] = v
            if (k, a) != ("x", 1.0) or p == 4:
                hrow.append(f"{LAB[(k, a)]} & {p} & {v['trained']:.3f} & {v['cum']:,.0f} & {v['fixed']:.3f} & "
                            f"{v['ft']:.3f} & {v['succ_t']:.1f} & {v['succ_f']:.1f}\\\\")
    (out / "tab_transfer.tex").write_text("\n".join(hrow), encoding="utf-8")
    h4, c4, x4 = hv[("xy", 1.0, 4)], hv[("xy", 0.1, 4)], hv[("x", 1.0, 4)]
    put("HoN", str(ho["n_new"]))
    put("HoFt", str(ho["ft_budget"]))
    put("HoTrainedFour", f"{h4['trained']:.3f}")
    put("HoFixedFour", f"{h4['fixed']:.3f}")
    put("HoFtFour", f"{h4['ft']:.3f}")
    put("HoCumFour", f"{h4['cum']:,.0f}")
    put("HoWinsFour", str(h4["wins"]))
    put("HoPFour", sci(h4["p"]))
    put("HoRatioFour", f"{h4['fixed'] / h4['trained']:.1f}")
    put("HoSuccFixed", f"{h4['succ_f']:.2f}")
    put("HoSuccTrained", f"{h4['succ_t']:.1f}")
    put("HoCvarFixed", f"{c4['fixed']:.3f}")
    put("HoCvarTrained", f"{c4['trained']:.3f}")
    put("HoCvarWins", str(c4["wins"]))
    put("HoXFixed", f"{x4['fixed']:.3f}")
    put("HoXTrained", f"{x4['trained']:.3f}")
    put("HoUniform", f"{np.mean([r['uniform'] for r in H]):.4f}")
    put("HoFixedOverX", f"{h4['fixed'] / x4['trained']:.1f}")
    assert h4["p"] < 1e-3 and c4["p"] < 1e-3, "text: fixed angles beat per-instance training on new instances"
    assert all(hv[("xy", 1.0, p)]["fixed"] > hv[("xy", 1.0, p)]["trained"] for p in (1, 2, 3, 4)), \
        "text: fixed > trained at every depth (XY, mean)"
    assert h4["ft"] > h4["fixed"], "text: fine-tuning adds a little"
    assert x4["fixed"] < 0.2 * h4["fixed"], "text: transfer does not rescue the X mixer"

    # cross-network transfer: OSM road graphs of six cities (exp_p1_cities.py)
    cj = json.loads((work / "p1_cities.json").read_text(encoding="utf-8"))
    CR = [r for r in cj["rows"] if r["feasible_instance"]]
    put("CityN", str(len(CR)))
    put("CityAll", str(len(cj["rows"])))
    put("CityNCities", str(len(cj["cities"])))
    put("CityBinding", str(sum(r["binding"] for r in CR)))
    put("CityUniform", f"{np.mean([r['uniform'] for r in CR]):.4f}")
    put("CityQuboExact", f"{100 * np.mean([r['qubo_exact'] for r in CR]):.0f}")
    put("CityMeanCost", f"{np.mean([r['mean_cost'] for r in CR]):.0f}")
    crow, cv = [], {}
    s32 = lambda x: 1 - (1 - np.asarray(x)) ** 32
    for (k, a), lab in ((("xy", 1.0), "XY, mean"), (("xy", 0.1), "XY, CVaR"), (("x", 1.0), "X, mean")):
        f = np.array([r[f"{k}:{a}:4"]["fixed"] for r in CR])
        t = np.array([r[f"{k}:{a}:4"]["trained"] for r in CR])
        ev = np.mean([r[f"{k}:{a}:4"]["trained_cum_nfev"] for r in CR])
        v = {"f": f.mean(), "t": t.mean(), "p": wilcoxon(f, t).pvalue, "sf": 100 * s32(f).mean(),
             "st": 100 * s32(t).mean(), "ps": wilcoxon(s32(f), s32(t)).pvalue, "ev": ev,
             "tmin_n": int(np.sum(t < 0.01)), "fmin_n": int(np.sum(f < 0.01))}
        cv[(k, a)] = v
        hv4 = hv[(k, a, 4)]
        crow.append(f"{lab} & {hv4['trained']:.3f} & {hv4['fixed']:.3f} & {v['t']:.3f} & {v['f']:.3f} & "
                    f"{v['st']:.1f} & {v['sf']:.1f}\\\\")
    (out / "tab_cities.tex").write_text("\n".join(crow), encoding="utf-8")
    c1, c2, c3 = cv[("xy", 1.0)], cv[("xy", 0.1)], cv[("x", 1.0)]
    put("CityFixed", f"{c1['f']:.3f}")
    put("CityTrained", f"{c1['t']:.3f}")
    put("CityP", f"{c1['p']:.2f}")
    put("CitySuccFixed", f"{c1['sf']:.1f}")
    put("CitySuccTrained", f"{c1['st']:.1f}")
    put("CitySuccP", sci(c1["ps"]))
    put("CityTrainedLow", str(c1["tmin_n"]))
    put("CityFixedLow", str(c1["fmin_n"]))
    put("CityEvals", f"{c1['ev']:,.0f}")
    put("CityCvarFixed", f"{c2['f']:.3f}")
    put("CityCvarTrained", f"{c2['t']:.3f}")
    put("CityCvarP", sci(c2["p"]))
    put("CityXFixed", f"{c3['f']:.3f}")
    put("CityXTrained", f"{c3['t']:.3f}")
    assert c1["p"] > 0.05, "text: on city graphs fixed and trained XY/mean P_opt do not differ significantly"
    assert c1["sf"] > c1["st"] + 10 and c1["ps"] < 0.05, "text: fixed angles raise success@32 on city graphs"
    assert c1["tmin_n"] > c1["fmin_n"], "text: per-instance training leaves more near-zero instances"
    assert c2["f"] > c2["t"] and c2["p"] < 1e-3, "text: CVaR angles transfer to city graphs"
    assert c1["f"] > 4 * max(c3["f"], c3["t"]), "text: XY far above X on city graphs"

    # Fig.: held-out transfer against depth
    fig, ax = plt.subplots(figsize=(3.45, 2.0))
    ps = [1, 2, 3, 4]
    ax.plot(ps, [hv[("xy", 1.0, p)]["fixed"] for p in ps], "s-", color="0.05", ms=3, lw=0.9,
            label="XY, fixed angles (0 evals)")
    ax.plot(ps, [hv[("xy", 1.0, p)]["ft"] for p in ps], "^-.", color="0.35", ms=3, lw=0.9,
            label=f"XY, fixed + {ho['ft_budget']} evals")
    ax.plot(ps, [hv[("xy", 1.0, p)]["trained"] for p in ps], "o--", color="0.55", ms=3, lw=0.9,
            label="XY, trained per instance")
    ax.plot(ps, [hv[("x", 1.0, p)]["trained"] for p in ps], ":", color="0.6", lw=0.9, label="X, trained per instance")
    ax.set_xlabel("depth $p$")
    ax.set_ylabel("$P_{\\mathrm{opt}}$, new instances")
    ax.set_xticks(ps)
    ax.grid(lw=0.3)
    fig.legend(*ax.get_legend_handles_labels(), fontsize=5.8, frameon=False, loc="upper center", ncol=2,
               columnspacing=1.0)
    fig.tight_layout(pad=0.3, rect=(0, 0, 1, 0.80))
    fig.savefig(out / "fig_transfer.pdf")
    plt.close(fig)
    return pop, feas
