"""p3.json -> nums.tex, tab_policy.tex, tab_event.tex, tab_mu.tex, fig_tradeoff.pdf. Asserts text claims."""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

WORK, OUT = Path(sys.argv[1]), Path(sys.argv[2])
j = json.loads((WORK / "p3.json").read_text(encoding="utf-8"))
cfg, runs = j["config"], j["runs"]
M = {}


def put(k, v):
    M[k] = v


def f1(x):
    return "--" if x is None else f"{x:.1f}"


def f2(x):
    return "--" if x is None else f"{x:.2f}"


base = runs["mu0_cold"]["summary"]
warm = runs["mu0_warm"]["summary"]
put("Seeds", str(cfg["seeds"]))
put("Shots", str(cfg["shots"]))
put("SeedsLast", str(cfg["seeds"] - 1))
put("Depth", str(cfg["p"]))
put("NEvents", str(base["n_events"]))
put("NReplans", str(base["n_replans"]))
put("NNoChange", str(base["no_change_events"]))
put("NInfeasible", str(base["infeasible_events"]))
P = {"raw": "Raw", "verified": "Verified", "portfolio": "Portfolio", "classical": "Classical", "oracle": "Oracle"}
for p, n in P.items():
    s = base[p]
    put(n + "Invalid", f1(s["dispatched_invalid_pct"]))
    put(n + "Valid", f1(s["valid_when_feasible_pct"]))
    put(n + "Esc", str(s["escalations"]))
    put(n + "CorrEsc", str(s["correct_escalations"]))
    put(n + "Opt", f1(s["opt_pct"]))
    put(n + "Gap", f2(s["mean_gap_min"]))
    put(n + "Churn", f2(s["mean_churn"]))
    put(n + "Ms", f1(s["mean_ms"]))
    put(n + "Nfev", f"{s['mean_nfev']:.0f}")
    put(n + "Fallback", f1(s["fallback_pct"]))
    put(n + "GreedyWon", f1(s["greedy_won_pct"]))
put("WarmNfev", f"{warm['verified']['mean_nfev']:.0f}")
put("ColdNfev", f"{base['verified']['mean_nfev']:.0f}")
put("WarmOpt", f1(warm["verified"]["opt_pct"]))
put("ColdOpt", f1(base["verified"]["opt_pct"]))
put("WarmMs", f1(warm["verified"]["mean_ms"]))
put("ColdMs", f1(base["verified"]["mean_ms"]))
put("WarmFallback", f1(warm["verified"]["fallback_pct"]))
put("NfevSaving", f"{100 * (1 - warm['verified']['mean_nfev'] / base['verified']['mean_nfev']):.0f}")

rows = []
names = {"raw": "QAOA top sample, unverified", "verified": "QAOA + verifier + fallback",
         "portfolio": "Portfolio (QAOA $\\|$ greedy)", "classical": "Greedy + exact fallback", "oracle": "Exhaustive (oracle)"}
log0 = [r for r in runs["mu0_cold"]["log"] if r.get("replanned")]
opt_all = {p: 100 * sum(1 for r in log0 if r[p]["gap_obj"] is not None and abs(r[p]["gap_obj"]) < 1e-6) / len(log0)
           for p in names}
put("RawOptAll", f1(opt_all["raw"]))
for p in ("verified", "portfolio", "classical", "oracle"):
    assert abs(opt_all[p] - base[p]["opt_pct"]) < 1e-9, "opt over all re-plans equals opt over valid ones"
for p, lab in names.items():
    s = base[p]
    rows.append(f"{lab} & {f1(s['dispatched_invalid_pct'])} & {s['escalations']} & {f1(opt_all[p])} & "
                f"{f2(s['mean_gap_min'])} & {f1(s['mean_ms'])}\\\\")
(OUT / "tab_policy.tex").write_text("\n".join(rows), encoding="utf-8")

rows = []
for ev, d in base["by_event"].items():
    rows.append(f"{ev} & {d['replans']} & {d['infeasible']} & {d['raw_invalid']}\\\\")
