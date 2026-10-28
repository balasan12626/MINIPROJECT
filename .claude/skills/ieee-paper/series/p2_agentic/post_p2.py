"""p2.json -> nums.tex (every number used in paper.tex) + fig_dual.pdf. Fails if a claim in the text
no longer holds for the data (asserts at the bottom)."""
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

WORK = Path(sys.argv[1])
OUT = Path(sys.argv[2])
j = json.loads((WORK / "p2.json").read_text(encoding="utf-8"))
M = {}


def put(k, v):
    M[k] = v


pol, dual, g = j["policy"], j["dual"], j["guard"]
put("PolCases", f"{pol['cases']:,}")
put("PolViol", str(pol["violations"]))
put("PolAuto", f"{pol['actions']['AUTOMATED_RESPONSE']:,}")
put("PolReview", f"{pol['actions']['HUMAN_REVIEW']:,}")
put("PolMonitor", f"{pol['actions']['MONITOR']:,}")
put("PolOverride", f"{pol['actions']['HUMAN_OVERRIDE']:,}")
put("PolUnavail", f"{pol['actions']['UNAVAILABLE']:,}")
put("PolAutoUnhealthy", str(pol["auto_when_unhealthy"]))
put("PolMs", f"{pol['ms']:.0f}")
e2e = j["e2e"]
put("EtoECases", f"{e2e['cases']:,}")
put("EtoEViolBefore", f"{e2e['viol_before']:,}")
put("EtoEViolAfter", str(e2e["viol_after"]))
put("EtoEFiredBefore", f"{e2e['fired_before']:,}")
put("EtoEFiredAfter", f"{e2e['fired_after']:,}")
assert e2e["viol_after"] == 0 and e2e["viol_before"] > 0, "text: bypass existed and is fixed"
assert e2e["fired_before"] - e2e["fired_after"] == e2e["viol_before"], "text: fix removed exactly the unsafe dispatches"

put("DualN", str(dual["n"]))
put("DualHold", f"{dual['hold_pct']:.1f}")
put("DualGap", f"{dual['gap_pct']:.1f}")
put("DualStraddle", f"{dual['straddle_pct']:.1f}")
put("DualStraddleOnly", f"{dual['straddle_only_pct']:.1f}")
put("DualEligible", str(dual["eligible"]))
put("DualEligibleHeld", f"{dual['eligible_held_pct']:.1f}")
put("DualBoth", str(dual["both_auto"]))
put("DualBothHeld", f"{dual['both_auto_held_pct']:.1f}")
put("DualMeanGap", f"{dual['mean_gap']:.3f}")
put("DualMaxGap", f"{dual['max_gap']:.3f}")
put("DualRfAuto", f"{dual['rf_auto_pct']:.1f}")
put("DualXgbAuto", f"{dual['xgb_auto_pct']:.1f}")

R = g["results"]
put("GuardCtx", str(g["n_ctx"]))
put("GuardFacts", f"{g['facts_numbers_mean']:.1f}")
put("GuardMs", f"{g['ms_per_check']:.1f}")
put("GuardFalseRej", str(R["grounded"]["n"] - R["grounded"]["accepted"]))
for b in ("calm", "watch", "admin", "auto"):
    put("Band" + b.capitalize(), str(g["bands"][b]))
names = {"prob_small": "ProbSmall", "prob_large": "ProbLarge", "rain_rel": "Rain", "river": "River",
         "count": "Count", "eta": "Eta", "words": "Words"}
num = [k for k in names if k != "words"]
for k, nm in names.items():
    for v in ("deployed", "no_scale", "facts_only", "strict"):
        put(f"G{nm}{v.replace('_', '').capitalize()}", f"{100 * R[k][v] / R[k]['n']:.1f}")
tot = lambda v: 100 * sum(R[k][v] for k in num) / sum(R[k]["n"] for k in num)
for v in ("deployed", "no_scale", "facts_only", "strict"):
    put(f"GAll{v.replace('_', '').capitalize()}", f"{tot(v):.1f}")
put("GMissDeployed", f"{100 - tot('deployed'):.1f}")
put("GInjected", f"{sum(R[k]['n'] for k in num):,}")
for k, nm in names.items():
    put(f"G{nm}Typed", f"{100 * R[k]['typed'] / R[k]['n']:.1f}")
