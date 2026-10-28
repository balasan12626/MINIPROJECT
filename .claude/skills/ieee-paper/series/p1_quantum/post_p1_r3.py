"""Third-revision numbers for P1 -> macros, tab_select.tex, tab_gap.tex, tab_cities.tex (per city), tab_mixers.tex.

Reads only stored results: p1_r3.json, p1_r3_cities.json, p1_r3_cand.json (exp_p1_r3.py phases select, cities,
cand), p1_v2.json, p1_r2.json, p1_holdout.json, p1_cities.json, p1.json.
  - M1: theta* chosen by mean P_opt (needs development optima), by mean scaled energy and by mean CVaR
  - M5: Holm correction per family, median paired differences, per-city table and sign test, two-level
        bootstrap (instances, then optimiser seeds) for the seeded variants
  - M6: expected optimality gap of the cheapest verified-feasible plan among N samples
  - M4: SA with one-hot moves, uniform sampling over feasible plans
  - M7: CNOT counts per layer (analytic, standard decompositions)
Called from post_p1.py; every claim the text makes about these numbers is asserted here.
"""
import json

import numpy as np
from scipy.stats import binomtest, spearmanr, wilcoxon

RULES = ("popt", "energy", "cvar")
NSH = 32


from post_p1_v2 import sci  # noqa: E402  one p-value format for the whole paper


def holm(ps):
    ps = np.asarray(ps, dtype=float)
    order = np.argsort(ps)
    adj, run = np.empty(len(ps)), 0.0
    for r, k in enumerate(order):
        run = max(run, min(1.0, (len(ps) - r) * ps[k]))
        adj[k] = run
    return adj


def s32(x):
    return 100.0 * float(np.mean(1.0 - (1.0 - np.asarray(x)) ** NSH))


