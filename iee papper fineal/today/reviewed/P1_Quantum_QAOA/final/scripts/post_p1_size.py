"""p1_size.json -> macros + tab_size.tex (transfer across problem size, fixed angles under gate noise).

Called from post_p1.py (extend) before nums.tex is written. Sentences whose direction depends on the data
are generated here; every directional claim left in paper.tex is asserted.
"""
import json

import numpy as np
from scipy.stats import wilcoxon

N_SHOTS = 32


def sci(x):
    if x >= 0.001:
        return f"{x:.3f}"
    m, e = f"{x:.1e}".split("e")
    return f"{m}\\times10^{{{int(e)}}}"


def succ(p):
    return 100.0 * float(np.mean(1.0 - (1.0 - np.asarray(p)) ** N_SHOTS))


def extend(put, work, out):
    j = json.loads((work / "p1_size.json").read_text(encoding="utf-8"))
    rows, groups = [], {}
    for r in j["size"]:
        if r["feasible_instance"]:
            groups.setdefault((r["G"], r["alpha"]), []).append(r)
    tags = {(5, 1.0): ("Five", "15", "mean"), (5, 0.1): ("FiveCvar", "15", "CVaR"), (6, 1.0): ("Six", "18", "mean")}
    res = {}
    for key, (tag, nq, obj) in tags.items():
        g = sorted(groups[key], key=lambda r: r["i"])
        f = np.array([r["fixed_p4"] for r in g])
        t = np.array([r["trained_p4"] for r in g])
        u = float(np.mean([r["uniform"] for r in g]))
        p = float(wilcoxon(f, t).pvalue)
        ev = float(np.mean([r["trained_cum_nfev_p4"] for r in g]))
        res[key] = dict(f=f, t=t, u=u, p=p, ev=ev)
        put(f"Sz{tag}N", str(len(g)))
        put(f"Sz{tag}Fixed", f"{f.mean():.3f}")
        put(f"Sz{tag}Trained", f"{t.mean():.3f}")
        put(f"Sz{tag}FixedMin", f"{f.min():.3f}")
        put(f"Sz{tag}TrainedLow", str(int((t < 0.01).sum())))
        put(f"Sz{tag}Wins", str(int((f > t).sum())))
        put(f"Sz{tag}P", sci(p))
        put(f"Sz{tag}Unif", f"{u:.4f}")
        put(f"Sz{tag}Evals", f"{ev:.0f}")
        put(f"Sz{tag}SuccF", f"{succ(f):.1f}")
        put(f"Sz{tag}SuccT", f"{succ(t):.1f}")
        rows.append(f"{key[0]} ({nq}) & {obj} & {len(g)} & {u:.4f} & {t.mean():.3f} & {int((t < 0.01).sum())} & "
                    f"{f.mean():.3f} & {f.min():.3f} & {succ(t):.0f} & {succ(f):.0f}\\\\")
    (out / "tab_size.tex").write_text("\n".join(rows), encoding="utf-8")

    # data-chosen sentence on the mean comparison at each size
    parts = []
    for key, name in (((5, 1.0), "15 qubits"), ((6, 1.0), "18 qubits")):
        r = res[key]
        word = "significantly higher" if (r["p"] < 0.05 and r["f"].mean() > r["t"].mean()) else (
            "higher on average but not significantly so" if r["f"].mean() > r["t"].mean() else
            "lower on average" + ("" if r["p"] < 0.05 else ", although not significantly"))
        parts.append(f"at {name} the fixed angles were {word} ($p={sci(r['p'])}$, Wilcoxon)")
    put("SizeCompare", "; ".join(parts) + ".")

    for key in tags:
        r = res[key]
        assert r["f"].min() > 10 * r["u"], "text: fixed angles stay far above uniform sampling at every size"
        assert r["f"].min() > 0.05, "text: fixed angles never collapse below 0.05"
    for key in ((5, 1.0), (6, 1.0)):
        r = res[key]
        assert (r["t"] < 0.01).sum() >= 3, "text: per-instance training collapses on several instances"
        assert succ(r["f"]) > succ(r["t"]), "text: fixed angles give higher success@32"

    # noise: fixed against per-instance trained XY p=4 angles on new 12-qubit instances
    nz = j["noise"]
    eps = j["eps"]
    put("SzNoiseN", str(len(nz)))
    put("SzNoiseTraj", str(j["traj"]))
    keys = sorted({k.rsplit("_eps", 1)[0] for k in nz[0] if "_eps" in k})
    assert set(keys) >= {"fixed", "trained"}, keys
    nrows = []
    for e in eps:
        fx = np.array([x[f"fixed_eps{e}"] for x in nz])
        tr = np.array([x[f"trained_eps{e}"] for x in nz])
        tag = "Half" if abs(e - 0.005) < 1e-9 else "One"
        put(f"SzNoise{tag}Fixed", f"{fx.mean():.3f}")
        put(f"SzNoise{tag}Trained", f"{tr.mean():.3f}")
        put(f"SzNoise{tag}Wins", str(int((fx > tr).sum())))
        nrows.append((e, fx, tr))
    fx1, tr1 = nrows[-1][1], nrows[-1][2]
    if fx1.mean() > tr1.mean():
        s = (f"Under two-qubit noise the advantage persisted: at $\\epsilon=0.01$ the fixed angles kept "
             f"$P_{{\\mathrm{{opt}}}}={fx1.mean():.3f}$ against {tr1.mean():.3f} for per-instance angles "
             f"(better on {int((fx1 > tr1).sum())} of {len(fx1)} instances).")
    else:
        s = (f"Under two-qubit noise the advantage did not persist: at $\\epsilon=0.01$ the fixed angles kept "
             f"$P_{{\\mathrm{{opt}}}}={fx1.mean():.3f}$ against {tr1.mean():.3f} for per-instance angles.")
    put("SizeNoise", s)
    return res
