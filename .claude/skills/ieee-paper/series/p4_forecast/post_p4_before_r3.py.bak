"""p4.json (+ models/flood_evaluation_v4.json) -> nums.tex, tab_*.tex, fig_pr.pdf.
Asserts every directional claim made in paper.tex. usage: post_p4.py <work> <out>"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# IEEE: TrueType (Type 42) fonts only, Times for text and math
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "mathtext.fontset": "stix", "pdf.fonttype": 42, "ps.fonttype": 42})

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
WORK, OUT = Path(sys.argv[1]), Path(sys.argv[2])
j = json.loads((WORK / "p4.json").read_text(encoding="utf-8"))
meta = json.loads((ROOT / "models" / "flood_model_metadata_v4.json").read_text(encoding="utf-8"))
M = {}


def put(k, v):
    M[k] = v


m, b, a = j["methods"], j["bootstrap"], j["ablation"]
f3 = lambda x: f"{x:.3f}"
put("NTrainGauges", str(meta["gauges_used"] - len(meta["unseen_gauges"])))
put("NTestGauges", str(j["n_test_gauges"]))
put("NGauges", str(meta["gauges_used"]))
# fit time per ablation model, read from the experiment log (wall clock, laptop CPU, 4 threads)
import re  # noqa: E402

tl = [int(x) for x in re.findall(r"\[\s*(\d+)s\] (?:baselines done|ablation)", (WORK / "p4.log").read_text(encoding="utf-8"))]
assert len(tl) == 7, "log has the baseline line and six ablation lines"
put("AblMinutes", f"{np.median(np.diff(tl)) / 60:.1f}")
assert len(meta["unseen_gauges"]) == 49
assert meta["gauges_skipped"] == [] and meta["gauges_used"] == 242, "text: all 242 gauges in the file are used"
put("NTrainRows", f"{meta['n_train_available']:,}")
put("NValRows", f"{meta['n_val']:,}")
put("NTestRows", f"{j['n_test']:,}")
put("PosRate", f"{100 * j['pos_rate']:.1f}")
put("NFeat", str(len(meta["features"])))
put("Thr", f"{meta['decision_threshold']:.2f}")
for k, v in j["groups"].items():
    put("Group" + k.capitalize(), str(v))
for key, tag in (("xgboost", "Xgb"), ("persistence", "Pers"), ("climatology", "Clim"), ("lstm_sim", "Lstm"),
                 ("xgb_no_flow", "NoFlow")):
    put(f"{tag}BA", f3(m[key]["ba"]))
    put(f"{tag}PR", f3(m[key]["pr_auc"]))
    put(f"{tag}Rec", f3(m[key]["recall"]))
    put(f"{tag}Prec", f3(m[key]["precision"]))
    put(f"{tag}BALo", f3(b[key]["ba"][0]))
    put(f"{tag}BAHi", f3(b[key]["ba"][1]))
put("DiffPersLo", f3(b["persistence"]["diff_ba"][0]))
put("DiffPersHi", f3(b["persistence"]["diff_ba"][1]))
put("LstmCov", f"{100 * j['lstm_coverage']:.0f}")

# the LSTM comparison sentence is chosen by the data, not written in advance
xl, ll = m["xgboost_on_lstm_rows"], m["lstm_sim"]
dlo, dhi = b["lstm_sim"]["diff_ba"]
if dlo > 0:
    s = (f"Even so, on the rows it covers the model's balanced accuracy ({xl['ba']:.3f}) was higher than the "
         f"simulation's ({ll['ba']:.3f}), and the bootstrap interval of the difference excluded zero.")
elif dhi < 0:
    s = (f"On the rows it covers, the simulation reached a balanced accuracy of {ll['ba']:.3f} against "
         f"{xl['ba']:.3f} for the model, as expected from its access to future rain.")
else:
    s = (f"On the rows it covers, the model ({xl['ba']:.3f}) and the simulation ({ll['ba']:.3f}) were "
         f"statistically indistinguishable in balanced accuracy, although only the model is a real forecast.")
put("LstmCompare", s)

# main table
rows = []
lab = {"xgboost": "XGBoost (ours)", "xgb_no_flow": "No-flow XGB.", "lstm_sim": "LSTM sim.$^\\dagger$",
       "climatology": "Climatology", "persistence": "Persistence"}
for k in ("xgboost", "xgb_no_flow", "lstm_sim", "climatology", "persistence"):
    r = m[k]
    rows.append(f"{lab[k]} & {r['ba']:.3f} & {b[k]['ba'][0]:.3f}--{b[k]['ba'][1]:.3f} & {r['pr_auc']:.3f} & "
                f"{r['recall']:.3f} & {r['precision']:.3f} & {r['f1']:.3f}\\\\")
(OUT / "tab_main.tex").write_text("\n".join(rows), encoding="utf-8")

# ablation table
names = {"all": "All inputs", "no_flow": "No streamflow", "no_static": "No catchment", "no_soil": "No soil moisture",
         "no_rain": "No rainfall", "flow_only": "Streamflow + season"}
arow = [f"{names[k]} & {v['n_features']} & {v['ba']:.3f} & {v['pr_auc']:.3f} & {v['recall']:.3f} & "
        f"{v['onset']['ba']:.3f}\\\\" for k, v in a.items()]
(OUT / "tab_abl.tex").write_text("\n".join(arow), encoding="utf-8")
put("AblAllBA", f3(a["all"]["ba"]))
put("AblAllPR", f3(a["all"]["pr_auc"]))
put("NoFlowPR", f3(a["no_flow"]["pr_auc"]))

# operating points
ops = j["operating_points"]
(OUT / "tab_ops.tex").write_text("\n".join(f"{o['thr']:.2f} & {o['recall']:.3f} & {o['precision']:.3f} & "
                                           f"{o['alarms_per_1000']:.1f}\\\\" for o in ops), encoding="utf-8")
o_thr = min(ops, key=lambda o: abs(o["thr"] - meta["decision_threshold"]))
o75 = [o for o in ops if abs(o["thr"] - 0.75) < 1e-9][0]
put("AlarmsThr", f"{o_thr['alarms_per_1000']:.1f}")
put("PrecSeventyFive", f3(o75["precision"]))
put("RecSeventyFive", f3(o75["recall"]))
c = j["calibration"]
put("EceRaw", f3(c["ece_raw"]))
put("EceIso", f3(c["ece_iso"]))
over = np.average([x["conf"] - x["freq"] for x in c["bins_raw"]], weights=[x["n"] for x in c["bins_raw"]])
put("CalWord", "over-confident" if over > 0.01 else ("under-confident" if over < -0.01 else "close to calibrated"))
pg = j["per_gauge"]["xgboost"]
put("PgN", str(pg["n"]))
put("PgMed", f3(pg["median"]))
put("PgQOne", f3(pg["q1"]))
put("PgQThree", f3(pg["q3"]))
put("PgMin", f3(pg["min"]))
e = j["events"]
put("EvN", str(e["n"]))
for k, tag in (("xgboost", "Xgb"), ("lstm_sim", "Lstm"), ("climatology", "Clim"), ("persistence", "Pers"),
               ("xgb_no_flow", "NoFlow")):
    put(f"Ev{tag}Warn", f"{e[k]['warned_pct']:.1f}")
assert e["xgb_no_flow"]["warned_pct"] > e["xgboost"]["warned_pct"], "text: no-flow variant warns of more onsets"

# evaluation protocol vs measured skill (exp_p4_leak.py: same features, thresholds and model; only the split changes)
L = json.loads((WORK / "p4_leak.json").read_text(encoding="utf-8"))["protocols"]
PL = {"random": "Random rows", "time": "New years", "space": "New gauges", "space_time": "New gauges and years"}
lrow = [f"{PL[k]} & {L[k]['n_gauges']} & {100 * L[k]['pos_rate']:.1f} & {L[k]['ba']:.3f} & {L[k]['ba_ci'][0]:.3f}--{L[k]['ba_ci'][1]:.3f} & "
        f"{L[k]['pr_auc']:.3f} & {L[k]['precision']:.3f}\\\\" for k in PL]
(OUT / "tab_leak.tex").write_text("\n".join(lrow), encoding="utf-8")
for k, tag in (("random", "Rand"), ("time", "Time"), ("space", "Space"), ("space_time", "SpTi")):
    put(f"Leak{tag}BA", f3(L[k]["ba"]))
    put(f"Leak{tag}PR", f3(L[k]["pr_auc"]))
gap_ba = L["random"]["ba"] - L["space_time"]["ba"]
gap_pr = L["random"]["pr_auc"] - L["space_time"]["pr_auc"]
put("LeakGapBA", f"{100 * gap_ba:.1f}")
put("LeakGapPR", f"{100 * gap_pr:.1f}")
best = max(PL, key=lambda k: L[k]["pr_auc"])
worst = min(PL, key=lambda k: L[k]["pr_auc"])
if L["random"]["ba_ci"][0] > L["space_time"]["ba_ci"][1]:
    lt = (f"The random row split gave the highest balanced accuracy, {M['LeakRandBA']}, against {M['LeakSpTiBA']} on "
          f"unseen gauges in later years; the two bootstrap intervals ({L['random']['ba_ci'][0]:.4f}--{L['random']['ba_ci'][1]:.4f} "
          f"and {L['space_time']['ba_ci'][0]:.4f}--{L['space_time']['ba_ci'][1]:.4f}) only just separate, and they come "
          f"from different test sets, so the gap is indicative rather than tested. Random splitting inflated "
          f"balanced accuracy by {M['LeakGapBA']} points and PR-AUC by {M['LeakGapPR']} points.")
elif gap_ba > 0:
    lt = (f"The random row split gave a balanced accuracy of {M['LeakRandBA']} against {M['LeakSpTiBA']} on unseen gauges "
          f"in later years, {M['LeakGapBA']} points higher, but the bootstrap intervals overlap, so on this task the "
          f"inflation is smaller than the variation between gauges.")
else:
    lt = (f"The random row split did not inflate balanced accuracy here ({M['LeakRandBA']} against {M['LeakSpTiBA']}); "
          f"with flood thresholds fixed from training years and features scaled per gauge, the leakage that a random "
          f"split allows carried little information on this task.")
lt += (f" PR-AUC ranged from {L[worst]['pr_auc']:.3f} ({PL[worst].lower()}) to {L[best]['pr_auc']:.3f} "
       f"({PL[best].lower()}).")
if L["time"]["pr_auc"] < L["space"]["pr_auc"]:
    lt += (f" Holding out later years lowered PR-AUC more than holding out gauges ({L['time']['pr_auc']:.3f} against "
           f"{L['space']['pr_auc']:.3f}), so a temporal split matters at least as much as a spatial one. In the "
           f"spatial protocol, the test years are also the years from which each gauge's flood threshold was "
           f"computed.")
assert gap_pr > gap_ba, "text: PR-AUC inflated more than balanced accuracy"
lt += (f" Flood prevalence differs between protocols ({100 * L['random']['pos_rate']:.1f}\% of random rows against "
       f"{100 * L['space_time']['pos_rate']:.1f}\% in the held-out test), which moves PR-AUC on its own.")
put("LeakText", lt)
if L["random"]["ba_ci"][0] > L["space_time"]["ba_ci"][1]:
    put("LeakDiscuss", (f"the evaluation protocol alone moved balanced accuracy by {M['LeakGapBA']} points "
                        f"(Table~\\ref{{tab:leak}}), so scores from random row splits overstate what a forecaster will "
                        f"achieve at a new gauge, and published Indian flood models can only be compared under the "
                        f"same split."))
    put("LeakConclude", f"A random row split would have reported a balanced accuracy {M['LeakGapBA']} points higher.")
elif gap_ba > 0:
    put("LeakDiscuss", (f"a random row split scored {M['LeakGapBA']} points higher in balanced accuracy "
                        f"(Table~\\ref{{tab:leak}}), a gap within the variation between gauges, so the protocol "
                        f"should still be reported with every score."))
    put("LeakConclude", "A random row split scored somewhat higher, within the variation between gauges.")
else:
    put("LeakDiscuss", (f"on this task a random row split did not inflate the score (Table~\\ref{{tab:leak}}), "
                        f"because thresholds and feature scaling come from training years only; the held-out "
                        f"protocol remains the one that matches deployment."))
    put("LeakConclude", "A random row split did not inflate the score once thresholds came from training years only.")
assert m["lstm_sim"]["precision"] < 0.5, "text: even the LSTM with future rain has low precision"
if L["random"]["ba_ci"][0] > L["space_time"]["ba_ci"][1]:
    put("LeakAbstract", (f"Scoring the same model on random rows raised balanced accuracy to {M['LeakRandBA']}, an "
                         f"inflation of {M['LeakGapBA']} points."))
elif gap_ba > 0:
    put("LeakAbstract", f"A random row split scored {M['LeakGapBA']} points higher, within the gauge-to-gauge variation.")
else:
    put("LeakAbstract", "A random row split did not inflate the score once thresholds came from training years only.")

# where the forecaster succeeds and fails (exp_p4_extra.py)
E = json.loads((WORK / "p4_extra.json").read_text(encoding="utf-8"))
ld = {int(k): v for k, v in E["lead"].items()}
(OUT / "tab_lead.tex").write_text("\n".join(
    f"{h} & {ld[h]['n']} & {100 * ld[h]['recall']:.1f} & {ld[h]['n_rising']} & {100 * ld[h]['recall_rising']:.1f}\\\\"
    for h in (1, 2, 3)), encoding="utf-8")
assert ld[1]["recall"] > ld[2]["recall"] > ld[3]["recall"], "text: recall falls with lead"
assert ld[1]["recall_rising"] > ld[2]["recall_rising"] > ld[3]["recall_rising"], "text: also on rising rivers"
assert all(ld[h]["recall_rising"] < ld[h]["recall"] for h in ld), "text: rising floods are harder"
for h, w in ((1, "One"), (2, "Two"), (3, "Three")):
    put(f"Lead{w}", f"{100 * ld[h]['recall']:.1f}")
    put(f"Lead{w}Rise", f"{100 * ld[h]['recall_rising']:.1f}")
S = E["season"]
mo, ot = S["monsoon"], S["other"]
(OUT / "tab_season.tex").write_text("\n".join(
    f"{lab} & {v['n']:,} & {100 * v['pos_rate']:.1f} & {v['ba']:.3f} & {v['recall']:.3f} & {v['precision']:.3f} & "
    f"{v['alarms_per_1000']:.0f}\\\\" for lab, v in (("Jun--Sep", mo), ("Oct--May", ot))), encoding="utf-8")
put("FpMonsoonPct", f"{100 * S['fp_share_monsoon']:.0f}")
put("MonPrec", f3(mo["precision"]))
put("OthPrec", f3(ot["precision"]))
put("MonAlarms", f"{mo['alarms_per_1000']:.0f}")
put("OthAlarms", f"{ot['alarms_per_1000']:.0f}")
assert S["fp_share_monsoon"] > 0.8 and mo["precision"] < ot["precision"], "text: false alarms are a monsoon problem"
put("NearMissMon", f"{100 * mo['near_miss_share']:.0f}")
put("FaRatioMon", f"{100 * mo['fa_median_ratio']:.0f}")
assert mo["near_miss_share"] < 0.5 and mo["fa_median_ratio"] < 0.5, "text: most monsoon false alarms are not near misses"
sp = E["spearman"]
put("PgGauges", str(len(E["gauges"])))
put("RhoArea", f"{sp['log_area']['rho']:.2f}")
put("PArea", f"{sp['log_area']['p']:.3f}")
put("PMinOther", f"{min(sp[k]['p'] for k in ('aridity', 'p_mean', 'slope')):.2f}")
assert sp["log_area"]["rho"] > 0 and sp["log_area"]["p"] < 0.01, "text: larger catchments are easier"
assert all(sp[k]["p"] > 0.5 for k in ("aridity", "p_mean", "slope")), "text: no link with aridity, rain or slope"

# warning lead before flood onsets
EVL = {"xgboost": "XGBoost (ours)", "xgb_no_flow": "No-flow XGB.", "lstm_sim": "LSTM sim.$^\\dagger$",
       "climatology": "Climatology"}
wrow = []
for k, lb in EVL.items():
    hst = {int(a_): b_ for a_, b_ in e[k]["lead_hist"].items()}
    tot = sum(hst.values())
    wrow.append(f"{lb} & " + " & ".join(f"{100 * hst[L_] / tot:.1f}" for L_ in (3, 2, 1, 0)) +
                f" & {e[k]['mean_lead_warned']:.2f}\\\\")
(OUT / "tab_warn.tex").write_text("\n".join(wrow), encoding="utf-8")
h3 = {k: 100 * {int(a_): b_ for a_, b_ in e[k]["lead_hist"].items()}[3] / e["n"] for k in EVL}
put("WarnThreeXgb", f"{h3['xgboost']:.1f}")
put("WarnThreeLstm", f"{h3['lstm_sim']:.1f}")
put("WarnThreeClim", f"{h3['climatology']:.1f}")
put("EvGauges", str(e["gauges"]))
put("MeanLeadXgb", f"{e['xgboost']['mean_lead_warned']:.2f}")
assert h3["climatology"] > h3["xgboost"] and h3["lstm_sim"] > h3["xgboost"], "text: clim and LSTM look better on lead"
assert m["climatology"]["precision"] < 0.5 * m["xgboost"]["precision"] + 0.05, "text: climatology alarms constantly"
assert c["ece_raw"] > 10 * c["ece_iso"], "text: raw probabilities badly calibrated, isotonic fixes"
over_bins = [x for x in c["bins_raw"] if x["n"] >= 50 and x["conf"] > 0.5]
assert all(x["conf"] > x["freq"] for x in over_bins), "text: raw scores over-confident"

# figure: gain importance of the selected model (exp_p4_imp.py)
IM = json.loads((WORK / "p4_imp.json").read_text(encoding="utf-8"))
NICE = {"qr_l0": "flow / $q^{95}$, day $t$", "qr_max7": "7-day max flow / $q^{95}$", "prcp_l0": "rain, day $t$",
        "rh": "relative humidity", "doy_sin": "season (sine)", "pet": "potential evapotransp.",
        "prcp_s3": "3-day rain", "doy_cos": "season (cosine)", "prcp_s30": "30-day rain", "prcp_s14": "14-day rain",
        "qr_m30": "30-day mean flow / $q^{95}$", "p_mean": "mean annual rain"}
topf = sorted(IM["feature"].items(), key=lambda kv: -kv[1])[:10]
assert all(f in NICE for f, _ in topf), "label every plotted feature"
fig, ax = plt.subplots(figsize=(3.45, 1.95))
ax.barh(range(len(topf))[::-1], [100 * v for _, v in topf], color=["0.25" if f.startswith("qr_") else "0.65"
                                                                   for f, _ in topf], height=0.7)
ax.set_yticks(range(len(topf))[::-1])
ax.set_yticklabels([NICE[f] for f, _ in topf], fontsize=6.5)
ax.set_xlabel("share of total gain (%)")
ax.grid(lw=0.3, axis="x")
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_imp.pdf")
plt.close(fig)
gi = IM["group"]
put("ImpFlow", f"{100 * gi['flow']:.1f}")
put("ImpRain", f"{100 * gi['rain']:.1f}")
put("ImpWeather", f"{100 * gi['weather']:.1f}")
put("ImpTopOne", f"{100 * topf[0][1]:.1f}")
put("ImpTopTwo", f"{100 * topf[1][1]:.1f}")
assert topf[0][0] == "qr_l0" and topf[1][0] == "qr_max7" and topf[2][0] == "prcp_l0", "text: top three features"
assert gi["flow"] > 0.5 and gi["rain"] == max(v for k, v in gi.items() if k != "flow"), "text: flow, then rain"
put("ImpRainDay", f"{100 * topf[2][1]:.1f}")

# figure: reliability before and after isotonic recalibration
fig, ax = plt.subplots(figsize=(3.45, 1.9))
for key, mk, col, lb in (("bins_raw", "o-", "0.1", f"raw (ECE {c['ece_raw']:.3f})"),
                         ("bins_iso", "s--", "0.5", f"isotonic (ECE {c['ece_iso']:.3f})")):
    bs_ = [x for x in c[key] if x["n"] >= 50]
    ax.plot([x["conf"] for x in bs_], [x["freq"] for x in bs_], mk, color=col, ms=3, lw=0.9, label=lb)
ax.plot([0, 1], [0, 1], ":", color="0.4", lw=0.6)
ax.set_xlabel("forecast probability (bin mean)")
ax.set_ylabel("observed frequency")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.grid(lw=0.3)
ax.legend(fontsize=6.2, frameon=False, loc="upper left")
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_rel.pdf")
plt.close(fig)
over_hi = [x for x in c["bins_raw"] if x["conf"] > 0.5 and x["n"] >= 50]
put("RelHiConf", f"{over_hi[-1]['conf']:.2f}" if over_hi else "--")
put("RelHiFreq", f"{over_hi[-1]['freq']:.2f}" if over_hi else "--")

# figure: per-gauge balanced accuracy against catchment area
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
fig, ax = plt.subplots(figsize=(3.45, 1.7))
G_ = E["gauges"]
ax.scatter([np.expm1(g["log_area"]) for g in G_], [g["ba"] for g in G_], s=9, facecolors="none", edgecolors="0.1",
           lw=0.6)
ax.set_xscale("log")
ax.set_xlabel("catchment area (km$^2$)")
ax.set_ylabel("balanced accuracy")
ax.grid(lw=0.3)
ax.text(0.02, 0.06, f"Spearman $\\rho$ = {sp['log_area']['rho']:.2f}, $p$ = {sp['log_area']['p']:.3f}",
        transform=ax.transAxes, fontsize=6.5, bbox={"facecolor": "white", "edgecolor": "none", "pad": 1})
assert abs(a["all"]["ba"] - m["xgboost"]["ba"]) < 0.0015, "text: all-input refit scored as the selected model"
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_area.pdf")
plt.close(fig)

# figure: PR curves
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
fig, ax = plt.subplots(figsize=(3.45, 2.2))
sty = {"xgboost": ("-", "0.05", "XGBoost (ours)"), "xgb_no_flow": ("--", "0.35", "XGBoost, no flow"),
       "lstm_sim": ("-.", "0.5", "LSTM sim. (future rain)"), "climatology": (":", "0.3", "Climatology")}
for k, (ls, col, lb) in sty.items():
    cv = j["pr_curves"][k]
    ax.plot(cv["recall"], cv["precision"], ls, color=col, lw=1.0, label=lb)
pp = j["persistence_point"]
ax.plot(pp["recall"], pp["precision"], "s", color="black", ms=4, label="Persistence")
ax.axhline(j["pos_rate"], color="black", lw=0.5, ls=":")
ax.set_xlabel("recall")
ax.set_ylabel("precision")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1.02)
ax.grid(lw=0.3)
ax.legend(fontsize=6.2, frameon=False, loc="center left", bbox_to_anchor=(0.0, 0.47))
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_pr.pdf")

# ---- claims in the text
X = m["xgboost"]
for k in ("persistence", "climatology"):
    assert X["ba"] > m[k]["ba"] and X["recall"] > m[k]["recall"] and X["pr_auc"] > m[k]["pr_auc"], \
        f"text: model beats {k} in BA, recall and PR-AUC"
assert m["persistence"]["precision"] > X["precision"], "text: persistence more precise"
assert b["persistence"]["diff_ba"][0] > 0, "text: BA gain over persistence excludes zero"
assert 0.85 <= X["recall"] < 0.95, "text: 'nine in ten flood windows'"
drops = {k: a["all"]["ba"] - v["ba"] for k, v in a.items() if k.startswith("no_")}
assert max(drops, key=drops.get) == "no_flow", "text: removing streamflow costs the most"
assert all(drops[k] < 0.5 * drops["no_flow"] for k in drops if k != "no_flow"), "text: other groups cost little"
put("OnsetAll", f3(a["all"]["onset"]["ba"]))
put("OnsetNoFlow", f3(a["no_flow"]["onset"]["ba"]))
put("OnsetFlowOnly", f3(a["flow_only"]["onset"]["ba"]))
od_noflow = a["all"]["onset"]["ba"] - a["no_flow"]["onset"]["ba"]
od_flowonly = a["all"]["onset"]["ba"] - a["flow_only"]["onset"]["ba"]
assert od_noflow < 0.25 * drops["no_flow"] and od_flowonly > 3 * od_noflow, \
    "text: on onset rows removing flow costs little, flow alone costs much"
assert a["no_flow"]["ba"] > m["climatology"]["ba"], "text: no-flow variant beats climatology"
assert 0.4 < o75["alarms_per_1000"] / o_thr["alarms_per_1000"] < 0.6, "text: threshold 0.75 about halves alarms"
assert c["ece_iso"] < c["ece_raw"], "text: isotonic lowers ECE"
assert e["persistence"]["warned_pct"] == 0.0, "text: persistence cannot anticipate an onset"
assert e["xgboost"]["warned_pct"] > e["climatology"]["warned_pct"], "text: model warns more often than climatology"

import post_p4_r2  # noqa: E402  second revision: onset columns, LSTM paired test, robustness refits, calibration

post_p4_r2.extend(put, WORK, OUT, ROOT, j)

with open(OUT / "nums.tex", "w", encoding="utf-8") as f:
    for k, v in M.items():
        f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
print("p4 nums:", len(M))