(OUT / "tab_event.tex").write_text("\n".join(rows), encoding="utf-8")

mus = [("mu0_warm", 0), ("mu3_warm", 3), ("mu6_warm", 6)]
rows, pts = [], {"verified": [], "oracle": []}
for key, mu in mus:
    s = runs[key]["summary"]
    rows.append(f"{mu} & {f2(s['verified']['mean_churn'])} & {f2(s['verified']['mean_travel'])} & "
                f"{f2(s['oracle']['mean_churn'])} & {f2(s['oracle']['mean_travel'])}\\\\")
    for p in pts:
        pts[p].append((s[p]["mean_travel"], s[p]["mean_churn"], mu))
    put(f"OracleChurnMu{['Zero', 'Three', 'Six'][mus.index((key, mu))]}", f2(s["oracle"]["mean_churn"]))
    put(f"OracleTravelMu{['Zero', 'Three', 'Six'][mus.index((key, mu))]}", f2(s["oracle"]["mean_travel"]))
    put(f"VerChurnMu{['Zero', 'Three', 'Six'][mus.index((key, mu))]}", f2(s["verified"]["mean_churn"]))
    put(f"VerTravelMu{['Zero', 'Three', 'Six'][mus.index((key, mu))]}", f2(s["verified"]["mean_travel"]))
(OUT / "tab_mu.tex").write_text("\n".join(rows), encoding="utf-8")

# all four configurations side by side
cfgs = [("mu0_cold", "0", "cold"), ("mu0_warm", "0", "memory"), ("mu3_warm", "3", "memory"), ("mu6_warm", "6", "memory")]
rows = []
for key, mu, st in cfgs:
    s = runs[key]["summary"]
    rows.append(f"{mu} & {st} & {f1(s['raw']['dispatched_invalid_pct'])} & {f1(s['verified']['opt_pct'])} & "
                f"{f1(s['portfolio']['opt_pct'])} & {f1(s['classical']['opt_pct'])} & {s['verified']['mean_nfev']:.0f}\\\\")
(OUT / "tab_cfg.tex").write_text("\n".join(rows), encoding="utf-8")
raw_inv = [runs[k]["summary"]["raw"]["dispatched_invalid_pct"] for k, _, _ in cfgs]
put("RawInvMuSix", f1(raw_inv[-1]))
put("RawInvWarm", f1(raw_inv[1]))
put("PortOptMuSix", f1(runs["mu6_warm"]["summary"]["portfolio"]["opt_pct"]))
put("VerOptMuSix", f1(runs["mu6_warm"]["summary"]["verified"]["opt_pct"]))
put("VerOptMuThree", f1(runs["mu3_warm"]["summary"]["verified"]["opt_pct"]))
put("ClsOptMuSix", f1(runs["mu6_warm"]["summary"]["classical"]["opt_pct"]))
put("RawOpt", f1(base["raw"]["opt_pct"]))
put("VerChurnCold", f2(base["verified"]["mean_churn"]))
put("OracleChurnCold", f2(base["oracle"]["mean_churn"]))
ev = base["by_event"]
put("RawInvEtwo", str(ev["E2 Shelter A surge"]["raw_invalid"]))
put("RawInvEthree", str(ev["E3 extra closure"]["raw_invalid"]))
put("RawInvEfour", str(ev["E4 Shelter A failed"]["raw_invalid"]))

# per-event optimality from the episode log (cold, mu = 0)
log = runs["mu0_cold"]["log"]
rows = []
for k, e in enumerate(evs_names := list(base["by_event"])):
    rr = [r for r in log if r.get("replanned") and r["event"] == k]
    cells = []
    for p in ("raw", "verified", "portfolio", "classical"):
        ok = [abs(r[p]["gap_obj"]) < 1e-6 for r in rr if r[p]["gap_obj"] is not None]
        cells.append(f"{100 * sum(ok) / len(rr):.1f}")
    fb = sum(1 for r in rr if r["verified"]["how"] in ("greedy-fallback", "exact-fallback"))
    rows.append(f"{e} & " + " & ".join(cells) + f" & {fb}\\\\")
