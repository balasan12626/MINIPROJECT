"""p1.json -> nums.tex, tab_main.tex, tab_scale.tex, fig_popt.pdf (+ circuit resource counts).
Asserts the qualitative claims made in paper.tex. Run with the repo .venv."""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(HERE.parent)]
import qaoa_sim as Q  # noqa: E402
from exp_p1 import disrupted  # noqa: E402

WORK, OUT = Path(sys.argv[1]), Path(sys.argv[2])
j = json.loads((WORK / "p1.json").read_text(encoding="utf-8"))
s = j["summary"]
M = {}
W = {1: "One", 2: "Two", 3: "Three", 4: "Four"}


def put(k, v):
    M[k] = v


put("NInst", str(s["n_instances"]))
put("NFeasInst", str(s["n_feasible_instances"]))
put("NBinding", str(s["capacity_binding"]))
put("MeanFeasAssign", f"{s['mean_feasible_assignments']:.1f}")
put("Shots", str(s["shots"]))
put("UniBits", f"{s['uniform_bits_popt']:.5f}")
put("UniOneHot", f"{s['uniform_onehot_popt']:.4f}")
put("ExactMs", f"{s['exact_ms']:.2f}")
put("SAOpt", f"{s['sa_opt_pct']:.1f}")
put("SAFeas", f"{s['sa_feas_pct']:.1f}")
put("SAMs", f"{s['sa_ms']:.1f}")
put("GreedyOpt", f"{s['greedy_opt_pct']:.1f}")
put("GreedyFeas", f"{s['greedy_feasible_pct']:.1f}")
put("QuboExact", f"{s['qubo_exact_pct']:.1f}")
Qd = {(r["alpha"], r["kind"], r["p"]): r for r in s["qaoa"]}
for (a, k, p), r in Qd.items():
    tag = f"Q{'X' if k == 'x' else 'XY'}{'Mean' if a == 1.0 else 'Cvar'}{W[p]}"
    put(tag + "Popt", f"{r['popt']:.3f}")
    put(tag + "Pfeas", f"{r['pfeas']:.3f}")
    put(tag + "Succ", f"{r['succ_shots_pct']:.1f}")
    put(tag + "Argmax", f"{r['argmax_opt_pct']:.1f}")
    put(tag + "Nfev", f"{r['nfev']:.0f}")
    put(tag + "Ms", f"{r['ms'] / 1000:.2f}")
xyf = [Qd[(1.0, "xy", p)]["pfeas"] for p in (1, 2, 3, 4)]
put("XYPfeasMin", f"{min(xyf):.3f}")
put("XYPfeasMax", f"{max(xyf):.3f}")
best_xy = Qd[(1.0, "xy", 4)]["popt"]
put("GainXYoverUni", f"{best_xy / s['uniform_onehot_popt']:.1f}")
put("GainXYoverX", f"{best_xy / Qd[(1.0, 'x', 4)]['popt']:.1f}")

# circuit resources per layer, averaged over the 30 main instances (G = 4)
zz_x, zz_xy, ov = [], [], []
for i in range(s["n_instances"]):
    inst = Q.instance_from_engine(disrupted(42 + 17 * i), 4)
    pairs = len(Q.overload_pairs(inst))
    ov.append(pairs)
    zz_x.append(inst["G"] * 3 + pairs)  # one-hot penalty couples the 3 qubits of a group
    zz_xy.append(pairs)
put("ZZX", f"{np.mean(zz_x):.1f}")
put("ZZXY", f"{np.mean(zz_xy):.1f}")
put("OvPairs", f"{np.mean(ov):.1f}")