put("GAllTyped", f"{100 * sum(R[k]['typed'] for k in num) / sum(R[k]['n'] for k in num):.1f}")
put("GTypedFalseRej", str(R["grounded"]["n"] - R["grounded"]["typed"]))
tm = g["typed_misses"]
put("GTypedMissN", str(len([m for m in tm if m["kind"] != "words"])))
put("GTypedWordMiss", str(len([m for m in tm if m["kind"] == "words"])))

# sensitivity of the dual gate to the gap tolerance delta (recomputed from the stored sweep)
drows = dual["rows"]
trows = []
for delta in (0.10, 0.15, 0.20, 0.25, 0.30, 0.35):
    hold = [r["gap"] >= delta or r["straddle"] for r in drows]
    both = [h for r, h in zip(drows, hold) if r["rf_auto"] and r["xgb_auto"]]
    trows.append((delta, 100 * sum(hold) / len(hold), 100 * sum(both) / max(len(both), 1)))
st_only = 100 * sum(r["straddle"] for r in drows) / len(drows)
lines = [f"{d:.2f} & {h:.1f} & {b:.1f}\\\\" for d, h, b in trows]
lines.append("\\midrule")
lines.append(f"straddle only & {st_only:.1f} & 0.0\\\\")
(OUT / "tab_delta.tex").write_text("\n".join(lines), encoding="utf-8")
put("DeltaStraddleOnly", f"{st_only:.1f}")
put("DeltaThirtyHold", f"{trows[4][1]:.1f}")
put("DeltaThirtyBoth", f"{trows[4][2]:.1f}")
misses = g["misses"]
first = [(m["cause"][0][1] if m["cause"] else "none") for m in misses]
put("GMissN", str(len(misses)))
put("GMissFact", str(first.count("fact")))
put("GMissRule", str(first.count("rule")))
put("GMissScale", str(first.count("scale")))
eta_prob = sum(1 for m in misses if m["kind"] == "eta" and m["cause"] and m["cause"][0][1] == "fact")
put("GMissEtaFact", str(eta_prob))

# Fig.: hold rate against delta on a fine grid (same stored sweep)
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
grid_d = [round(0.05 + 0.01 * i, 2) for i in range(36)]
h_all, h_both = [], []
both_rows = [r for r in drows if r["rf_auto"] and r["xgb_auto"]]
for dl in grid_d:
    h_all.append(100 * sum(r["gap"] >= dl or r["straddle"] for r in drows) / len(drows))
    h_both.append(100 * sum(r["gap"] >= dl or r["straddle"] for r in both_rows) / len(both_rows))
fig, ax = plt.subplots(figsize=(3.45, 1.7))
ax.plot(grid_d, h_all, "-", color="0.05", lw=1.0, label="all settings")
ax.plot(grid_d, h_both, "--", color="0.45", lw=1.0, label="both models $\\geq\\tau_a$")
ax.axhline(st_only, color="black", lw=0.5, ls=":")
ax.axvline(0.15, color="0.6", lw=0.5)
ax.text(0.152, 92, "deployed $\\delta$", fontsize=6)
ax.set_xlabel("gap tolerance $\\delta$")
ax.set_ylabel("dispatch held (%)")
ax.set_ylim(0, 100)
ax.legend(fontsize=6.3, frameon=False, loc="upper right")
ax.grid(lw=0.3)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_delta.pdf")
d_zero = next(dl for dl, hb in zip(grid_d, h_both) if hb == 0.0)
put("DeltaZeroBoth", f"{d_zero:.2f}")

# worked miss example (first ETA miss) for the text
ex_miss = next(m for m in g["misses"] if m["kind"] == "eta")
put("MissExProb", re.search(r"is ([\d.]+)%", ex_miss["text"][0]).group(1))
put("MissExEta", ex_miss["cause"][0][0])
assert ex_miss["cause"][0][1] == "fact"

# Fig.: detection by error type, deployed vs typed guard
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
labels_e = ["prob ±1–5", "prob ±10–30", "rain", "river", "count", "ETA", "words"]
keys_e = ["prob_small", "prob_large", "rain_rel", "river", "count", "eta", "words"]
fig, ax = plt.subplots(figsize=(3.45, 1.75))
xs = range(len(keys_e))
ax.bar([x - 0.2 for x in xs], [100 * R[k]["deployed"] / R[k]["n"] for k in keys_e], 0.4, color="0.75",
       edgecolor="black", lw=0.5, label="deployed $\\Gamma$")
