"""Third-revision numbers for P4 (p4_r3.json from exp_p4_r3.py, p4_r4.json from exp_p4_r4.py) -> macros and table rows.

Called from post_p4.py after post_p4_r2.extend. Adds rows to tab_robust.tex (climate indices from training years, no climate
indices, real-time inputs, logistic regression), writes tab_rules.tex (operating rules) and asserts every claim in the text.
"""
import json


def f3(x):
    return f"{x:.3f}"


def includes_zero(ci):
    return ci[0] <= 0 <= ci[1]


def extend(put, work, out, j):
    r = json.loads((work / "p4_r3.json").read_text(encoding="utf-8"))
    V, P = r["variants"], r["paired"]
    mn = r["main"]
    assert abs(mn["ba"] - j["methods"]["xgboost"]["ba"]) < 1e-9
    put("MainBAGYLo", f3(mn["ba_ci_gauge_year"][0]))
    put("MainBAGYHi", f3(mn["ba_ci_gauge_year"][1]))
    assert mn["ba_ci_gauge_year"][1] - mn["ba_ci_gauge_year"][0] > mn["ba_ci_gauge"][1] - mn["ba_ci_gauge"][0], \
        "text: resampling years as well widens the interval"
    assert abs(V["all"]["ba"] - j["ablation"]["all"]["ba"]) < 1e-9, "refit reproduces the ablation's all-input model"

    # ---- below-level skill: what it needs (paired gauge bootstrap)
    for key, tag in (("all-no_flow", "NoFlow"), ("all-flow_season", "NoMet"), ("met_season-flow_season", "MetFlow")):
        put(f"Bel{tag}Diff", f3(P[key]["below_diff"]))
        put(f"Bel{tag}Lo", f3(P[key]["below_ci"][0]))
        put(f"Bel{tag}Hi", f3(P[key]["below_ci"][1]))
    assert includes_zero(P["all-no_flow"]["below_ci"]), "text: removing flow did not lower below-level BA detectably"
    assert P["all-flow_season"]["below_ci"][0] > 0, "text: removing the non-flow inputs did"
    assert P["all-met_season"]["below_ci"][0] > 0, "text: meteorology alone stays below the full model"
    assert includes_zero(P["met_season-flow_season"]["below_ci"]), "text: meteorology alone vs flow alone not resolved"

    # ---- onset warnings at a common alarm rate
    mw = r["matched_warn"]
    put("MatchAlarms", f"{1000 * mw['alarm_rate']:.0f}")
    put("MatchWarnAll", f"{mw['all']['matched_pct']:.1f}")
    put("MatchWarnNoFlow", f"{mw['no_flow']['matched_pct']:.1f}")
    put("OwnWarnNoFlow", f"{mw['no_flow']['own_thr_pct']:.1f}")
    put("NoFlowAlarms", f"{V['no_flow']['alarms_per_1000']:.0f}")
    assert mw["no_flow"]["own_thr_pct"] > mw["all"]["own_thr_pct"], "text: at its own threshold no-flow warns more"
    assert mw["no_flow"]["matched_pct"] <= mw["all"]["matched_pct"], "text: at a common alarm rate it does not"
    assert V["no_flow"]["alarms_per_1000"] > V["all"]["alarms_per_1000"], "text: because it raises more alarms"

    # ---- climate indices, real-time inputs, logistic regression
    au = r["clim_audit"]
    put("ClimCorrMin", f"{min(v['corr_full_vs_train'] for v in au.values()):.2f}")
    rows = []
    for key, tag, lab in (("clim_train", "ClimTr", "Climate indices, 1980--2008"), ("no_clim", "NoClim", "No climate indices"),
                          ("realtime", "Rt", "Real-time inputs only")):
        v = V[key]
        d = P[f"all-{key}"]
        put(f"{tag}BA", f3(v["ba"]))
        put(f"{tag}PR", f3(v["pr_auc"]))
        put(f"{tag}Below", f3(v["below_ba"]))
        put(f"{tag}Lo", f3(d["ba_ci"][0]))
        put(f"{tag}Hi", f3(d["ba_ci"][1]))
        if key == "realtime":
            put("RtDiff", f3(d["ba_diff"]))
            put("RtBelLo", f3(d["below_ci"][0]))
            put("RtBelHi", f3(d["below_ci"][1]))
            assert d["ba_ci"][0] > 0 and d["ba_diff"] < 0.01, "text: real-time inputs cost a small, detectable amount"
            assert includes_zero(d["below_ci"]), "text: and no detectable amount on below-level rows"
        else:
            assert includes_zero(d["ba_ci"]), f"text: {key} is not detectably different from all inputs"
        rows.append(f"{lab} & {j['n_test_gauges']} & {v['ba']:.3f} & {v['pr_auc']:.3f} & {v['below_ba']:.3f}\\\\")
    lr = r["logreg"]
    put("LrTestBA", f3(lr["ba"]))
    put("LrTestPR", f3(lr["pr_auc"]))
    put("LrDiffLo", f3(lr["diff_vs_all_ci"][0]))
    put("LrDiffHi", f3(lr["diff_vs_all_ci"][1]))
    put("LrGainPR", f"{100 * (V['all']['pr_auc'] - lr['pr_auc']):.1f}")
    assert V["all"]["pr_auc"] - lr["pr_auc"] > 0.03, "text: boosting adds PR-AUC over logistic regression"
    rows.append(f"Logistic regression & {j['n_test_gauges']} & {lr['ba']:.3f} & {lr['pr_auc']:.3f} & {lr['below_ba']:.3f}\\\\")
    with open(out / "tab_robust.tex", "a", encoding="utf-8") as fh:
        fh.write("\n\\midrule\n" + "\n".join(rows))
    put("RtLate", "humidity, evapotranspiration and soil moisture")
    assert set(["rh", "pet", "aet"]) and V["realtime"]["n_inputs"] == V["all"]["n_inputs"] - 9, "real-time drops 3 + 6 inputs"

    # ---- random split scored on the same rows
    sr = r["samerows"]
    put("SrN", f"{sr['n_rows']:,}")
    put("SrGauges", str(sr["n_gauges"]))
    put("SrRandBA", f3(sr["random"]["ba"]))
    put("SrHeldBA", f3(sr["heldout"]["ba"]))
    put("SrRandPR", f3(sr["random"]["pr_auc"]))
    put("SrHeldPR", f3(sr["heldout"]["pr_auc"]))
    put("SrBALo", f"{100 * sr['ba_diff_ci'][0]:.1f}")
    put("SrBAHi", f"{100 * sr['ba_diff_ci'][1]:.1f}")
    put("SrPRLo", f"{100 * sr['pr_diff_ci'][0]:.1f}")
    put("SrPRHi", f"{100 * sr['pr_diff_ci'][1]:.1f}")
    put("SrGapBA", f"{100 * (sr['random']['ba'] - sr['heldout']['ba']):.1f}")
    put("SrGapPR", f"{100 * (sr['random']['pr_auc'] - sr['heldout']['pr_auc']):.1f}")
    assert sr["ba_diff_ci"][0] > 0 and sr["pr_diff_ci"][0] > 0, "text: on the same rows the random split scored higher"
    assert sr["n_gauges"] == j["n_test_gauges"], "the shared rows cover every test gauge"

    # ---- operating rules (exp_p4_r4.py): thresholds chosen for validation CSI, test scored once
    q = json.loads((work / "p4_r4.json").read_text(encoding="utf-8"))
    T, PD = q["test"], q["paired"]
    assert abs(T["model_ba_thr"]["csi"] - csi_of(j)) < 1e-6, "same model and test rows as Table II"
    for k, tag in (("model", "Mc"), ("hybrid", "Hy"), ("persistence", "Pe"), ("model_ba_thr", "Mb")):
        put(f"{tag}CSI", f3(T[k]["csi"]))
        put(f"{tag}Prec", f3(T[k]["precision"]))
        put(f"{tag}Rec", f3(T[k]["recall"]))
        put(f"{tag}Alarms", f"{T[k]['alarms_per_1000']:.0f}")
        put(f"{tag}Warn", f"{T[k]['onsets_warned_pct']:.0f}")
    put("HyThr", f"{q['thresholds']['hybrid']['t']:.2f}")
    put("McThr", f"{q['thresholds']['model']['t']:.2f}")
    for key, tag in (("hybrid-model", "HyM"), ("hybrid-persistence", "HyP"), ("model-persistence", "McP")):
        put(f"{tag}Lo", f3(PD[key]["csi"][0]))
        put(f"{tag}Hi", f3(PD[key]["csi"][1]))
    assert PD["hybrid-model"]["csi"][0] > 0 and PD["hybrid-persistence"]["csi"][0] > 0, \
        "text: the hybrid rule beats the model alone and persistence on CSI"
    assert includes_zero(PD["seasonal-model"]["csi"]), "text: seasonal thresholds did not help"
    assert j["methods"]["xgboost"]["precision"] < 0.5, "text: at the BA threshold most alarms were false"
    assert PD["model-persistence"]["csi"][0] > 0, "text: at a CSI threshold the model alone scores above persistence"
    assert T["hybrid"]["onsets_warned_pct"] < T["model_ba_thr"]["onsets_warned_pct"], "text: at the cost of onset warnings"
    assert T["hybrid"]["alarms_per_1000"] < 0.5 * T["model_ba_thr"]["alarms_per_1000"], "text: fewer than half the alarms"
    lab = {"persistence": "Persistence", "model_ba_thr": f"Model, BA ({q['decision_threshold_ba']:.2f})",
           "model": f"Model, CSI ({q['thresholds']['model']['t']:.2f})",
           "hybrid": f"Hybrid ({q['thresholds']['hybrid']['t']:.2f})"}
    cvq = q["curve"]
    hi_warn = [c_ for c_, w_ in zip(cvq["hybrid_csi"] + cvq["model_csi"], cvq["hybrid_warn"] + cvq["model_warn"]) if w_ >= 80]
    put("TradeMax", f3(max(hi_warn)))
    assert max(hi_warn) < T["hybrid"]["csi"] - 0.05, "text: no threshold gives both high CSI and >=80% onsets warned"

    lk = json.loads((work / "p4_leak.json").read_text(encoding="utf-8"))["protocols"]
    assert lk["time"]["pr_auc"] < lk["space"]["pr_auc"], "text: holding out later years lowered PR-AUC more than gauges"
    assert lk["random"]["ba"] == max(v["ba"] for v in lk.values()), "text: the random row split scored highest"

    ep = json.loads((work / "p4_r2.json").read_text(encoding="utf-8"))["episodes"]
    assert j["events"]["xgboost"]["warned_pct"] > ep["random_warn_3d_pct"], "text: the model warns of more onsets than random alarms"

    # ---- neural baseline (exp_p4_r5.py): MLP on the same split and sample
    n5 = json.loads((work / "p4_r5.json").read_text(encoding="utf-8"))
    mm = n5["mlp"]
    for k, tag in (("ba", "BA"), ("pr_auc", "PR"), ("below_ba", "Below")):
        put(f"Mlp{tag}", f3(mm[k]))
    put("MlpWin", str(n5["window_days"]))
    put("MlpDiffLo", f3(n5["xgb_minus_mlp"]["ba_ci"][0]))
    put("MlpDiffHi", f3(n5["xgb_minus_mlp"]["ba_ci"][1]))
    assert all(n5["xgb_minus_mlp"][k][0] > 0 for k in ("ba_ci", "pr_ci", "below_ci")), \
        "text: the MLP scored below XGBoost on BA, PR-AUC and below-level BA"
    with open(out / "tab_robust.tex", "a", encoding="utf-8") as fh:
        fh.write(f"\nMLP, {n5['window_days']}-day history & {j['n_test_gauges']} & {mm['ba']:.3f} & {mm['pr_auc']:.3f} & "
                 f"{mm['below_ba']:.3f}\\\\")

    if "curve" in q:  # trade-off figure: CSI against onsets warned, chosen operating points marked
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                             "pdf.fonttype": 42, "ps.fonttype": 42})
        cv = q["curve"]
        fig, ax = plt.subplots(figsize=(3.45, 1.85))
        ax.plot(cv["model_warn"], cv["model_csi"], "-", color="0.45", lw=1.0, label="Model, any threshold")
        ax.plot(cv["hybrid_warn"], cv["hybrid_csi"], "-", color="0.05", lw=1.2, label="Hybrid, any threshold")
        pts = (("model_ba_thr", "o", "Model, BA threshold"), ("model", "^", "Model, CSI threshold"),
               ("hybrid", "s", "Hybrid, CSI threshold"), ("persistence", "D", "Persistence"))
        for k, mk, lb in pts:
            ax.plot(T[k]["onsets_warned_pct"], T[k]["csi"], mk, color="black", ms=4.5, mfc="white", mew=0.9, label=lb)
        ax.set_xlabel("flood onsets warned 1--3 days ahead (%)".replace("--", "–"))
        ax.set_ylabel("CSI")
        ax.set_xlim(-3, 100)
        ax.grid(lw=0.3)
        ax.legend(fontsize=6.6, frameon=True, framealpha=1, edgecolor="none", loc="lower left", ncol=2,
                  handlelength=1.8, columnspacing=0.8)
        fig.tight_layout(pad=0.3)
        fig.savefig(out / "fig_trade.pdf")
        plt.close(fig)
    (out / "tab_rules.tex").write_text("\n".join(
        f"{lab[k]} & {T[k]['csi']:.3f} & {T[k]['precision']:.3f} & {T[k]['recall']:.3f} & "
        f"{T[k]['alarms_per_1000']:.0f} & {T[k]['onsets_warned_pct']:.0f}\\\\" for k in lab), encoding="utf-8")
    return r


def csi_of(j):
    m = j["methods"]["xgboost"]
    return 1.0 / (1.0 / m["precision"] + 1.0 / m["recall"] - 1.0)