# main table rows
lines = []
for a, an in ((1.0, "mean"), (0.1, "CVaR$_{0.1}$")):
    for k, kn in (("x", "X"), ("xy", "XY")):
        for p in (1, 2, 3, 4):
            r = Qd[(a, k, p)]
            lines.append(f"{kn} & {an} & {p} & {r['popt']:.3f} & {r['pfeas']:.3f} & {r['succ_shots_pct']:.1f} & "
                         f"{r['nfev']:.0f}\\\\")
        lines.append("\\addlinespace[1pt]" if not (a == 0.1 and k == "xy") else "")
(OUT / "tab_main.tex").write_text("\n".join(x for x in lines if x), encoding="utf-8")

rows = []
for r in s["scaling"]:
    rows.append(f"{r['G']} & {r['qubits']} & {r['n']} & {r['uniform_onehot_popt']:.3f} & {r['x_popt']:.3f} & "
                f"{r['xy_popt']:.3f} & {r['xy_pfeas']:.3f} & {r['xy_ms'] / 1000:.1f} & {r['exact_ms']:.2f}\\\\")
(OUT / "tab_scale.tex").write_text("\n".join(rows), encoding="utf-8")
sc = {r["G"]: r for r in s["scaling"]}
put("ScaleMaxQ", str(max(sc[g]["qubits"] for g in sc)))
put("ScaleXYsix", f"{sc[max(sc)]['xy_popt']:.3f}")
put("ScaleUnisix", f"{sc[max(sc)]['uniform_onehot_popt']:.4f}")
put("ScaleXYmsSix", f"{sc[max(sc)]['xy_ms'] / 1000:.1f}")
put("ScaleExactSix", f"{sc[max(sc)]['exact_ms']:.2f}")
put("ScaleQuboMin", f"{min(sc[g]['qubo_exact_pct'] for g in sc):.0f}")

# capacity-binding analysis and per-instance spread at p = 4
bind = {b["i"]: b["capacity_binding"] for b in j["base"] if b["feasible_instance"]}
brow = []
spread = {}
for k, a, lab in (("x", 1.0, "X, mean"), ("x", 0.1, "X, CVaR"), ("xy", 1.0, "XY, mean"), ("xy", 0.1, "XY, CVaR")):
    r = [x for x in j["rows"] if x["kind"] == k and x["alpha"] == a and x["p"] == 4]
    b = [x["popt"] for x in r if bind[x["i"]]]
    nb = [x["popt"] for x in r if not bind[x["i"]]]
    allp = [x["popt"] for x in r]
    spread[(k, a)] = (np.min(allp), np.median(allp), np.max(allp), np.mean(b), np.mean(nb))
    brow.append(f"{lab} & {np.mean(nb):.3f} & {np.mean(b):.3f} & {np.min(allp):.3f} & {np.median(allp):.3f} & {np.max(allp):.3f}\\\\")
(OUT / "tab_bind.tex").write_text("\n".join(brow), encoding="utf-8")
put("NNonBinding", str(sum(1 for v in bind.values() if not v)))
put("XYBind", f"{spread[('xy', 1.0)][3]:.3f}")
put("XYNonBind", f"{spread[('xy', 1.0)][4]:.3f}")
put("XYMin", f"{spread[('xy', 1.0)][0]:.3f}")
put("XYCvarMin", f"{spread[('xy', 0.1)][0]:.3f}")
put("XYMax", f"{spread[('xy', 1.0)][2]:.3f}")
put("XYCvarMax", f"{spread[('xy', 0.1)][2]:.3f}")
put("XBind", f"{spread[('x', 1.0)][3]:.3f}")
put("XNonBind", f"{spread[('x', 1.0)][4]:.3f}")
put("ScaleXYtwo", f"{sc[min(sc)]['xy_popt']:.3f}")
put("ScaleXtwo", f"{sc[min(sc)]['x_popt']:.3f}")
put("ScaleXsix", f"{sc[max(sc)]['x_popt']:.4f}")
put("ScaleInfeasSix", str(sc[max(sc)]["n_infeasible"]))
put("ScaleXYfeasSix", f"{sc[max(sc)]['xy_pfeas']:.3f}")
put("ScaleXfeasSix", f"{sc[max(sc)]['x_pfeas']:.3f}")

