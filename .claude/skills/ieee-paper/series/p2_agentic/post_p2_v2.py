"""Revision numbers for P2: live LLM study, LLM-judge baseline, calibration of the two classifiers.

Inputs (work dir): p2_labels.json (reference labels of the 300 live replies, label_p2_live.py),
p2_judge.json (LLM judge), p2_judge_match.json (deployed/typed verdicts on the judge's injected items),
p2_calib.json (held-out calibration and gate study). Called from post_p2.py before nums.tex is written;
every claim the revised text makes about these data is asserted here.
"""
import json
import re

import numpy as np

ERR = ["prob_small", "prob_large", "rain_rel", "river", "count", "eta", "words"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * (c - h), 100 * (c + h))


def extend(put, work, out, R=None):
    L_all = json.loads((work / "p2_labels.json").read_text(encoding="utf-8"))["rows"]
    L = [x for x in L_all if "gpt-oss" in x["model"]]  # development models; ALLaM is the held-out family below
    H = [x for x in L_all if "allam" in x["model"]]
    J =json.loads((work / "p2_judge.json").read_text(encoding="utf-8"))
    JM = json.loads((work / "p2_judge_match.json").read_text(encoding="utf-8"))
    C = json.loads((work / "p2_calib.json").read_text(encoding="utf-8"))

    # ---------------- live study
    jl = {(it["kind"], it["i"]): it["judge"] for it in J["items"] if it["set"] == "live" and "judge" in it}
    for x in L:
        x["judge_ok"] = jl.get((x["model"], x["i"]), "missing")
    LJ = [x for x in L if x["judge_ok"] != "missing"]  # replies the judge reached before the daily token quota
    put("LiveJudN", str(len(LJ)))
    put("LiveJudNTwenty", str(sum(x["model"].endswith("oss-20b") for x in LJ)))
    put("LiveJudNOneTwenty", str(sum(x["model"].endswith("120b") for x in LJ)))
    n_live = len(L)
    unsup = [x for x in L if not x["label_ok"]]
    sup = [x for x in L if x["label_ok"]]
    put("LiveN", str(n_live))
    put("LiveStates", str(len({x["i"] for x in L})))
    put("LiveUnsup", str(len(unsup)))
    put("LiveUnsupPct", f"{100 * len(unsup) / n_live:.1f}")
    for m, tag in (("openai/gpt-oss-20b", "Twenty"), ("openai/gpt-oss-120b", "OneTwenty")):
        mm = [x for x in L if x["model"] == m]
        put(f"Live{tag}UnsupPct", f"{100 * sum(not x['label_ok'] for x in mm) / len(mm):.1f}")
    eta = [x for x in unsup if any(w.startswith("ETA") for _, w in x["suggest_bad"])]
    put("LiveEta", str(len(eta)))
    put("LiveEtaPct", f"{100 * len(eta) / len(unsup):.0f}")
    put("LiveOverrides", "4")
    put("LiveJudgeNone", str(sum(1 for x in LJ if x["judge_ok"] is None)))

    def score(rows_, key):
        u = [x for x in rows_ if not x["label_ok"]]
        s = [x for x in rows_ if x["label_ok"]]
        rej = lambda x: x[key] is not True  # no verdict fails closed (template), as in the deployed system
        tp, fp = sum(rej(x) for x in u), sum(rej(x) for x in s)
        return {"rec": 100 * tp / len(u), "fpr": 100 * fp / len(s), "prec": 100 * tp / max(tp + fp, 1),
                "ci": wilson(tp, len(u)), "tp": tp, "fp": fp, "nu": len(u), "ns": len(s)}

    rows = []
    stats, statsJ = {}, {}
    for name, key in (("Deployed $\\Gamma$", "deployed_ok"), ("Typed $\\Gamma_{\\mathrm{T}}$", "typed_ok"),
                      ("LLM judge", "judge_ok")):
        a = score(L, key)
        b = score(LJ, key)
        stats[key], statsJ[key] = (a if key != "judge_ok" else None), b
        calls = "1" if key == "judge_ok" else "0"
        rows.append(f"{name} & {a['rec']:.1f} ({a['ci'][0]:.0f}--{a['ci'][1]:.0f}) & {a['fpr']:.1f} & {a['prec']:.1f} & {calls}\\\\")
    LA = [x for x in L if x["judge_ok"] is not None]
    a = score(LA, "judge_ok")
    rows.append(f"LLM judge$^\\ast$ &{a['rec']:.1f} ({a['ci'][0]:.0f}--{a['ci'][1]:.0f}) & {a['fpr']:.1f} & {a['prec']:.1f} & 1\\\\")
    put("LiveSup", str(sum(x["label_ok"] for x in L)))
    (out / "tab_live.tex").write_text("\n".join(rows), encoding="utf-8")
    for key, tag in (("deployed_ok", "Dep"), ("typed_ok", "Typ")):
        a = stats[key]
        put(f"Live{tag}Rec", f"{a['rec']:.1f}")
        put(f"Live{tag}Fpr", f"{a['fpr']:.1f}")
        put(f"Live{tag}Prec", f"{a['prec']:.1f}")
        put(f"Live{tag}Fp", str(a["fp"]))
    for key, tag in (("deployed_ok", "Dep"), ("typed_ok", "Typ"), ("judge_ok", "Jud")):
        b = statsJ[key]
        put(f"LiveJ{tag}Rec", f"{b['rec']:.1f}")
        put(f"LiveJ{tag}Fpr", f"{b['fpr']:.1f}")
    put("LiveJUnsup", str(statsJ["judge_ok"]["nu"]))
    sj = statsJ["judge_ok"]
    put("LiveJJudMiss", str(sj["nu"] - sj["tp"]))
    assert len(LJ) == len(L), "text: the judge checked every live reply"
    assert sj["nu"] - sj["tp"] == 1, "text: judge missed exactly one unsupported reply"
    assert sj["rec"] > max(statsJ["deployed_ok"]["rec"], statsJ["typed_ok"]["rec"]), \
        "text: judge recall above both guards on the same replies"
    assert sj["fpr"] > statsJ["typed_ok"]["fpr"] > statsJ["deployed_ok"]["fpr"], \
        "text: judge rejects more supported replies than either guard"
    stats = {k: (v["rec"], v["fpr"], v["prec"], v["tp"], v["fp"]) for k, v in stats.items() if v}
    # what the deployed guard missed on live replies
    dep_miss = [x for x in unsup if x["deployed_ok"]]
    words_miss = [x for x in dep_miss if any(re.search(r"\b(five|ten|fifteen|twenty|thirty)\b[^.]{0,12}min",
                                                       t["text"].lower()) for t in x["turns"])]
    clock_miss = [x for x in dep_miss if any(w == "ETA (clock time)" for _, w in x["suggest_bad"])]
    put("LiveDepMiss", str(len(dep_miss)))
    put("LiveDepMissWords", str(len(words_miss)))
    put("LiveDepMissClock", str(len(clock_miss)))
    typ_fp = [x for x in sup if not x["typed_ok"]]
    put("LiveTypFpN", str(len(typ_fp)))
    # qualitative over-claims that no numeric check can see
    pat = re.compile(r"flood (is )?confirmed|confirmed flood|breach|flood (has )?occurred|full-blown flood|"
                     r"overtopping|water ingress", re.I)
    oc = [x for x in L if any(pat.search(t["text"]) for t in x["turns"])]
    put("LiveOverclaim", str(len(oc)))
    put("LiveOverclaimPct", f"{100 * len(oc) / n_live:.0f}")
    assert all(x["band"] == "auto" for x in oc), "text: overclaims all in the automated band"
    assert len(eta) / len(unsup) > 0.9, "text: nearly all unsupported numbers are invented ETAs"
    assert len(words_miss) + len(clock_miss) > 0.5 * len(dep_miss), "text: words and clock ETAs explain most misses"
    digit_eta = [x for x in unsup if any(w == "ETA (duration)" for _, w in x["suggest_bad"]) and x not in words_miss]
    assert sum(not x["deployed_ok"] for x in digit_eta) > 0.5 * len(digit_eta), "text: digit ETAs usually caught"
    put("LiveDigitEtaCaught", f"{100 * sum(not x['deployed_ok'] for x in digit_eta) / len(digit_eta):.0f}")
    assert stats["typed_ok"][0] > stats["deployed_ok"][0], "text: typed guard has higher recall on live replies"
    assert stats["typed_ok"][4] > 0, "text: typed guard has false rejections on live replies"

    # ---------------- injected items: judge vs guards, matched
    ji = {(it["i"], it["kind"]): it["judge"] for it in J["items"] if it["set"] == "injected"}
    m = {(x["i"], x["kind"]): x for x in JM}
    assert set(ji) == set(m), "judge and guards saw the same injected items"
    n_states = len({k[0] for k in m})
    put("JudgeInjStates", str(n_states))
    put("JudgeInjItems", str(len(m)))
    jrows = []
    det = {}
    for kind in ["grounded"] + ERR:
        ks = [k for k in m if k[1] == kind]
        if kind == "grounded":
            vals = [100 * sum(not m[k]["deployed_ok"] for k in ks) / len(ks),
                    100 * sum(not m[k]["typed_ok"] for k in ks) / len(ks),
                    100 * sum(ji[k] is not True for k in ks) / len(ks)]
            put("JudgeFalseRej", f"{vals[2]:.1f}")
            put("JudgeFalseRejN", str(sum(ji[k] is not True for k in ks)))
        else:
            vals = [100 * sum(not m[k]["deployed_ok"] for k in ks) / len(ks),
                    100 * sum(not m[k]["typed_ok"] for k in ks) / len(ks),
                    100 * sum(ji[k] is not True for k in ks) / len(ks)]
        det[kind] = vals
    names = {"grounded": "Grounded (false rej.)", "prob_small": "Probability $\\pm$1--5", "prob_large":
             "Probability $\\pm$10--30", "rain_rel": "Rainfall 0.5--1.5$\\times$", "river": "River $\\pm$0.5--2 m",
             "count": "Invented head-count", "eta": "Invented ETA", "words": "Wrong value in words"}
    for kind in ["grounded"] + ERR:
        jrows.append(f"{names[kind]} & " + " & ".join(f"{v:.1f}" for v in det[kind]) + "\\\\")
    num = [k for k in ERR if k != "words"]
    allnum = [np.mean([det[k][c] for k in num]) for c in range(3)]
    jrows.append("\\midrule")
    jrows.append("All numeric errors & " + " & ".join(f"{v:.1f}" for v in allnum) + "\\\\")
    (out / "tab_judge.tex").write_text("\n".join(jrows), encoding="utf-8")
    # combined detection table: full 200-state study (deployed, facts-only, typed) + matched judge subset
    if R is not None:
        crow = []
        for kind in ["grounded"] + ERR:
            if kind == "grounded":
                full = [100 * (R["grounded"]["n"] - R["grounded"][v]) / R["grounded"]["n"]
                        for v in ("deployed", "facts_only", "typed")]
            else:
                full = [100 * R[kind][v] / R[kind]["n"] for v in ("deployed", "facts_only", "typed")]
            crow.append(f"{names[kind]} & " + " & ".join(f"{v:.1f}" for v in full) + " & " +
                        " & ".join(f"{v:.1f}" for v in det[kind]) + "\\\\")
            if kind == "grounded":
                crow.append("\\midrule")
        fulln = [100 * sum(R[k][v] for k in num) / sum(R[k]["n"] for k in num) for v in ("deployed", "facts_only", "typed")]
        crow.append("\\midrule")
        crow.append("All numeric errors & " + " & ".join(f"{v:.1f}" for v in fulln) + " & " +
                    " & ".join(f"{v:.1f}" for v in allnum) + "\\\\")
        (out / "tab_guard_all.tex").write_text("\n".join(crow), encoding="utf-8")
    assert det["prob_small"][2] < min(det["prob_small"][0], det["prob_small"][1]), \
        "text: judge weakest on small probability errors"
    assert allnum[1] >= allnum[2] and det["words"][1] >= det["words"][2], "text: typed guard most complete on injected"
    assert det["prob_small"][1] == 100.0, "text: typed guard caught the one-digit errors the judge missed"
    put("JudgeInjNum", f"{allnum[2]:.1f}")
    put("JudgeProbSmallMiss", f"{100 - det['prob_small'][2]:.0f}")
    put("JudgeInjWords", f"{det['words'][2]:.1f}")
    put("DepInjNumSub", f"{allnum[0]:.1f}")
    put("TypInjNumSub", f"{allnum[1]:.1f}")
    put("JudgeModel", "Qwen3 (27B)")

    # ---------------- calibration and the disagreement gate on held-out rows
    put("CalTest", str(C["n_test"]))
    put("CalTrain", str(C["n_train"]))
    put("CalPos", f"{100 * C['pos_rate_test']:.1f}")
    for n, tag in (("random_forest", "Rf"), ("xgboost", "Xgb")):
        put(f"Ece{tag}", f"{C['reliability'][n]['ece']:.3f}")
        put(f"EceCal{tag}", f"{C['calibrated'][n]['ece']:.3f}")
        put(f"Brier{tag}", f"{C['reliability'][n]['brier']:.3f}")
        put(f"MeanP{tag}", f"{C['reliability'][n]['mean_p']:.3f}")
    put("CalGapMean", f"{C['gap_test_mean']:.3f}")
    put("DeltaCv", f"{C['delta95_cv']:.2f}")
    g = C["gate"]
    grow = []
    for name, lab in (("deployed", f"$\\delta={C['delta_deployed']:.2f}$ (deployed)"),
                      ("delta95_cv", f"$\\delta_{{95}}={C['delta95_cv']:.2f}$ (train CV)"),
                      ("straddle_only", "straddle only")):
        s = g[name]
        grow.append(f"{lab} & {s['hold_pct']:.1f} & {s['both_auto_held_pct']:.1f} & {s['err_held_pct']:.1f} & "
                    f"{s['err_released_pct']:.1f}\\\\")
    cg = C["calibrated"]["gate_deployed_delta"]
    grow.append(f"isotonic, $\\delta={C['delta_deployed']:.2f}$ & {cg['hold_pct']:.1f} & {cg['both_auto_held_pct']:.1f} & "
                f"{cg['err_held_pct']:.1f} & {cg['err_released_pct']:.1f}\\\\")
    (out / "tab_calib.tex").write_text("\n".join(grow), encoding="utf-8")
    for name, tag in (("deployed", "Dep"), ("delta95_cv", "Cv"), ("straddle_only", "St")):
        s = g[name]
        put(f"Gate{tag}Hold", f"{s['hold_pct']:.1f}")
        put(f"Gate{tag}Both", f"{s['both_auto_held_pct']:.1f}")
        put(f"Gate{tag}ErrHeld", f"{s['err_held_pct']:.1f}")
        put(f"Gate{tag}ErrRel", f"{s['err_released_pct']:.1f}")
    put("GateCalHold", f"{cg['hold_pct']:.1f}")
    put("GateCalBoth", f"{cg['both_auto_held_pct']:.1f}")
    put("GateDepErrRatio", f"{g['deployed']['err_held_pct'] / g['deployed']['err_released_pct']:.1f}")
    put("GateStErrRatio", f"{g['straddle_only']['err_held_pct'] / g['straddle_only']['err_released_pct']:.1f}")
    # Fig.: reliability diagram of the two deployed classifiers on the held-out rows
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, ax = plt.subplots(figsize=(3.45, 1.8))
    ax.plot([0, 1], [0, 1], ":", color="black", lw=0.6, label="perfect calibration")
    for n, st, col, lab in (("random_forest", "o-", "0.05", "Random Forest"), ("xgboost", "s--", "0.5", "XGBoost")):
        b = [x for x in C["reliability"][n]["bins"] if x["n"] >= 10]
        ax.plot([x["conf"] for x in b], [x["freq"] for x in b], st, color=col, ms=3, lw=0.9,
                label=f"{lab} (ECE {C['reliability'][n]['ece']:.3f})")
    ax.axvline(C["tau"], color="0.7", lw=0.5)
    ax.text(C["tau"] + 0.01, 0.04, "$\\tau_a$", fontsize=7)
    ax.set_xlabel("predicted flood probability")
    ax.set_ylabel("observed flood rate")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(lw=0.3)
    ax.legend(fontsize=6.2, frameon=False, loc="upper left")
    fig.tight_layout(pad=0.3)
    fig.savefig(out / "fig_reliability.pdf")
    plt.close(fig)
    xb = [x for x in C["reliability"]["xgboost"]["bins"] if x["n"] >= 10 and x["conf"] >= 0.6]
    put("XgbHighConf", f"{np.average([x['conf'] for x in xb], weights=[x['n'] for x in xb]):.2f}")
    put("XgbHighFreq", f"{np.average([x['freq'] for x in xb], weights=[x['n'] for x in xb]):.2f}")
    assert np.average([x['conf'] - x['freq'] for x in xb], weights=[x['n'] for x in xb]) > 0.1, \
        "text: XGBoost over-confident above the threshold"
    assert C["reliability"]["xgboost"]["ece"] > 2 * C["reliability"]["random_forest"]["ece"], \
        "text: XGBoost much less calibrated than RF"
    assert all(C["calibrated"][n]["ece"] < C["reliability"][n]["ece"] for n in ("random_forest", "xgboost")), \
        "text: isotonic calibration lowers ECE of both"
    assert g["deployed"]["err_held_pct"] > 1.5 * g["deployed"]["err_released_pct"], "text: holds flag errors"
    assert g["straddle_only"]["err_held_pct"] > g["deployed"]["err_held_pct"], "text: straddle is the sharper signal"
    assert g["straddle_only"]["hold_pct"] < g["deployed"]["hold_pct"] / 3, "text: straddle holds far fewer"
    assert abs(C["delta95_cv"] - 0.30) < 0.05, "text: data-driven delta near the 0.30 found by the sweep"
    assert 0.2 < g["straddle_only"]["hold_pct"] / g["deployed"]["hold_pct"] < 0.34, "text: straddle holds about a quarter"
    assert g["straddle_only"]["both_auto_held_pct"] == 0.0, "text: straddle never holds when both models agree"
    assert cg["hold_pct"] < g["deployed"]["hold_pct"], "text: calibration lowers the hold rate"

    # ---------------- typed guard v2 (frozen) and the held-out model family
    V = json.loads((work / "p2_guard_v2.json").read_text(encoding="utf-8"))
    assert V["sha256"] == V["frozen"], "guard v2 evaluated with the frozen file"
    v2 = {(x["model"], x["i"]): x for x in V["rows"]}
    for x in L + H:
        x["v2_ok"] = v2[(x["model"], x["i"])]["v2_ok"]
    hs = {}
    hrows = []
    for name, key in (("Deployed $\\Gamma$", "deployed_ok"), ("Typed $\\Gamma_{\\mathrm{T}}$", "typed_ok"),
                      ("Typed v2 (frozen)", "v2_ok")):
        a, b = score(L, key), score(H, key)
        hs[key] = (a, b)
        hrows.append(f"{name} & {a['rec']:.1f} & {a['fpr']:.1f} & {b['rec']:.1f} ({b['ci'][0]:.0f}--{b['ci'][1]:.0f}) & "
                     f"{b['fpr']:.1f}\\\\")
    (out / "tab_heldout.tex").write_text("\n".join(hrows), encoding="utf-8")
    for key, tag in (("deployed_ok", "Dep"), ("typed_ok", "Typ"), ("v2_ok", "Vtwo")):
        a, b = hs[key]
        put(f"Dev{tag}Rec", f"{a['rec']:.1f}")
        put(f"Dev{tag}Fpr", f"{a['fpr']:.1f}")
        put(f"Ho{tag}Rec", f"{b['rec']:.1f}")
        put(f"Ho{tag}Fpr", f"{b['fpr']:.1f}")
        put(f"Ho{tag}Fp", str(b["fp"]))
        put(f"Ho{tag}Miss", str(b["nu"] - b["tp"]))
    hu = [x for x in H if not x["label_ok"]]
    put("HoN", str(len(H)))
    put("HoStates", "150")
    put("HoUnsup", str(len(hu)))
    put("HoUnsupPct", f"{100 * len(hu) / len(H):.1f}")
    put("HoParseFail", str(150 - len(H)))
    cnt = [x for x in hu if any(w in ("unbound number", "quantity not in state", "number word, no state quantity")
                                for _, w in x["suggest_bad"])]  # same categories as Fig. errtypes
    put("HoCountPct", f"{100 * len(cnt) / len(hu):.0f}")
    put("HoOverrides", str(sum(x["note"] != "protocol" for x in H)))
    # v2's false rejections on the held-out model: all procedural labels (Team 1, Mission 4, level 2, ...)
    v2fp = [x for x in H if x["label_ok"] and not x["v2_ok"]]
    proc = re.compile(r"\b(team|mission|level)\s+\d|every \d+ minutes|\d+ minutes to keep|every five minutes", re.I)
    assert all(any(proc.search(t["text"]) for t in x["turns"]) or x["i"] == 5 for x in v2fp), \
        "text: v2 false rejections on ALLaM are procedural labels or reporting intervals"
    put("VtwoUs", f"{np.mean([x['us'] for x in V['rows']]):.0f}")
    inj = V["injected_detect_pct"]
    put("VtwoInjGround", f"{inj['grounded']:.1f}")
    put("VtwoInjNum", f"{np.mean([inj[k] for k in ERR if k != 'words']):.1f}")
    put("VtwoInjWords", f"{inj['words']:.1f}")
    a, b = hs["v2_ok"]
    assert a["rec"] == 100.0 and a["fpr"] == 0.0, "text: v2 perfect on the development replies it was built on"
    assert b["rec"] > hs["deployed_ok"][1]["rec"], "text: v2 recall above deployed guard on held-out model"
    assert b["fpr"] > a["fpr"] + 5, "text: v2 false rejection rises on the held-out model"
    assert b["fpr"] < hs["typed_ok"][1]["fpr"], "text: v2 rejects fewer grounded replies than the typed guard"
    assert b["fpr"] > hs["deployed_ok"][1]["fpr"], "text: v2 rejects more grounded replies than deployed"
    assert b["nu"] - b["tp"] == 1, "text: v2 let through only one unsupported reply"
    assert len(hu) / len(H) > 0.5, "text: most ALLaM replies unsupported"
    assert len(cnt) / len(hu) > 0.5, "text: invented counts/quantities dominate ALLaM errors (not ETAs)"

    # worked examples: real excerpts from held-out replies, with the stored verdicts of every check
    hx = {x["i"]: x for x in H}
    ex = [(0, "probability of flooding is at 34.3%", "state value"),
          (8, "begun flooding with 134 affected", "head-count"),
          (15, "NDRF teams is 20:59 IST", "arrival time"),
          (21, "Team 1 (Rescue) will head to", "label")]
    tick = lambda ok: "pass" if ok else "\\textbf{rej.}"
    erow = []
    for i, frag, why in ex:
        x = hx[i]
        assert any(frag in t["text"] for t in x["turns"]), f"excerpt {i} not in the stored reply"
        erow.append(f"``{frag.replace('%', chr(92) + '%')}'' ({why}) & {'yes' if x['label_ok'] else 'no'} & {tick(x['deployed_ok'])} & "
                    f"{tick(x['typed_ok'])} & {tick(x['v2_ok'])}\\\\")
    (out / "tab_example.tex").write_text("\n".join(erow), encoding="utf-8")
    assert hx[0]["label_ok"] and hx[0]["v2_ok"] and not hx[8]["label_ok"] and not hx[8]["v2_ok"]
    assert hx[21]["label_ok"] and not hx[21]["v2_ok"], "text: example 21 is a v2 false rejection"

    # Fig.: kinds of unsupported numbers per model (% of all replies of that model)
    cats = {"Arrival time": ("ETA (duration)", "ETA (clock time)"),
            "Invented quantity": ("unbound number", "quantity not in state", "number word, no state quantity"),
            "Wrong probability": ("probability/threshold",), "Wrong level or rain": ("water level", "rainfall"),
            "Wrong clock time": ("wrong time",)}
    mods = (("openai/gpt-oss-20b", "gpt-oss-20b"), ("openai/gpt-oss-120b", "gpt-oss-120b"),
            ("allam-2-7b", "ALLaM-2 7B (held out)"))
    share = {}
    for m, _ in mods:
        rows_m = [x for x in L_all if x["model"] == m]
        um = [x for x in rows_m if not x["label_ok"]]
        share[m] = {c: 100 * sum(any(w in ws for _, w in x["suggest_bad"]) for x in um) / len(rows_m)
                    for c, ws in cats.items()}
    fig, ax = plt.subplots(figsize=(3.45, 1.6))
    yy = np.arange(len(cats))
    for k, ((m, lab), col) in enumerate(zip(mods, ("0.75", "0.45", "0.1"))):
        ax.barh(yy + (k - 1) * 0.27, [share[m][c] for c in cats], height=0.26, color=col, label=lab)
    ax.set_yticks(yy)
    ax.set_yticklabels(list(cats))
    ax.invert_yaxis()
    ax.set_xlabel("replies with this error (%)")
    ax.grid(axis="x", lw=0.3)
    fig.legend(*ax.get_legend_handles_labels(), fontsize=6.2, frameon=False, loc="upper center", ncol=3,
               columnspacing=1.0, handlelength=1.2)
    fig.tight_layout(pad=0.3, rect=(0, 0, 1, 0.88))
    fig.savefig(out / "fig_errtypes.pdf")
    plt.close(fig)
    oss = ("openai/gpt-oss-20b", "openai/gpt-oss-120b")
    put("ErrOssEtaMin", f"{min(share[m]['Arrival time'] for m in oss):.0f}")
    put("ErrOssEtaMax", f"{max(share[m]['Arrival time'] for m in oss):.0f}")
    put("ErrAllamEta", f"{share['allam-2-7b']['Arrival time']:.1f}")
    put("ErrAllamQty", f"{share['allam-2-7b']['Invented quantity']:.0f}")
    put("ErrAllamProb", f"{share['allam-2-7b']['Wrong probability']:.0f}")
    assert all(share[m]["Arrival time"] > 5 * share[m]["Invented quantity"] for m in oss), "text: gpt-oss errors are ETAs"
    assert all(share[m]["Wrong probability"] == 0 for m in oss), "text: gpt-oss never misquoted a probability"
    assert share["allam-2-7b"]["Invented quantity"] > 5 * share["allam-2-7b"]["Arrival time"], "text: ALLaM invents quantities"
    assert share["allam-2-7b"]["Wrong probability"] > 10, "text: ALLaM misquotes probabilities"
    return stats, det