(OUT / "tab_evopt.tex").write_text("\n".join(rows), encoding="utf-8")
fb_events = {e: sum(1 for r in log if r.get("replanned") and r["event"] == k and r["verified"]["how"] in ("greedy-fallback", "exact-fallback"))
             for k, e in enumerate(evs_names)}
put("FallbackTotal", str(sum(fb_events.values())))
assert fb_events["E0 initial"] == 0 and fb_events["E1 road R5 closed"] == 0, "text: fallbacks only after capacity events"

# Fig. 4: QAOA objective evaluations per event, cold vs angle memory (mu = 0)
cold_ev, warm_ev = [], []
for k, e in enumerate(evs_names):
    for key, acc in (("mu0_cold", cold_ev), ("mu0_warm", warm_ev)):
        rr = [r for r in runs[key]["log"] if r.get("replanned") and r["event"] == k]
        acc.append(sum(r["verified"]["nfev"] for r in rr) / len(rr))
put("NfevEzeroWarm", f"{warm_ev[0]:.0f}")
put("NfevLaterWarm", f"{sum(warm_ev[1:]) / len(warm_ev[1:]):.0f}")
put("NfevEzeroCold", f"{cold_ev[0]:.0f}")
assert warm_ev[0] > max(warm_ev[1:]), "text: warm start pays full cost only at E0"

# Fig. 2: unverified invalid dispatches by event, per configuration
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
fig, ax = plt.subplots(figsize=(3.45, 1.8))
evs = list(base["by_event"])
w = 0.2
for ci, ((key, mu, st), col, h) in enumerate(zip(cfgs, ["0.15", "0.45", "0.7", "1.0"], ["", "//", "..", "xx"])):
    v = [runs[key]["summary"]["by_event"][e]["raw_invalid"] for e in evs]
    ax.bar([x + (ci - 1.5) * w for x in range(len(evs))], v, w, color=col, edgecolor="black", lw=0.5, hatch=h,
           label=f"$\\mu$={mu}, {st}")
ax.set_xticks(range(len(evs)))
ax.set_xticklabels([e.split()[0] for e in evs])
ax.set_ylabel("Invalid if unverified")
ax.legend(fontsize=6, ncol=2, frameon=False, loc="upper left")
ax.grid(axis="y", lw=0.3)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_event.pdf")
fig, ax = plt.subplots(figsize=(3.45, 1.7))
xs = range(len(evs_names))
ax.bar([x - 0.18 for x in xs], cold_ev, 0.36, color="0.75", edgecolor="black", lw=0.5, label="cold start")
ax.bar([x + 0.18 for x in xs], warm_ev, 0.36, color="0.25", edgecolor="black", lw=0.5, label="angle memory")
ax.set_xticks(list(xs))
ax.set_xticklabels([e.split()[0] for e in evs_names])
ax.set_ylabel("Evaluations per re-plan")
ax.legend(fontsize=6.5, frameon=False)
ax.grid(axis="y", lw=0.3)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_nfev.pdf")
assert raw_inv[0] > raw_inv[1] > raw_inv[3], "text: raw invalid falls with memory and mu"
for key, _, _ in cfgs:
    s = runs[key]["summary"]
    assert s["verified"]["dispatched_invalid_pct"] == 0 and s["portfolio"]["dispatched_invalid_pct"] == 0
    assert s["by_event"]["E0 initial"]["raw_invalid"] == 0 and s["by_event"]["E1 road R5 closed"]["raw_invalid"] == 0
assert base["verified"]["mean_churn"] > base["oracle"]["mean_churn"], "text: QAOA churns more than exact at mu=0"