# Fig. 3: scaling of P_opt with qubits (log scale)
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
fig, ax = plt.subplots(figsize=(3.45, 1.9))
qs = [sc[g]["qubits"] for g in sorted(sc)]
ax.semilogy(qs, [sc[g]["xy_popt"] for g in sorted(sc)], "o-", color="0.05", ms=3.5, lw=0.9, label="XY mixer, $p=2$")
ax.semilogy(qs, [sc[g]["x_popt"] for g in sorted(sc)], "s--", color="0.5", ms=3.5, lw=0.9, label="X mixer, $p=2$")
ax.semilogy(qs, [sc[g]["uniform_onehot_popt"] for g in sorted(sc)], ":", color="black", lw=0.8, label="uniform one-hot")
ax.set_xlabel("qubits $n=3G$")
ax.set_ylabel("$P_{\\mathrm{opt}}$")
ax.set_xticks(qs)
ax.grid(lw=0.3, which="both")
ax.legend(fontsize=6.5, frameon=False)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_scale.pdf")
# Fig. 4: per-instance P_opt at p = 4, binding vs non-binding
fig, ax = plt.subplots(figsize=(3.45, 1.75))
vars4 = [("x", 1.0, "X, mean"), ("x", 0.1, "X, CVaR"), ("xy", 1.0, "XY, mean"), ("xy", 0.1, "XY, CVaR")]
rng = np.random.default_rng(0)
for vi, (k, a, lab) in enumerate(vars4):
    r = [x for x in j["rows"] if x["kind"] == k and x["alpha"] == a and x["p"] == 4]
    for x in r:
        jit = rng.uniform(-0.12, 0.12)
        b = bind[x["i"]]
        ax.plot(vi + jit, x["popt"], "o" if b else "^", ms=3, mfc="black" if b else "white", mec="black", mew=0.5)
ax.set_xticks(range(4))
ax.set_xticklabels([v[2] for v in vars4])
ax.set_ylabel("$P_{\\mathrm{opt}}$ at $p=4$")
ax.grid(axis="y", lw=0.3)
ax.plot([], [], "o", ms=3, mfc="black", mec="black", label="capacity binding")
ax.plot([], [], "^", ms=3, mfc="white", mec="black", label="non-binding")
ax.legend(fontsize=6.3, frameon=False, loc="upper left")
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_inst.pdf")
low = [x for x in j["rows"] if x["kind"] == "xy" and x["alpha"] == 1.0 and x["p"] == 4 and x["popt"] < 0.02]
assert low and all(bind[x["i"]] for x in low), "text: near-zero XY instances are all capacity-bound"
assert spread[("xy", 0.1)][0] > 0.02, "text: CVaR removes the near-zero tail"
assert spread[("xy", 1.0)][3] < spread[("xy", 1.0)][4], "text: binding instances are harder for XY"
assert spread[("xy", 0.1)][0] > spread[("xy", 1.0)][0], "text: CVaR lifts the worst instance"
assert all(sc[g]["xy_popt"] > sc[g]["uniform_onehot_popt"] for g in sc), "text: XY above uniform at every size"
assert all(sc[g]["x_popt"] < sc[g]["uniform_onehot_popt"] for g in sc if g >= 4), "text: X below uniform from 12 qubits"
assert sc[max(sc)]["n_infeasible"] == 1, "text: singular 'instance was excluded'"
assert spread[("xy", 1.0)][3] < 0.5, "text: most probability on suboptimal plans for binding instances"

# global depolarizing estimate: F = (1-eps)^N2, P_noisy = F P_opt + (1-F) n_opt / 2^n
nopt = np.mean([b["n_opt"] for b in j["base"] if b["feasible_instance"]])
ov_mean = float(np.mean(ov))
def n2(kind, p, cw):
    return p * (12 + ov_mean) + (cw * 4 if kind == "xy" else 0)
