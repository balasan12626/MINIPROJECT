"""Second-revision numbers for P4 (p4_r2.json, models/flood_evaluation_v4.json) -> macros and tables.

Rewrites tab_main.tex with onset-row BA and PR-AUC for every reference and the trend rule, and writes
tab_robust.tex (other gauge splits, leave-basin-out, 99th percentile, meteorology-only, no class weight) and
tab_cand.tex (the seven candidate models on validation). Called from post_p4.py; asserts every claim in the text.
"""
import json

import numpy as np


def f3(x):
    return f"{x:.3f}"


def csi(p, r):
    """Critical success index TP/(TP+FP+FN) from precision and recall."""
    return 1.0 / (1.0 / p + 1.0 / r - 1.0)


def extend(put, work, out, root, j):
    r = json.loads((work / "p4_r2.json").read_text(encoding="utf-8"))
    ev = json.loads((root / "models" / "flood_evaluation_v4.json").read_text(encoding="utf-8"))
    M, b = r["methods"], dict(j["bootstrap"])
    r3_f = work / "p4_r3.json"
    R3 = json.loads(r3_f.read_text(encoding="utf-8")) if r3_f.exists() else {}
    if "main" in R3:  # trend rule interval (exp_p4_r3.py), same gauge bootstrap
        b["trend"] = {"ba": R3["main"]["trend"]["ba_ci"]}
        assert abs(R3["main"]["trend"]["ba"] - M["trend"]["ba"]) < 1e-9, "same trend-rule scores as p4_r2"
    # ---- main table: overall and onset rows, every method on the same test rows
    lab = {"xgboost": "XGBoost (ours)", "lstm_sim": "LSTM sim.$^\\dagger$", "trend": "Trend rule",
           "climatology": "Climatology", "persistence": "Persistence"}
    rows = []
    for k in ("xgboost", "lstm_sim", "trend", "climatology", "persistence"):
        v = M[k]
        ci = f"{b[k]['ba'][0]:.3f}--{b[k]['ba'][1]:.3f}" if k in b else "--"
        rows.append(f"{lab[k]} & {v['ba']:.3f} & {ci} & {v['pr_auc']:.3f} & {v['recall']:.3f} & {v['precision']:.3f} & "
                    f"{csi(v['precision'], v['recall']):.3f} & {v['onset_ba']:.3f}\\\\")
    nf = j["methods"]["xgb_no_flow"]
    rows.insert(1, f"No-flow XGB.$^\\ddagger$ & {nf['ba']:.3f} & {b['xgb_no_flow']['ba'][0]:.3f}--{b['xgb_no_flow']['ba'][1]:.3f} & "
                   f"{nf['pr_auc']:.3f} & {nf['recall']:.3f} & {nf['precision']:.3f} & "
                   f"{csi(nf['precision'], nf['recall']):.3f} & {nf['onset']['ba']:.3f}\\\\")
    (out / "tab_main.tex").write_text("\n".join(rows), encoding="utf-8")
    for k, t in (("xgboost", "Xgb"), ("lstm_sim", "Lstm"), ("trend", "Trend"), ("climatology", "Clim"),
                 ("persistence", "Pers")):
        put(f"On{t}BA", f3(M[k]["onset_ba"]))
        put(f"On{t}PR", f3(M[k]["onset_pr_auc"]))
    put("TrendBA", f3(M["trend"]["ba"]))
    put("TrendPR", f3(M["trend"]["pr_auc"]))
    assert abs(M["xgboost"]["ba"] - j["methods"]["xgboost"]["ba"]) < 1e-9, "same test rows as p4.json"
    assert M["lstm_sim"]["onset_ba"] > M["xgboost"]["onset_ba"], "text: on onset rows the LSTM (future rain) leads"
    assert M["xgboost"]["ba"] > M["trend"]["ba"] > M["persistence"]["ba"], "text: trend rule between model and persistence"
    assert all(M["xgboost"]["onset_ba"] > M[k]["onset_ba"] for k in ("trend", "climatology", "persistence")), \
        "text: on onset rows the model leads every reference except the LSTM"

    # ---- hydrological scores: POD = recall, FAR = 1 - precision, CSI = TP/(TP+FP+FN)
    cs = {k: csi(M[k]["precision"], M[k]["recall"]) for k in M}
    for k, t in (("xgboost", "Xgb"), ("lstm_sim", "Lstm"), ("trend", "Trend"), ("climatology", "Clim"),
                 ("persistence", "Pers")):
        put(f"{t}CSI", f3(cs[k]))
    put("XgbFAR", f3(1.0 - M["xgboost"]["precision"]))
    assert cs["persistence"] > cs["lstm_sim"] > cs["xgboost"], "text: persistence highest CSI, then LSTM, then the model"
    # ---- operating points + seasons in one table (BA per threshold derived from prevalence, recall and alarm rate)
    S = json.loads((work / "p4_extra.json").read_text(encoding="utf-8"))["season"]
    pv, t0 = j["pos_rate"], j["methods"]["xgboost"]["thr"]
    star = "$^\\ast$"
    opr, c75, c_other = [], None, []
    for o in j["operating_points"]:
        fp = o["alarms_per_1000"] / 1000.0 - o["recall"] * pv
        ba_o = 0.5 * (o["recall"] + 1.0 - fp / (1.0 - pv))
        sel = abs(o["thr"] - t0) < 1e-9
        if sel:
            assert abs(ba_o - j["methods"]["xgboost"]["ba"]) < 1e-6, "derived BA reproduces the stored BA"
        c = csi(o["precision"], o["recall"])
        if abs(o["thr"] - 0.75) < 1e-9:
            c75 = c
        else:
            c_other.append(c)
        opr.append(f"{o['thr']:.2f}{star if sel else ''}, all & {100 * pv:.1f} & {ba_o:.3f} & {o['recall']:.3f} & "
                   f"{o['precision']:.3f} & {c:.3f} & {o['alarms_per_1000']:.0f}\\\\")
    opr.append("\\midrule")
    for lab_s, v in (("Jun--Sep", S["monsoon"]), ("Oct--May", S["other"])):
        opr.append(f"{t0:.2f}{star}, {lab_s} & {100 * v['pos_rate']:.1f} & {v['ba']:.3f} & {v['recall']:.3f} & "
                   f"{v['precision']:.3f} & {csi(v['precision'], v['recall']):.3f} & {v['alarms_per_1000']:.0f}\\\\")
    (out / "tab_opsea.tex").write_text("\n".join(opr), encoding="utf-8")
    put("MonN", f"{S['monsoon']['n']:,}")
    put("OthN", f"{S['other']['n']:,}")
    put("CsiSeventyFive", f3(c75))
    assert c75 > cs["persistence"] and all(c < cs["persistence"] for c in c_other), \
        "text: of the tabled thresholds only 0.75 lifts the model's CSI above persistence"

    # ---- LSTM: paired difference, matched alarm rate, training design
    L = r["lstm"]
    put("LstmDiffLo", f3(L["diff_ci"][0]))
    put("LstmDiffHi", f3(L["diff_ci"][1]))
    put("LstmDiffOnLo", f3(L["diff_onset_ci"][0]))
    put("LstmDiffOnHi", f3(L["diff_onset_ci"][1]))
    put("LstmAlarm", f"{1000 * L['lstm_alarm_rate']:.0f}")
    put("MatchPrec", f3(L["xgb_matched"]["precision"]))
    put("MatchRec", f3(L["xgb_matched"]["recall"]))
    assert L["diff_ci"][0] < 0 < L["diff_ci"][1], "text: paired CI of the BA difference includes zero"
    assert L["xgb_matched"]["precision"] > M["lstm_sim"]["precision"] and L["xgb_matched"]["recall"] > M["lstm_sim"]["recall"], \
        "text: at the LSTM's alarm rate the model is more precise and finds more floods"
    assert abs(r["lstm_coverage_test"] - 1.0) < 1e-12, "text: the LSTM covers every test row"

    # ---- gauges
    g = r["gauges"]
    put("UnseenNoRows", str(len(g["unseen_without_test_rows"])))
    put("NUnseen", str(g["unseen"]))
    put("SeenTestGauges", str(g["seen_with_test_rows"]))
    assert g["unseen"] == 49 and g["unseen_with_test_rows"] == 48 and len(g["unseen_without_test_rows"]) == 1
    assert r["g228"]["n_gauges_total"] == 242, "text: every gauge of this dataset version passes the >30% filter"

    # ---- calibration
    c = r["calibration"]
    put("BrierRaw", f3(c["brier_raw"]))
    put("BrierIso", f3(c["brier_iso"]))
    put("BrierClim", f3(c["brier_clim"]))
    put("EceRawLo", f3(c["ece_ci"]["raw"][0]))
    put("EceRawHi", f3(c["ece_ci"]["raw"][1]))
    put("EceIsoLo", f3(c["ece_ci"]["iso"][0]))
    put("EceIsoHi", f3(c["ece_ci"]["iso"][1]))
    put("EceMonRaw", f3(c["monsoon"]["ece_raw"]))
    put("EceMonIso", f3(c["monsoon"]["ece_iso"]))
    put("EceOthRaw", f3(c["other"]["ece_raw"]))
    assert c["brier_raw"] > c["brier_clim"] > c["brier_iso"], "text: raw Brier worse than climatology, recalibrated better"
    assert c["monsoon"]["ece_raw"] > 5 * c["other"]["ece_raw"], "text: miscalibration is a monsoon problem"

    # ---- per year, regulation, non-stationarity, dropped days
    py = r["per_year"]
    big = {y: v for y, v in py.items() if v["n"] > 5000}
    put("YearMinBA", f3(min(v["ba"] for v in big.values())))
    put("YearMaxBA", f3(max(v["ba"] for v in big.values())))
    put("YearMin", min(big, key=lambda y: big[y]["ba"]))
    put("YearMax", max(big, key=lambda y: big[y]["ba"]))
    put("YearsBig", f"{min(big)}--{max(big)}")
    small = {y: v for y, v in py.items() if v["n"] <= 5000}
    put("YearsSmallRows", f"{sum(v['n'] for v in small.values()):,}")
    put("YearsSmall", " and ".join(sorted(small)))
    put("YearLateBA", " and ".join(f"{small[y_]['ba']:.3f} in {y_}" for y_ in sorted(small)))
    assert all(v["ba"] < min(b_["ba"] for b_ in big.values()) for v in small.values()), \
        "text: the sparse late years scored lower than every well-covered year"
    rg = r["regulation"]
    put("RegRho", f"{rg['rho_num_dams']:.2f}")
    put("RegP", f"{rg['p_num_dams']:.2f}")
    put("RegRhoRes", f"{rg['rho_reservoir_index']:.2f}")
    put("RegPRes", f"{rg['p_reservoir_index']:.2f}")
    assert rg["p_reservoir_index"] > 0.05, "text: the reservoir index showed no clear relation"
    put("RegDams", str(rg["n_with_dams"]))
    put("RegNoDams", str(rg["n_no_dams"]))
    put("RegBADams", f3(rg["ba_with_dams"]))
    put("RegBANoDams", f3(rg["ba_no_dams"]))
    ns = r["nonstationarity"]
    put("NsTrain", f"{100 * ns['flood_today_rate_train_years']:.1f}")
    put("NsTest", f"{100 * ns['flood_today_rate_test_years']:.1f}")
    dr = r["dropped"]
    put("DropN", f"{dr['n_dropped']:,}")
    put("DropPct", f"{100 * dr['n_dropped'] / dr['n_days']:.1f}")
    put("DropMon", f"{100 * dr['monsoon_share_dropped']:.0f}")
    put("KeptMon", f"{100 * dr['monsoon_share_kept']:.0f}")
    put("DropHigh", f"{100 * dr['after_high_share_dropped']:.1f}")
    put("KeptHigh", f"{100 * dr['after_high_share_kept']:.1f}")
    assert dr["monsoon_share_dropped"] < dr["monsoon_share_kept"], "text: dropped days are not concentrated in the monsoon"
    assert dr["after_high_share_dropped"] < dr["after_high_share_kept"], "text: nor after high flow"

    # ---- episodes and random-alarm reference
    e = r["episodes"]
    put("EpN", f"{e['n']:,}")
    put("EpFalse", f"{e['false']:,}")
    put("EpFalsePct", f"{100 * e['false'] / e['n']:.0f}")
    put("RandWarn", f"{e['random_warn_3d_pct']:.1f}")
    put("RandWarnMon", f"{e['random_warn_3d_monsoon_pct']:.1f}")

    # ---- refits: other splits, basins, q99, meteorology-only, no class weight
    R = r.get("refits", {})
    rob = []
    if "splits" in r and r["splits"]:
        sp = r["splits"]
        bas = [v["ba"] for v in sp.values()]
        prs = [v["pr_auc"] for v in sp.values()]
        ons = [v["onset_ba"] for v in sp.values()]
        put("SplitN", str(len(sp)))
        put("SplitBAMin", f3(min(bas)))
        put("SplitBAMax", f3(max(bas)))
        put("SplitPRMin", f3(min(prs)))
        put("SplitPRMax", f3(max(prs)))
        put("SplitOnMin", f3(min(ons)))
        put("SplitOnMax", f3(max(ons)))
        six = bas + [j["ablation"]["all"]["ba"]]
        put("SplitBAMean", f3(float(np.mean(six))))
        put("SplitBASd", f3(float(np.std(six, ddof=1))))
        assert f3(j["ablation"]["all"]["ba"]) == f3(max(bas)), "text: the primary split tied for the highest BA at three decimals"
        assert j["ablation"]["all"]["onset"]["ba"] > max(ons), "text: and the highest below-level BA"
        rob.insert(0, f"Primary split & {j['n_test_gauges']} & {j['ablation']['all']['ba']:.3f} & "
                   f"{j['ablation']['all']['pr_auc']:.3f} & {j['ablation']['all']['onset']['ba']:.3f}\\\\")
        ng = [v["n_test_gauges"] for v in sp.values()]
        rob.append(f"{len(sp)} other gauge splits & {min(ng)}--{max(ng)} & {min(bas):.3f}--{max(bas):.3f} & {min(prs):.3f}--{max(prs):.3f} & "
                   f"{min(ons):.3f}--{max(ons):.3f}\\\\")
    if "basins" in r and r["basins"]:
        B = r["basins"]
        bas_ = [v["ba"] for v in B.values()]
        prs_ = [v["pr_auc"] for v in B.values()]
        ons_ = [v["onset_ba"] for v in B.values()]
        ngb = [v["n_test_gauges"] for v in B.values()]
        rob.append(f"{len(B)} basin folds & {min(ngb)}--{max(ngb)} & {min(bas_):.3f}--{max(bas_):.3f} & {min(prs_):.3f}--{max(prs_):.3f} & "
                   f"{min(ons_):.3f}--{max(ons_):.3f}\\\\")
        put("BasinN", str(len(B)))
        put("BasinCount", str(sum(len(v["basins"]) for v in B.values())))
        put("BasinOnMin", f3(min(ons_)))
        put("BasinOnMax", f3(max(ons_)))
        worst = min(B.values(), key=lambda v: v["ba"])
        put("BasinWorst", ", ".join(worst["basins"]))
        put("BasinBAMin", f3(min(v["ba"] for v in B.values())))
        put("BasinBAMax", f3(max(v["ba"] for v in B.values())))
        put("BasinPRMin", f3(min(v["pr_auc"] for v in B.values())))
        put("BasinPRMax", f3(max(v["pr_auc"] for v in B.values())))
    for k, lab_ in (("q99", "99th-percentile level$^\\ast$"),):
        if k in R:
            v = R[k]
            rob.append(f"{lab_} & {v['n_test_gauges']} & {v['ba']:.3f} & {v['pr_auc']:.3f} & {v['onset_ba']:.3f}\\\\")
    if "met_only" in R:
        vm = R["met_only"]
        n_met = sum(j["groups"][g_] for g_ in ("rain", "weather", "soil", "season"))
        with open(out / "tab_abl.tex", "a", encoding="utf-8") as fh:  # same 500k sample as the ablation
            fh.write(f"\nMeteorology + season & {n_met} & {vm['ba']:.3f} & {vm['pr_auc']:.3f} & {vm['recall']:.3f} & "
                     f"{vm['onset_ba']:.3f}\\\\")
        put("MetBA", f3(R["met_only"]["ba"]))
        put("MetOnBA", f3(R["met_only"]["onset_ba"]))
        put("MetPR", f3(R["met_only"]["pr_auc"]))
    if "q99" in R:
        put("QnnBA", f3(R["q99"]["ba"]))
        put("QnnPR", f3(R["q99"]["pr_auc"]))
        put("QnnPrev", f"{100 * R['q99']['prev']:.1f}")
        put("QnnPrec", f3(R["q99"]["precision"]))
        put("QnnOnBA", f3(R["q99"]["onset_ba"]))
    if "no_class_weight" in R:
        put("NcwEce", f3(R["no_class_weight"]["ece_raw"]))
        put("NcwBA", f3(R["no_class_weight"]["ba"]))
        assert abs(R["no_class_weight"]["ba"] - j["ablation"]["all"]["ba"]) < 0.01, \
            "text: the unweighted refit matched the selected model in balanced accuracy"
        assert R["no_class_weight"]["ba"] >= j["methods"]["xgboost"]["ba"], "text: the unweighted refit was at least as good in BA"
        if R["no_class_weight"]["ece_raw"] < 0.5 * j["calibration"]["ece_raw"]:
            put("NcwText", (f"When the model was refit without the positive-class weight, its raw ECE was "
                            f"{R['no_class_weight']['ece_raw']:.3f}, so the weighting explains most of the over-confidence."))
        else:
            put("NcwText", (f"Refit without the positive-class weight, the raw ECE was still "
                            f"{R['no_class_weight']['ece_raw']:.3f}, so the weighting does not explain the over-confidence."))
    else:
        put("NcwText", "")
    (out / "tab_robust.tex").write_text("\n".join(rob), encoding="utf-8")

    # ---- candidate models on validation
    names = {"logistic_regression": "Logistic regression", "random_forest": "Random forest",
             "hist_gradient_boosting": "Hist. gradient boosting", "xgboost_d4": "XGBoost, depth 4",
             "xgboost_d6": "XGBoost, depth 6", "xgboost_d8": "XGBoost, depth 8",
             "xgboost_d6_full": "XGBoost, depth 6, all rows"}
    cand = []
    for k, nm in names.items():
        v = ev["candidates"][k]["validation"]
        cand.append(f"{nm} & {v['balanced_accuracy']:.3f} & {v['pr_auc']:.3f}\\\\")
    (out / "tab_cand.tex").write_text("\n".join(cand), encoding="utf-8")
    lr = ev["candidates"]["logistic_regression"]["validation"]
    sel = ev["candidates"]["xgboost_d6_full"]["validation"]
    put("CandLrBA", f3(lr["balanced_accuracy"]))
    put("CandLrPR", f3(lr["pr_auc"]))
    put("CandSelBA", f3(sel["balanced_accuracy"]))
    put("CandSelPR", f3(sel["pr_auc"]))
    put("CandGainPR", f"{100 * (sel['pr_auc'] - lr['pr_auc']):.1f}")
    vba = [ev["candidates"][k]["validation"]["balanced_accuracy"] for k in names]
    assert min(vba) == lr["balanced_accuracy"] and max(vba) == sel["balanced_accuracy"], \
        "text: all seven candidates lie between logistic regression and the selected model"
    return r