# worked episode: the first seed (cold, mu = 0) in which the raw policy would dispatch an invalid plan
seeds = sorted({r["seed"] for r in log})
tr_seed = next(s for s in seeds if any(r["seed"] == s and r.get("replanned") and r["raw"]["dispatched_invalid"] for r in log))
put("TraceSeed", str(tr_seed))
EVN = {0: "E0 initial", 1: "E1 R5 closed", 2: "E2 surge", 3: "E3 closure", 4: "E4 A failed"}
trace = []
for r in [x for x in log if x["seed"] == tr_seed and x.get("replanned")]:
    rg = r["raw"]["gap_obj"]
    raw = "invalid" if r["raw"]["dispatched_invalid"] else ("optimal" if abs(rg) < 1e-6 else ("+$<$0.01" if rg < 0.005 else f"+{rg:.2f}"))
    v = r["verified"]
    vhow = {"qaoa": "QAOA", "greedy-fallback": "greedy fb.", "exact-fallback": "exact fb."}.get(v["how"], v["how"])
    vres = "optimal" if abs(v["gap_obj"]) < 1e-6 else f"+{v['gap_obj']:.2f}"
    trace.append(f"{EVN[r['event']]} & {raw} & {vhow} & {vres} & {v['churn']} & {r['oracle']['travel']:.2f}\\\\")
(OUT / "tab_trace.tex").write_text("\n".join(trace), encoding="utf-8")
tr_inv = [EVN[r["event"]] for r in log if r["seed"] == tr_seed and r.get("replanned") and r["raw"]["dispatched_invalid"]]
put("TraceInvalidEvents", ", ".join(tr_inv))
put("TraceNInvalid", str(len(tr_inv)))

# Fig.: optimal plans by event for each policy (cold, mu = 0)
fig, ax = plt.subplots(figsize=(3.45, 1.75))
pols = [("raw", "0.85", "Raw"), ("verified", "0.55", "Verified"), ("portfolio", "0.3", "Portfolio"), ("classical", "0.05", "Classical")]
for pi, (pk, col, lab) in enumerate(pols):
    vals = []
    for k in range(5):
        rr = [r for r in log if r.get("replanned") and r["event"] == k]
        vals.append(100 * sum(1 for r in rr if r[pk]["gap_obj"] is not None and abs(r[pk]["gap_obj"]) < 1e-6) / len(rr))
    ax.bar([x + (pi - 1.5) * 0.2 for x in range(5)], vals, 0.2, color=col, edgecolor="black", lw=0.4, label=lab)
ev_opt = {}
for pk, _, _ in pols:
    ev_opt[pk] = []
    for k in range(5):
        rr = [r for r in log if r.get("replanned") and r["event"] == k]
        ev_opt[pk].append(100 * sum(1 for r in rr if r[pk]["gap_obj"] is not None and abs(r[pk]["gap_obj"]) < 1e-6) / len(rr))
put("EvVerMin", f"{min(ev_opt['verified']):.0f}")
put("EvPortMin", f"{min(ev_opt['portfolio']):.0f}")
put("EvRawMax", f"{max(ev_opt['raw']):.0f}")
ax.set_xticks(range(5))
ax.set_xticklabels(["E0", "E1", "E2", "E3", "E4"])
ax.set_ylabel("optimal plans (%)")
ax.set_ylim(0, 105)
ax.legend(fontsize=6, ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.18))
ax.grid(axis="y", lw=0.3)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_evopt.pdf")

# Fig.: churn per event, verified and exhaustive, mu = 0 vs mu = 6 (both with angle memory)
fig, ax = plt.subplots(figsize=(3.45, 1.7))
for key, ls, lab in (("mu0_warm", "-", "$\\mu$=0"), ("mu6_warm", "--", "$\\mu$=6")):
    lg = runs[key]["log"]
    for pk, mk, col in (("verified", "o", "0.05"), ("oracle", "s", "0.55")):
        vals = [sum(r[pk]["churn"] for r in lg if r.get("replanned") and r["event"] == k) / 30 for k in range(1, 5)]
        ax.plot(range(1, 5), vals, ls, marker=mk, color=col, ms=3, lw=0.8,
                label=f"{'QAOA+verifier' if pk == 'verified' else 'exhaustive'}, {lab}")