noise_rows, best_depth = [], {}
for eps in (0.001, 0.005, 0.01, 0.02):
    cells = []
    for k, a in (("x", 1.0), ("xy", 1.0), ("xy", 0.1)):
        vals = []
        for p in (1, 2, 3, 4):
            F = (1 - eps) ** n2(k, p, 4)
            vals.append(F * Qd[(a, k, p)]["popt"] + (1 - F) * nopt / 2 ** 12)
        bp = int(np.argmax(vals)) + 1
        best_depth[(eps, k, a)] = (bp, max(vals))
        cells.append(f"{max(vals):.3f} ({bp})")
    noise_rows.append(f"{eps:g} & " + " & ".join(cells) + "\\\\")
(OUT / "tab_noise.tex").write_text("\n".join(noise_rows), encoding="utf-8")
# robustness of the conclusion to the W-state charge (2..6 two-qubit gates per group)
for cw in (2, 6):
    for eps in (0.001, 0.005, 0.01, 0.02):
        xy = max((1 - eps) ** n2("xy", p, cw) * Qd[(1.0, "xy", p)]["popt"] + (1 - (1 - eps) ** n2("xy", p, cw)) * nopt / 4096 for p in (1, 2, 3, 4))
        x = max((1 - eps) ** n2("x", p, cw) * Qd[(1.0, "x", p)]["popt"] + (1 - (1 - eps) ** n2("x", p, cw)) * nopt / 4096 for p in (1, 2, 3, 4))
        assert xy > x, "text: XY stays ahead under noise for any W-state charge 2..6"
# gate-level Pauli-trajectory study on 10 instances (exp_p1_noise.py), depth 4
nz = json.loads((WORK / "p1_noise.json").read_text(encoding="utf-8"))
ns = {(r["kind"], r["p"], r["eps"]): r for r in nz["summary"]}
trows = []
for eps in (0.001, 0.005, 0.01, 0.02):
    x4, y4 = ns[("x", 4, eps)], ns[("xy", 4, eps)]
    trows.append(f"{eps:g} & {x4['traj']:.3f} & {x4['global']:.3f} & {y4['traj']:.3f} & {y4['global']:.3f}\\\\")
    assert y4["traj"] > x4["traj"], "text: XY ahead under gate-level noise"
    if eps >= 0.005:
        assert x4["traj"] > x4["global"] and y4["traj"] > y4["global"], "text: global model is conservative"
(OUT / "tab_traj.tex").write_text("\n".join(trows), encoding="utf-8")
put("TrajInst", str(nz["n_inst"]))
put("TrajRuns", str(nz["traj"]))
put("TrajIdealXY", f"{ns[('xy', 4, 0.001)]['ideal']:.3f}")
put("TrajIdealX", f"{ns[('x', 4, 0.001)]['ideal']:.3f}")
put("TrajXYOne", f"{ns[('xy', 4, 0.01)]['traj']:.3f}")
put("TrajXOne", f"{ns[('x', 4, 0.01)]['traj']:.3f}")
put("TrajGlobXYOne", f"{ns[('xy', 4, 0.01)]['global']:.3f}")
put("TrajXYTwo", f"{ns[('xy', 4, 0.02)]['traj']:.3f}")
put("TrajRatioOne", f"{ns[('xy', 4, 0.01)]['traj'] / ns[('x', 4, 0.01)]['traj']:.1f}")
put("NtwoLayer", f"{12 + ov_mean:.1f}")
put("CnotLayer", f"{2 * (12 + ov_mean):.0f}")
put("CnotFour", f"{4 * 2 * (12 + ov_mean):.0f}")

