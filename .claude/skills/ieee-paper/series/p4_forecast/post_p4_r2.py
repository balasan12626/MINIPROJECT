"""Second-revision numbers for P4 (p4_r2.json, models/flood_evaluation_v4.json) -> macros and tables.

Rewrites tab_main.tex with onset-row BA and PR-AUC for every reference and the trend rule, and writes
tab_robust.tex (other gauge splits, leave-basin-out, 99th percentile, meteorology-only, no class weight) and
tab_cand.tex (the seven candidate models on validation). Called from post_p4.py; asserts every claim in the text.
"""
import json

import numpy as np


def f3(x):
    return f"{x:.3f}"


def extend(put, work, out, root, j):
    r = json.loads((work / "p4_r2.json").read_text(encoding="utf-8"))
    ev = json.loads((root / "models" / "flood_evaluation_v4.json").read_text(encoding="utf-8"))
    M, b = r["methods"], j["bootstrap"]
    # ---- main table: overall and onset rows, every method on the same test rows
    lab = {"xgboost": "XGBoost (ours)", "lstm_sim": "LSTM sim.$^\\dagger$", "trend": "Trend rule",
           "climatology": "Climatology", "persistence": "Persistence"}
    rows = []
    for k in ("xgboost", "lstm_sim", "trend", "climatology", "persistence"):
        v = M[k]
        ci = f"{b[k]['ba'][0]:.3f}--{b[k]['ba'][1]:.3f}" if k in b else "--"
        rows.append(f"{lab[k]} & {v['ba']:.3f} & {ci} & {v['pr_auc']:.3f} & {v['recall']:.3f} & {v['precision']:.3f} & "
                    f"{v['onset_ba']:.3f} & {v['onset_pr_auc']:.3f}\\\\")
    nf = j["methods"]["xgb_no_flow"]
    rows.insert(1, f"No-flow XGB. & {nf['ba']:.3f} & {b['xgb_no_flow']['ba'][0]:.3f}--{b['xgb_no_flow']['ba'][1]:.3f} & "
                   f"{nf['pr_auc']:.3f} & {nf['recall']:.3f} & {nf['precision']:.3f} & {nf['onset']['ba']:.3f} & "
                   f"{nf['onset']['pr_auc']:.3f}\\\\")
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
    rg = r["regulation"]
    put("RegRho", f"{rg['rho_num_dams']:.2f}")
    put("RegP", f"{rg['p_num_dams']:.2f}")
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
        rob.append(f"{len(sp)} other gauge splits & range & {min(bas):.3f}--{max(bas):.3f} & {min(prs):.3f}--{max(prs):.3f} & "
                   f"{min(ons):.3f}--{max(ons):.3f}\\\\")
    if "basins" in r and r["basins"]:
        B = r["basins"]
        bas_ = [v["ba"] for v in B.values()]
        prs_ = [v["pr_auc"] for v in B.values()]
        ons_ = [v["onset_ba"] for v in B.values()]
        rob.append(f"{len(B)} basin folds & range & {min(bas_):.3f}--{max(bas_):.3f} & {min(prs_):.3f}--{max(prs_):.3f} & "
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
    for k, lab_ in (("q99", "99th-percentile level"), ("met_only", "meteorology + season only"),
                    ("no_class_weight", "no class weight")):
        if k in R:
            v = R[k]
            rob.append(f"{lab_} & {v['n_test_gauges']} & {v['ba']:.3f} & {v['pr_auc']:.3f} & {v['onset_ba']:.3f}\\\\")
    if "met_only" in R:
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
        if R["no_class_weight"]["ece_raw"] < 0.5 * j["calibration"]["ece_raw"]:
            put("NcwText", (f"Refit without the positive-class weight, the model's raw ECE was "
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
    return r