ax.bar([x + 0.2 for x in xs], [100 * R[k]["typed"] / R[k]["n"] for k in keys_e], 0.4, color="0.2",
       edgecolor="black", lw=0.5, label="typed $\\Gamma_{\\mathrm{T}}$")
ax.set_xticks(list(xs))
ax.set_xticklabels(labels_e, fontsize=6.3, rotation=20)
ax.set_ylabel("detected (%)")
ax.set_ylim(0, 105)
ax.legend(fontsize=6.3, frameon=False, loc="lower left")
ax.grid(axis="y", lw=0.3)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_guard.pdf")

import post_p2_v2  # noqa: E402  revision: live LLM study, LLM judge, held-out calibration

_, det = post_p2_v2.extend(put, WORK, OUT, R)
# Wilson 95% half-widths of the judge column of the injected-error table (40 replies per row)
half = []
for kind, vals in det.items():
    k_, n_ = round(vals[2] * 40 / 100), 40
    lo_, hi_ = post_p2_v2.wilson(k_, n_)
    half.append(max(100 * k_ / n_ - lo_, hi_ - 100 * k_ / n_))
put("JudgeCiMax", f"{max(half):.0f}")
import post_p2_r2  # noqa: E402  second revision: prompt designs, over-claims, paired tests, gate cost

post_p2_r2.extend(put, WORK, OUT)
import post_p2_r3  # noqa: E402  third revision: taxonomy, clustered bootstrap, guard ablation, Eq. (4), break-even

post_p2_r3.extend(put, WORK, OUT)
C2 = json.loads((WORK / "p2_calib.json").read_text(encoding="utf-8"))
assert abs(d_zero - C2["delta95_cv"]) < 0.05, "text: delta_95 close to the sweep's zero point for both-agree holds"

with open(OUT / "nums.tex", "w", encoding="utf-8") as f:
    for k, v in M.items():
        f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")

# ---- Fig. 2: RF vs XGBoost probability over rainfall, July, with hold regions
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
rows = [r for r in dual["rows"] if r["month"] == 7]
x = [r["rain"] for r in rows]
fig, ax = plt.subplots(figsize=(3.45, 2.0))
for r in rows:
    if r["hold"]:
        ax.axvspan(r["rain"] - 1, r["rain"] + 1, color="0.88", lw=0)
ax.plot(x, [r["rf"] for r in rows], "-", color="0.15", lw=1.0, label="Random Forest")
ax.plot(x, [r["xgb"] for r in rows], "--", color="0.45", lw=1.0, label="XGBoost")
ax.axhline(dual["auto_t"], color="black", lw=0.5, ls=":")
ax.text(296, dual["auto_t"] + 0.015, "auto threshold", ha="right", fontsize=6.5)
ax.set_xlim(0, 300)
ax.set_ylim(0, 1.02)
ax.set_xlabel("24-h rainfall (mm), July")
ax.set_ylabel("Flood probability")
ax.legend(fontsize=6.5, loc="lower right", frameon=False)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_dual.pdf")

# ---- claims made in the text
assert pol["violations"] == 0 and pol["monotone_healthy"] and pol["auto_when_unhealthy"] == 0
assert dual["mean_gap"] > dual["gap_max"], "text says mean gap exceeds tolerance"
assert dual["both_auto_held_pct"] > 50, "text says most both-auto cases are held"
assert R["words"]["deployed"] == 0, "text says words are never caught"
assert R["grounded"]["accepted"] == R["grounded"]["n"], "text says no false rejections"
assert tot("strict") >= tot("deployed"), "text says strict matching catches at least as many"
assert first.count("none") == 0, "every miss should be explained by a collision"
typed_all = sum(R[k]["typed"] for k in num) / sum(R[k]["n"] for k in num)
assert typed_all > tot("deployed") / 100, "text: typed guard detects more numeric errors"
assert R["words"]["typed"] > R["words"]["deployed"], "text: typed guard catches some number words"
assert R["count"]["typed"] == R["count"]["n"] and R["eta"]["typed"] == R["eta"]["n"], "text: typed catches all counts/ETAs"
assert R["grounded"]["typed"] == R["grounded"]["n"], "text: typed has no false rejections"
assert R["words"]["typed"] > 0.5 * R["words"]["n"], "text: typed catches most number words"
assert {m["kind"] for m in tm} <= {"prob_small", "prob_large", "river", "words"}, "text: typed misses are same-slot"
assert first.count("fact") > first.count("rule") + first.count("scale"), "text says most misses collide with real facts"
print("p2 nums:", len(M))