# worked example (exp_p1_example.py): instance 0, seed 42
exj = json.loads((WORK / "p1_example.json").read_text(encoding="utf-8"))
SH = ["A", "B", "C"]
rows = []
for g in range(4):
    cells = [("--" if exj["forbidden"][g][s] else f"{exj['cost'][g][s]:.2f}") for s in range(3)]
    rows.append(f"G{g + 1} & {exj['sizes'][g]} & " + " & ".join(cells) + "\\\\")
rows.append("\\midrule")
rows.append("Seats left & & " + " & ".join(str(r) for r in exj["remaining"]) + "\\\\")
(OUT / "tab_example.tex").write_text("\n".join(rows), encoding="utf-8")
fmt_plan = lambda a: "".join(SH[s] for s in a)
trow = []
for k in exj["samples"]["xy"]["top"]:
    trow.append(f"{fmt_plan(k['assign'])} & {k['cost']:.2f} & {k['prob']:.3f} & "
                f"{exj['samples']['x']['top'][[fmt_plan(z['assign']) for z in exj['samples']['x']['top']].index(fmt_plan(k['assign']))]['prob']:.3f}"
                if fmt_plan(k['assign']) in [fmt_plan(z['assign']) for z in exj['samples']['x']['top']] else
                f"{fmt_plan(k['assign'])} & {k['cost']:.2f} & {k['prob']:.3f} & $<${exj['samples']['x']['top'][-1]['prob']:.3f}")
    trow[-1] += (" & optimal" if k["optimal"] else " & ") + "\\\\"
(OUT / "tab_top.tex").write_text("\n".join(trow), encoding="utf-8")
top = exj["samples"]["xy"]["top"]
put("ExOpt", fmt_plan(exj["optimum"]))
put("ExOptCost", f"{exj['opt_cost']:.2f}")
put("ExSecond", fmt_plan(top[1]["assign"]))
put("ExSecondCost", f"{top[1]['cost']:.2f}")
put("ExGap", f"{top[1]['cost'] - exj['opt_cost']:.2f}")
put("ExXYOpt", f"{top[0]['prob']:.3f}")
put("ExXYSecond", f"{top[1]['prob']:.3f}")
put("ExXYFeas", f"{exj['samples']['xy']['p_feas']:.3f}")
put("ExXOpt", f"{exj['samples']['x']['p_opt']:.3f}")
put("ExXFeas", f"{exj['samples']['x']['p_feas']:.3f}")
put("ExNFeas", str(exj["n_feasible"]))
assert top[0]["optimal"] and not top[1]["optimal"] and top[1]["prob"] > 0.5 * top[0]["prob"], "text: near-tie between the two top plans"
assert exj["greedy"] == exj["optimum"], "text: greedy finds this optimum"

# Fig.: gate-level P_opt against eps for each depth (exp_p1_noise.py)
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})  # Type 42: no Type 3 fonts (IEEE)
fig, ax = plt.subplots(figsize=(3.45, 1.8))
eps_l = (0.001, 0.005, 0.01, 0.02)
for kind, ls, col in (("xy", "-", "0.05"), ("x", "--", "0.55")):
    for p, mk in zip((1, 2, 3, 4), ("o", "s", "^", "D")):
        ax.plot(eps_l, [ns[(kind, p, e)]["traj"] for e in eps_l], ls, marker=mk, color=col, ms=3, lw=0.8,
                label=f"{kind.upper()}, $p$={p}")
