"""Fourth-revision numbers for P1 -> macros and tab_beyond.tex.

Reads only stored results written by exp_p1_r4.py:
  p1_r4_sub.json  M3: fixed 12-qubit angles (rule popt = eq. 7, energy rule) vs per-instance training at G groups
  p1_r4_dis.json  M2: the same fixed angles (rules popt / energy / cvar) on 12-qubit instances of three other
                  disruption patterns vs per-instance training
Tests: two-sided Wilcoxon signed-rank on per-instance P_opt, Holm within each family (M3: sizes x 2 rules;
M2: patterns x 3 rules). Effect size: median paired difference. Gain over uniform one-hot sampling:
P_opt / U with U = |X*| / 3^G (equal to P_opt * 3^G when the optimum is unique).
Called from post_p1.py; every comparison the text makes is asserted here.
"""
import json

import numpy as np
from scipy.stats import wilcoxon

from post_p1_r3 import holm, s32  # noqa: E402
from post_p1_v2 import sci  # noqa: E402

PAT = (("roads", "Two roads closed", "Roads"), ("shelter", "Shelter B failed", "Shelter"),
       ("capacity", "Shelter C cut", "Capacity"))
WORD = {5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}


def extend(put, work, out):
    sub = json.loads((work / "p1_r4_sub.json").read_text(encoding="utf-8"))
    dis = json.loads((work / "p1_r4_dis.json").read_text(encoding="utf-8"))
    R = {"sub": {}, "dis": {}}
    rows_tab = []

    # ------------------------------------------------------------------ M3: size
    sizes = sorted({r["G"] for r in sub["rows"]})
    tests, data = [], {}
    for G in sizes:
        g = sorted([r for r in sub["rows"] if r["G"] == G], key=lambda r: r["i"])
        assert [r["i"] for r in g] == sub["screened"][str(G)]["ids"], "every screened instance was run"
        t = np.array([r["trained"] for r in g])
        u = np.array([r["uniform"] for r in g])
        data[G] = {"t": t, "u": u, "popt": np.array([r["popt"] for r in g]),
                   "energy": np.array([r["energy"] for r in g]), "bind": int(sum(r["binding"] for r in g)),
                   "nfev": float(np.mean([r["nfev"] for r in g])), "tried": sub["screened"][str(G)]["tried"]}
        for rule in ("popt", "energy"):
            tests.append((G, rule))
    raw = [wilcoxon(data[G][rule], data[G]["t"]).pvalue for G, rule in tests]
    adj = dict(zip(tests, holm(raw)))
    put("ScFamily", str(len(tests)))
    put("ScSizes", ", ".join(str(G) for G in sizes[:-1]) + f" and {sizes[-1]}")
    put("ScQubitsMax", str(3 * sizes[-1]))
    put("ScQubitsMin", str(3 * sizes[0]))
    put("ScGMax", str(sizes[-1]))
    put("ScN", str(len(data[sizes[0]]["t"])))
    put("ScNTotal", str(sum(len(data[G]["t"]) for G in sizes)))
    put("ScEvals", f"{np.mean([data[G]['nfev'] for G in sizes]):,.0f}")
    for G in sizes:
        d = data[G]
        w = WORD[G]
        res = {"t": d["t"], "u": d["u"]}
        put(f"Sc{w}N", str(len(d["t"])))
        put(f"Sc{w}Tried", str(d["tried"]))
        put(f"Sc{w}Bind", str(d["bind"]))
        put(f"Sc{w}Trained", f"{d['t'].mean():.3f}")
        put(f"Sc{w}TrainedGain", f"{np.median(d['t'] / d['u']):.0f}")
        put(f"Sc{w}TrainedLow", str(int((d["t"] < 0.01).sum())))
        put(f"Sc{w}Unif", f"{d['u'].mean():.5f}")
        for rule, tg in (("popt", "O"), ("energy", "E")):
            f = d[rule]
            res[rule] = dict(f=f, p=float(adj[(G, rule)]), med=float(np.median(f - d["t"])),
                             wins=int((f > d["t"]).sum()), gain=float(np.median(f / d["u"])))
            put(f"Sc{w}{tg}", f"{f.mean():.3f}")
            put(f"Sc{w}{tg}P", sci(adj[(G, rule)]))
            put(f"Sc{w}{tg}Med", f"{np.median(f - d['t']):+.3f}")
            put(f"Sc{w}{tg}Wins", str(int((f > d["t"]).sum())))
            put(f"Sc{w}{tg}Gain", f"{np.median(f / d['u']):.0f}")
            put(f"Sc{w}{tg}Min", f"{f.min():.4f}")
            put(f"Sc{w}{tg}MinGain", f"{np.min(f / d['u']):.0f}")
        R["sub"][G] = res
        o, e = res["popt"], res["energy"]
        rows_tab.append(f"$G={G}$ ({3 * G}) & {len(d['t'])} & "
                        f"{d['t'].mean():.3f} & {o['f'].mean():.3f} & {o['med']:+.3f} & ${sci(o['p'])}$ & "
                        f"{e['f'].mean():.3f} & {e['med']:+.3f} & ${sci(e['p'])}$\\\\")
    rows_tab.append("\\addlinespace[2pt]")

    # ------------------------------------------------------------------ M2: other disruption patterns
    tests, dd = [], {}
    for pat, _, _ in PAT:
        g = [r for r in dis["rows"] if r["pattern"] == pat]
        dd[pat] = {"t": np.array([r["trained"] for r in g]), "u": np.array([r["uniform"] for r in g]),
                   "bind": int(sum(r["binding"] for r in g)), "tried": sum(1 for r in dis["all"] if r["pattern"] == pat)}
        for rule in ("popt", "energy", "cvar"):
            dd[pat][rule] = np.array([r[rule] for r in g])
            tests.append((pat, rule))
    raw = [wilcoxon(dd[p][rule], dd[p]["t"]).pvalue for p, rule in tests]
    adj = dict(zip(tests, holm(raw)))
    put("DsFamily", str(len(tests)))
    put("DsN", str(len(dd["roads"]["t"])))
    put("DsNTotal", str(sum(len(dd[p]["t"]) for p, _, _ in PAT)))
    for pat, label, tg0 in PAT:
        d = dd[pat]
        res = {"t": d["t"], "u": d["u"]}
        put(f"Ds{tg0}N", str(len(d["t"])))
        put(f"Ds{tg0}Tried", str(d["tried"]))
        put(f"Ds{tg0}Bind", str(d["bind"]))
        put(f"Ds{tg0}Trained", f"{d['t'].mean():.3f}")
        put(f"Ds{tg0}TrainedSucc", f"{s32(d['t']):.1f}")
        for rule, tg in (("popt", "O"), ("energy", "E"), ("cvar", "C")):
            f = d[rule]
            res[rule] = dict(f=f, p=float(adj[(pat, rule)]), med=float(np.median(f - d["t"])),
                             wins=int((f > d["t"]).sum()))
            put(f"Ds{tg0}{tg}", f"{f.mean():.3f}")
            put(f"Ds{tg0}{tg}P", sci(adj[(pat, rule)]))
            put(f"Ds{tg0}{tg}Med", f"{np.median(f - d['t']):+.3f}")
            put(f"Ds{tg0}{tg}Wins", str(int((f > d["t"]).sum())))
            put(f"Ds{tg0}{tg}Succ", f"{s32(f):.1f}")
        R["dis"][pat] = res
        o, e = res["popt"], res["energy"]
        rows_tab.append(f"{label} & {len(d['t'])} & {d['t'].mean():.3f} & "
                        f"{o['f'].mean():.3f} & {o['med']:+.3f} & ${sci(o['p'])}$ & "
                        f"{e['f'].mean():.3f} & {e['med']:+.3f} & ${sci(e['p'])}$\\\\")
    # pooled over the three patterns (descriptive, own Holm family of 3 rules)
    T = np.concatenate([dd[p]["t"] for p, _, _ in PAT])
    praw = []
    for rule in ("popt", "energy", "cvar"):
        F = np.concatenate([dd[p][rule] for p, _, _ in PAT])
        praw.append(wilcoxon(F, T).pvalue)
    padj = holm(praw)
    put("DsAllTrained", f"{T.mean():.3f}")
    put("DsAllTrainedSucc", f"{s32(T):.1f}")
    R["dis"]["all"] = {"t": T}
    for (rule, tg), p in zip((("popt", "O"), ("energy", "E"), ("cvar", "C")), padj):
        F = np.concatenate([dd[q][rule] for q, _, _ in PAT])
        R["dis"]["all"][rule] = dict(f=F, p=float(p), med=float(np.median(F - T)), wins=int((F > T).sum()))
        put(f"DsAll{tg}", f"{F.mean():.3f}")
        put(f"DsAll{tg}P", sci(p))
        put(f"DsAll{tg}Med", f"{np.median(F - T):+.3f}")
        put(f"DsAll{tg}Wins", str(int((F > T).sum())))
        put(f"DsAll{tg}Succ", f"{s32(F):.1f}")
    (out / "tab_beyond.tex").write_text("\n".join(rows_tab), encoding="utf-8")
    return R