ax.set_xticks(range(1, 5))
ax.set_xticklabels(["E1", "E2", "E3", "E4"])
ax.set_ylabel("groups moved")
ax.legend(fontsize=5.6, ncol=2, frameon=False, loc="upper left")
ax.grid(lw=0.3)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_churn.pdf")
e4 = {key: sum(r["verified"]["churn"] for r in runs[key]["log"] if r.get("replanned") and r["event"] == 4) / 30
      for key in ("mu0_warm", "mu6_warm")}
evc = {key: [sum(r["verified"]["churn"] for r in runs[key]["log"] if r.get("replanned") and r["event"] == k) / 30
             for k in range(1, 5)] for key in ("mu0_warm", "mu6_warm")}
put("ChurnEthreeZero", f"{evc['mu0_warm'][2]:.2f}")
put("ChurnEthreeSix", f"{evc['mu6_warm'][2]:.2f}")
assert evc["mu0_warm"][3] == max(evc["mu0_warm"]), "text: E4 has the largest churn"
assert evc["mu6_warm"][2] < 0.2 * evc["mu0_warm"][2], "text: mu removes almost all E3 churn"
assert abs(evc["mu6_warm"][3] - evc["mu0_warm"][3]) < 1e-9, "text: E4 churn unchanged"
put("ChurnEfourZero", f"{e4['mu0_warm']:.2f}")
put("ChurnEfourSix", f"{e4['mu6_warm']:.2f}")

# escalation experiment (sixth event: Shelter B also fails)
esc = json.loads((WORK / "p3_esc.json").read_text(encoding="utf-8"))
put("EscEpisodes", str(esc["n_episodes"]))
put("EscInfeasible", str(esc["e5_infeasible"]))
put("EscCorrect", str(esc["correct_escalations"]))
put("EscWrong", str(esc["wrong_escalations"]))
put("EscMissed", str(esc["missed_escalations"]))
put("EscRawInvalid", str(esc["raw_invalid_at_infeasible"]))
assert esc["wrong_escalations"] == 0 and esc["missed_escalations"] == 0, "text: escalation exact"
assert esc["correct_escalations"] == esc["e5_infeasible"] > 0
assert esc["raw_invalid_at_infeasible"] == esc["e5_infeasible"], "text: raw dispatches an invalid plan at every infeasible event"

with open(OUT / "nums.tex", "w", encoding="utf-8") as f:
    for k, v in M.items():
        f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
fig, ax = plt.subplots(figsize=(3.45, 1.9))
for p, (m, c, lab) in {"oracle": ("o-", "0.05", "Exhaustive"), "verified": ("s--", "0.5", "QAOA + verifier")}.items():
    xs, ys, ms = zip(*pts[p])
    ax.plot(ys, xs, m, color=c, ms=3.5, lw=0.9, label=lab)
    for x, y, mu in pts[p]:
        ax.annotate(f"$\\mu$={mu}", (y, x), textcoords="offset points", xytext=(4, 2), fontsize=6)
ax.set_xlabel("Groups reassigned per re-plan")
ax.set_ylabel("Mean plan travel cost (min)")
ax.grid(lw=0.3)
ax.legend(fontsize=6.5, frameon=False)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_tradeoff.pdf")
# claims in the text
ev = base["by_event"]
assert base["raw"]["dispatched_invalid_pct"] > 0 and base["verified"]["dispatched_invalid_pct"] == 0
assert ev["E0 initial"]["raw_invalid"] == 0 and ev["E1 road R5 closed"]["raw_invalid"] == 0, "text: raw failures only after capacity events"
assert base["infeasible_events"] == 0 and base["no_change_events"] == 0, "text: every event re-planned, none infeasible"
assert base["classical"]["opt_pct"] > base["verified"]["opt_pct"], "text: classical beats verified QAOA"
assert warm["verified"]["mean_nfev"] < base["verified"]["mean_nfev"] and warm["verified"]["mean_ms"] < base["verified"]["mean_ms"]
for p in ("oracle", "verified"):
    ch = [runs[k]["summary"][p]["mean_churn"] for k, _ in mus]
    assert ch[0] > ch[-1], f"text: mu reduces churn for {p}"
print("p3 nums:", len(M))