ax.set_xscale("log")
ax.set_xlabel("two-qubit error rate $\\epsilon$")
ax.set_ylabel("$P_{\\mathrm{opt}}$ (trajectories)")
ax.grid(lw=0.3, which="both")
ax.legend(fontsize=5.4, ncol=2, frameon=False, loc="upper right")
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_noise.pdf")
assert all(ns[("xy", 4, e)]["traj"] >= ns[("xy", 1, e)]["traj"] for e in eps_l), "text: deeper XY circuits stay ahead"
put("NoiseXYOnePct", f"{best_depth[(0.01, 'xy', 1.0)][1]:.3f}")
put("NoiseXYOnePctDepth", str(best_depth[(0.01, 'xy', 1.0)][0]))
put("NoiseXOnePct", f"{best_depth[(0.01, 'x', 1.0)][1]:.3f}")
put("NoiseXYTwoPct", f"{best_depth[(0.02, 'xy', 1.0)][1]:.3f}")
put("NoiseXYTwoPctDepth", str(best_depth[(0.02, 'xy', 1.0)][0]))
put("NoiseCvarTwoPctDepth", str(best_depth[(0.02, 'xy', 0.1)][0]))
assert best_depth[(0.02, "xy", 1.0)][0] == 4, "text: XY mean keeps depth 4 even at 2% error"
assert best_depth[(0.02, "xy", 0.1)][0] < 4, "text: CVaR variant prefers a shallower circuit at 2% error"
assert best_depth[(0.02, "xy", 1.0)][1] > best_depth[(0.02, "x", 1.0)][1], "text: XY ahead of X at 2%"

with open(OUT / "nums.tex", "w", encoding="utf-8") as f:
    for k, v in M.items():
        f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")

# figure: P_opt and P_feas vs depth
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
fig, axs = plt.subplots(1, 2, figsize=(3.45, 1.85))
sty = {("x", 1.0): ("o-", "0.55", "X, mean"), ("x", 0.1): ("s--", "0.55", "X, CVaR"),
       ("xy", 1.0): ("o-", "0.05", "XY, mean"), ("xy", 0.1): ("s--", "0.05", "XY, CVaR")}
for (k, a), (m, c, lab) in sty.items():
    for ax, key in zip(axs, ("popt", "pfeas")):
        ax.plot([1, 2, 3, 4], [Qd[(a, k, p)][key] for p in (1, 2, 3, 4)], m, color=c, ms=3, lw=0.9, label=lab)
axs[0].axhline(s["uniform_onehot_popt"], color="black", lw=0.5, ls=":")
axs[0].set_ylabel("$P_{\\mathrm{opt}}$")
axs[1].set_ylabel("$P_{\\mathrm{feas}}$")
for ax in axs:
    ax.set_xlabel("depth $p$")
    ax.set_xticks([1, 2, 3, 4])
    ax.grid(lw=0.3)
axs[1].set_ylim(0, 1.02)
axs[0].legend(fontsize=5.8, frameon=False, loc="upper left")
fig.tight_layout(pad=0.3, w_pad=0.8)
fig.savefig(OUT / "fig_popt.pdf")

# claims in the text
xy4, x4 = Qd[(1.0, "xy", 4)], Qd[(1.0, "x", 4)]
assert xy4["popt"] > x4["popt"], "text: XY beats X at p=4"
assert all(Qd[(1.0, "xy", p)]["pfeas"] > Qd[(1.0, "x", p)]["pfeas"] for p in (1, 2, 3, 4)), "text: XY more feasible"
assert xy4["popt"] > s["uniform_onehot_popt"], "text: XY beats uniform one-hot sampling"
assert Qd[(0.1, "x", 4)]["popt"] > Qd[(1.0, "x", 4)]["popt"], "text: CVaR raises X popt"
assert Qd[(0.1, "xy", 4)]["popt"] < Qd[(1.0, "xy", 4)]["popt"], "text: CVaR lowers XY popt"
for k in ("x", "xy"):
    assert Qd[(0.1, k, 4)]["succ_shots_pct"] > Qd[(1.0, k, 4)]["succ_shots_pct"], "text: CVaR raises success@N"
assert min(xyf) > 0.5, "text: XY keeps most probability feasible"
assert Qd[(1.0, "x", 1)]["pfeas"] < 0.15, "text: X starts almost all infeasible"
assert s["sa_opt_pct"] < 50, "text: single SA run is weak"
print("p1 nums:", len(M))