def extend(put, work, out):
    r3 = json.loads((work / "p1_r3.json").read_text(encoding="utf-8"))
    rc = json.loads((work / "p1_r3_cities.json").read_text(encoding="utf-8"))["rows"]
    cand = json.loads((work / "p1_r3_cand.json").read_text(encoding="utf-8"))["cand_heldout_popt"]
    r2 = json.loads((work / "p1_r2.json").read_text(encoding="utf-8"))
    v2 = json.loads((work / "p1_v2.json").read_text(encoding="utf-8"))
    p1 = json.loads((work / "p1.json").read_text(encoding="utf-8"))
    nid, did = r3["new_ids"], r3["dev_ids"]
    rng = np.random.default_rng(13)
    R = {}

    # ------------------------------------------------------------------ M1: selection rules on held-out instances
    def trained(v):
        return np.array([r3["new_trained"][f"{v}:4:{i}"] for i in nid])

    def fixed(v, rule):
        return np.array(r3["variants"][v]["4"]["new"][rule]["popt"])

    tests = [("xy:1.0", "popt"), ("xy:1.0", "energy"), ("xy:1.0", "cvar"), ("xy:0.1", "popt"), ("xy:0.1", "cvar"),
             ("x:1.0", "popt"), ("x:1.0", "energy")]
    raw = [wilcoxon(fixed(v, r), trained(v)).pvalue for v, r in tests]
    adj = dict(zip(tests, holm(raw)))
    put("SelFamily", str(len(tests)))
    b5 = {x["i"]: x for x in r3["best5"]["new"]}
    b5d = r3["best5"]["dev"]
    b5_new = np.array([b5[i]["popt"][int(np.argmin(b5[i]["energy"]))] for i in nid])
    b5_dev = np.array([x["popt"][int(np.argmin(x["energy"]))] for x in b5d])
    b5_ev = np.mean([sum(b5[i]["nfev"]) for i in nid])
    seed0 = np.array([b5[i]["popt"][0] for i in nid])
    assert np.allclose(seed0, trained("xy:1.0"), atol=1e-9), "best-of-5 seed 0 is the per-instance run"
    lb = {r["i"]: r["runs"][3]["popt"] for r in r2["rows"] if r["task"] == "lbfgs"}
    lb = np.array([lb[i] for i in nid])
    lab = {"xy:1.0": "XY, mean", "xy:0.1": "XY, CVaR", "x:1.0": "X, mean"}
    rname = {"popt": "fixed, max.\\ $P_{\\mathrm{opt}}$", "energy": "fixed, min.\\ energy",
             "cvar": "fixed, min.\\ CVaR"}
    rows = []
    for v in ("xy:1.0", "xy:0.1", "x:1.0"):
        V = r3["variants"][v]["4"]
        t = trained(v)
        rows.append(f"{lab[v]} & per instance & no & {t.mean():.3f} & & & & {np.mean(V['dev_trained']):.3f} & "
                    f"{s32(t):.1f}\\\\")
        if v == "xy:1.0":
            rows.append(f" & best of 5, min.\\ energy & no & {b5_new.mean():.3f} & & & & {b5_dev.mean():.3f} & "
                        f"{s32(b5_new):.1f}\\\\")
            rows.append(f" & L-BFGS-B & no & {lb.mean():.3f} & & & & & {s32(lb):.1f}\\\\")
        for v2_, rule in tests:
            if v2_ != v:
                continue
            f = fixed(v, rule)
            loo = np.mean(V["loo"][rule])
            rows.append(f" & {rname[rule]} & {'yes' if rule == 'popt' else 'no'} & {f.mean():.3f} & "
                        f"{np.median(f - t):+.3f} & {int((f > t).sum())} & ${sci(adj[(v, rule)])}$ & {loo:.3f} & "
                        f"{s32(f):.1f}\\\\")
            R[(v, rule)] = dict(f=f, t=t, p=adj[(v, rule)], wins=int((f > t).sum()), med=float(np.median(f - t)),
                                loo=float(loo), dev_tr=float(np.mean(V["dev_trained"])))
        rows.append("\\addlinespace[1pt]")
    (out / "tab_select.tex").write_text("\n".join(rows[:-1]), encoding="utf-8")
    tag = {("xy:1.0", "popt"): "Popt", ("xy:1.0", "energy"): "En", ("xy:1.0", "cvar"): "Cv",
           ("xy:0.1", "popt"): "CvarPopt", ("xy:0.1", "cvar"): "CvarCv", ("x:1.0", "popt"): "XPopt",
           ("x:1.0", "energy"): "XEn"}
    for k, tg in tag.items():
        x = R[k]
        put(f"Sel{tg}", f"{x['f'].mean():.3f}")
        put(f"Sel{tg}P", sci(x["p"]))
        put(f"Sel{tg}Wins", str(x["wins"]))
        put(f"Sel{tg}Med", f"{x['med']:.3f}")
        put(f"Sel{tg}Loo", f"{x['loo']:.3f}")
        put(f"Sel{tg}Succ", f"{s32(x['f']):.1f}")
    put("SelTrained", f"{trained('xy:1.0').mean():.3f}")
    put("SelDevTrained", f"{R[('xy:1.0', 'popt')]['dev_tr']:.3f}")
    put("SelCvarTrained", f"{trained('xy:0.1').mean():.3f}")
    put("SelCvarDevTrained", f"{R[('xy:0.1', 'cvar')]['dev_tr']:.3f}")
    put("SelBestFive", f"{b5_new.mean():.3f}")
    put("SelBestFiveDev", f"{b5_dev.mean():.3f}")
    put("SelBestFiveEv", f"{b5_ev:,.0f}")
    put("SelLbfgs", f"{lb.mean():.3f}")
    put("SelSuccTrained", f"{s32(trained('xy:1.0')):.1f}")
    a, e, c = R[("xy:1.0", "popt")], R[("xy:1.0", "energy")], R[("xy:1.0", "cvar")]
    assert a["p"] < 0.01 and e["p"] < 0.05 and a["f"].mean() > e["f"].mean() > c["f"].mean() > a["t"].mean(), \
        "text: all three rules beat per-instance training on held-out instances, the P_opt rule most"
    assert e["f"].mean() > b5_new.mean() and e["f"].mean() > lb.mean(), "text: energy rule above best-of-5 and L-BFGS-B"
    assert e["loo"] < 0.5 * e["dev_tr"] and c["loo"] < c["dev_tr"] and a["loo"] > a["dev_tr"], \
        "text: oracle-free rules fall below per-instance training in leave-one-out, the P_opt rule does not"
    cc = R[("xy:0.1", "cvar")]
    assert cc["p"] < 1e-3 and cc["loo"] < cc["dev_tr"], "text: CVaR rule for CVaR angles: held-out gain, LOO loss"
    assert R[("x:1.0", "popt")]["f"].mean() < 0.2 * a["f"].mean(), "text: transfer does not rescue X"
    # energy reached by per-instance training versus the fixed angles (training minimises energy, not P_opt)
    te = np.array([b5[i]["energy"][0] for i in nid])
    fe = np.array(r3["variants"]["xy:1.0"]["4"]["new"]["popt"]["energy"])
    put("EnTrained", f"{te.mean():.3f}")
    put("EnFixed", f"{fe.mean():.3f}")
    put("EnLower", str(int((te < fe).sum())))
    assert te.mean() < fe.mean() and (te < fe).sum() >= 20, "text: training reaches lower energy than fixed angles"
    V = r3["variants"]["xy:1.0"]["4"]
    rho_ep = spearmanr(V["cand_dev_popt"], -np.array(V["cand_dev_energy"])).statistic
    rho_dh = spearmanr(V["cand_dev_popt"], cand).statistic
    put("RhoEnPopt", f"{rho_ep:.2f}")
    put("RhoDevHeld", f"{rho_dh:.2f}")
    cand = np.array(cand)
    put("CandBeat", str(int((cand > trained("xy:1.0").mean()).sum())))
    put("CandN", str(len(cand)))
    put("CandMedian", f"{np.median(cand):.3f}")
    assert rho_dh > 0.9 and rho_ep < 0.5, "text: dev P_opt predicts held-out P_opt; energy is a weak proxy"
    # binding vs non-binding held-out instances
    bind = np.array([r3["new_binding"][str(i)] for i in nid])
    put("HoNBind", str(int(bind.sum())))
    put("HoBindFixed", f"{a['f'][bind].mean():.3f}")
    put("HoBindTrained", f"{a['t'][bind].mean():.3f}")
    put("HoNonBindFixed", f"{a['f'][~bind].mean():.3f}")
    put("HoNonBindTrained", f"{a['t'][~bind].mean():.3f}")
    assert a["t"][bind].mean() < 0.6 * a["t"][~bind].mean(), "text: per-instance training drops on binding instances"
    assert abs(a["f"][bind].mean() - a["f"][~bind].mean()) < 0.05, "text: fixed angles about equal in both groups"
    assert (a["f"][bind] - a["t"][bind]).mean() > 2 * (a["f"][~bind] - a["t"][~bind]).mean(), \
        "text: most of the gain comes from capacity-binding instances"

    # ------------------------------------------------------------------ M6: best verified plan among N samples
    base = {x["i"]: x for x in r3["new_baselines"]}
    gsrc = {"uniform one-hot": [base[i]["uni_onehot"] for i in nid],
            "uniform feasible": [base[i]["uni_feas"] for i in nid],
            "XY, per instance": [b5[i]["gaps_seed0"] for i in nid],
            "XY, fixed (max.\\ $P_{\\mathrm{opt}}$)": V["new"]["popt"]["gaps"],
            "XY, fixed (min.\\ energy)": V["new"]["energy"]["gaps"]}
    grows, G = [], {}
    for name, L in gsrc.items():
        cells = []
        for N in ("8", "32", "128"):
            gap = 100 * np.mean([x[N]["gap"] for x in L])
            po = 100 * np.mean([x[N]["p_opt"] for x in L])
            G[(name, N)] = (gap, po)
            cells.append(f"{gap:.2f} & {po:.1f}")
        grows.append(f"{name} & " + " & ".join(cells) + "\\\\")
    (out / "tab_gap.tex").write_text("\n".join(grows), encoding="utf-8")
    pf8 = {k: min(x["8"]["p_feas"] for x in L) for k, L in gsrc.items()}
    print("min P(feasible among 8):", {k: round(v, 4) for k, v in pf8.items()})
    pf32 = min(x["32"]["p_feas"] for k, L in gsrc.items() if k != "uniform one-hot" for x in L)
    put("PfeasThirtyTwoMin", f"{100 * pf32:.1f}")
    assert pf32 > 0.99, "text: with 32 samples the XY samplers draw a feasible plan in more than 99 % of cases"
    fx, tr_, un = "XY, fixed (max.\\ $P_{\\mathrm{opt}}$)", "XY, per instance", "uniform one-hot"
    put("GapUniEight", f"{G[(un, '8')][0]:.1f}")
    put("GapTrEight", f"{G[(tr_, '8')][0]:.2f}")
    put("GapFxEight", f"{G[(fx, '8')][0]:.2f}")
    put("GapTrBig", f"{G[(tr_, '128')][0]:.2f}")
    put("GapFxBig", f"{G[(fx, '128')][0]:.2f}")
    en = "XY, fixed (min.\\ energy)"
    put("GapEnBig", f"{G[(en, '128')][0]:.2f}")
    assert G[(fx, "8")][0] < G[(tr_, "8")][0] < G[(un, "8")][0], "text: gap ordering at N = 8"
    assert G[(tr_, "128")][0] < 1.0, "text: with 128 samples per-instance training is within 1 % of the optimum"

    # ------------------------------------------------------------------ M4: one-hot SA, uniform over feasible plans
    sa = r3["sa_dev"]
    put("SAohOpt", f"{100 * np.mean([x['oh_opt'] for x in sa]):.1f}")
    put("SAohFeas", f"{100 * np.mean([x['oh_feas'] for x in sa]):.1f}")
    put("SAohMs", f"{np.mean([x['oh_ms'] for x in sa]):.0f}")
    put("SAbfVer", f"{100 * np.mean([x['bf_ver_opt'] for x in sa]):.0f}")
    put("SAohVer", f"{100 * np.mean([x['oh_ver_opt'] for x in sa]):.0f}")
    assert all(x["oh_ver_opt"] and x["bf_ver_opt"] for x in sa), "text: with a verifier both SA variants always find the optimum"
    uf = np.mean([x["uni_feas_popt"] for x in sa])
    put("UniFeas", f"{uf:.3f}")
    R["unifeas"] = uf

    # ------------------------------------------------------------------ M5: cities, per city and sign test
    cities = []
    for r in rc:
        if r["city"] not in cities:
            cities.append(r["city"])
    crow, diffs_p, diffs_e = [], [], []
    for cname in cities:
        rr = [r for r in rc if r["city"] == cname]
        t = np.array([r["xy:1.0:trained"] for r in rr])
        fp = np.array([r["xy:1.0:popt"] for r in rr])
        fe_ = np.array([r["xy:1.0:energy"] for r in rr])
        diffs_p.append(fp.mean() - t.mean())
        diffs_e.append(fe_.mean() - t.mean())
        crow.append(f"{cname.capitalize()} & {len(rr)} & {t.mean():.3f} & {fp.mean():.3f} & {fe_.mean():.3f} & "
                    f"{s32(t):.0f} & {s32(fp):.0f} & {s32(fe_):.0f}\\\\")
    t = np.array([r["xy:1.0:trained"] for r in rc])
    fp = np.array([r["xy:1.0:popt"] for r in rc])
    fe_ = np.array([r["xy:1.0:energy"] for r in rc])
    crow.append("\\midrule")
    crow.append(f"All & {len(rc)} & {t.mean():.3f} & {fp.mean():.3f} & {fe_.mean():.3f} & {s32(t):.0f} & "
                f"{s32(fp):.0f} & {s32(fe_):.0f}\\\\")
    (out / "tab_cities.tex").write_text("\n".join(crow), encoding="utf-8")
    succ = lambda x: 1 - (1 - np.asarray(x)) ** NSH  # noqa: E731
    craw = [wilcoxon(fp, t).pvalue, wilcoxon(fe_, t).pvalue, wilcoxon(succ(fp), succ(t)).pvalue,
            wilcoxon(succ(fe_), succ(t)).pvalue]
    cadj = holm(craw)
    put("CityPHolm", sci(cadj[0]))
    put("CityEnPHolm", sci(cadj[1]))
    put("CitySuccPHolm", sci(cadj[2]))
    put("CityEnSuccPHolm", sci(cadj[3]))
    put("CityEnFixed", f"{fe_.mean():.3f}")
    put("CityEnSucc", f"{s32(fe_):.1f}")
    put("CityMedDiff", f"{np.median(fp - t):+.3f}")
    npos = int(sum(d > 0 for d in diffs_p))
    put("CityPos", str(npos))
    put("CityEnPos", str(int(sum(d > 0 for d in diffs_e))))
    put("CitySignP", f"{binomtest(npos, len(cities)).pvalue:.2f}")
    put("CitySignEnP", f"{binomtest(int(sum(d > 0 for d in diffs_e)), len(cities)).pvalue:.2f}")
    put("CityK", str(len(cities)))
    sz = json.loads((work / "p1_size.json").read_text(encoding="utf-8"))["size"]
    for G_, tg in ((5, "Five"), (6, "Six")):
        g_ = [r for r in sz if r["G"] == G_ and r["alpha"] == 1.0 and r["feasible_instance"]]
        put(f"Sz{tg}Ratio", f"{min(r['fixed_p4'] for r in g_) / np.mean([r['uniform'] for r in g_]):.0f}")
    sp = sum(s32([r["xy:1.0:popt"] for r in rc if r["city"] == c_]) > s32([r["xy:1.0:trained"] for r in rc if r["city"] == c_])
             for c_ in cities)
    put("CitySuccPos", str(int(sp)))
    put("CitySuccSignP", f"{binomtest(int(sp), len(cities)).pvalue:.2f}")
    assert cadj[0] > 0.05 and cadj[1] > 0.05, "text: fixed P_opt not significantly different from training on cities"
    assert cadj[2] < 0.05 and cadj[3] < 0.05, "text: success@32 higher with fixed angles after Holm"
    assert binomtest(npos, len(cities)).pvalue > 0.05, "text: per-city sign test not significant"
    R["city_succ_fixed"] = s32(fp)

    # ------------------------------------------------------------------ mixer table: two-level bootstrap and CNOTs
    res = [r for r in v2["results"] if r["feasible_instance"]]

    def runs(task):
        return {r["i"]: {x["p"]: x for x in r["runs"]} for r in res if r["task"] == task}
    ids = sorted(runs("seed:xy:1.0:0"))
    ov = []
    import sys
    from pathlib import Path
    sys.path[:0] = [str(Path(__file__).resolve().parent.parent)]
    import qaoa_sim as Q
    from exp_p1 import disrupted
    for i in ids:
        ov.append(len(Q.overload_pairs(Q.instance_from_engine(disrupted(42 + 17 * i), 4))))
    ov = float(np.mean(ov))
    G4, n = 4, 12
    w_cnot = 3 * G4  # W_3 per group: one controlled-H (1 CNOT) and two CNOTs, checked in exp notes
    mcp = 2 * (n - 2) * 6 + 2  # C^{n-1}-phase with n-2 ancillas: 2(n-2) Toffolis (6 CNOTs) + one controlled phase
    cn = {"x": 2 * (n + ov), "xy": 2 * ov + 2 * n, "grover": 2 * ov + 2 * w_cnot + mcp}
    put("CnotX", f"{cn['x']:.0f}")
    put("CnotXY", f"{cn['xy']:.0f}")
    put("CnotGM", f"{cn['grover']:.0f}")
    put("CnotW", str(w_cnot))
    put("CnotMCP", str(mcp))
    put("NAnc", str(n - 2))
    fg = {r["i"]: {x["p"]: x for x in r["runs"]} for r in r2["rows"] if r["task"] == "feasgm"}
    var = [(("x", 1.0), "X, mean", [runs(f"seed:x:1.0:{s}") for s in range(5)], cn["x"]),
           (("xy", 1.0), "XY, mean", [runs(f"seed:xy:1.0:{s}") for s in range(5)], cn["xy"]),
           (("xy", 0.1), "XY, CVaR", [runs(f"seed:xy:0.1:{s}") for s in range(5)], cn["xy"]),
           (("grover", 1.0), "Grover, mean", [runs("grover:1.0")], cn["grover"]),
           (("grover", 0.1), "Grover, CVaR", [runs("grover:0.1")], cn["grover"]),
           (("fg", 1.0), "Feasible subspace", [fg], None)]
    mrows = []
    for key, name, seeds, c in var:
        P = np.array([[s[i][4]["popt"] for i in ids] for s in seeds])
        F = np.array([[s[i][4]["pfeas"] for i in ids] for s in seeds])
        E = np.array([[sum(s[i][q]["nfev"] for q in (1, 2, 3, 4)) for i in ids] for s in seeds])
        B = 10000
        ii = rng.integers(0, len(ids), (B, len(ids)))
        ss = rng.integers(0, P.shape[0], (B, len(ids)))
        lo, hi = np.percentile(P[ss, ii].mean(axis=1), [2.5, 97.5])
        mrows.append(f"{name} & {P.mean():.3f} & {lo:.3f}--{hi:.3f} & {F.mean():.3f} & {s32(P):.1f} & "
                     f"{E.mean():,.0f} & " + (f"{c:.0f}" if c is not None else "n/a") + "\\\\")
        if key == ("xy", 1.0):
            put("TwoLevLo", f"{lo:.3f}")
            put("TwoLevHi", f"{hi:.3f}")
    (out / "tab_mixers.tex").write_text("\n".join(mrows), encoding="utf-8")
    # literature constants (not results): Sycamore two-qubit XEB Pauli error, isolated / simultaneous, Arute et al.
    put("SycIso", "0.36")
    put("SycSim", "0.62")
    return R
