"""Third-revision numbers for P2 -> macros and tables tab_live.tex, tab_heldout.tex (rewritten with
state-clustered bootstrap intervals), tab_taxonomy.tex, tab_ablation.tex.

Inputs (work dir): p2_r3.json (exp_p2_r3.py, stored replies only), p2_breakeven.json (exp_p2_breakeven.py).
Called from post_p2.py after post_p2_r2; every claim the revised text makes about these data is asserted here.
"""
import json

WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]


def nw(n, cap=False):
    s = WORDS[n] if 0 <= n < len(WORDS) else str(n)
    return s[0].upper() + s[1:] if cap else s


def count(n, noun, cap=False):
    """'One reply', 'three replies', '14 replies' (number-noun agreement)."""
    plural = {"reply": "replies", "miss": "misses"}.get(noun, noun + "s")
    return f"{nw(n, cap)} {noun if n == 1 else plural}"


def f1(x):
    return f"{x:.1f}"


def ci(c):
    return f"{c[0]:.0f}--{c[1]:.0f}"


def extend(put, work, out):
    R3 = json.loads((work / "p2_r3.json").read_text(encoding="utf-8"))
    BE = json.loads((work / "p2_breakeven.json").read_text(encoding="utf-8"))
    cb, pt = R3["cluster_boot"], R3["point"]

    # ---------------- Table I with n and state-clustered intervals
    nd = R3["n"]["dev"]
    rows = []
    for name, key, n, p, c in (
            ("Deployed $\\Gamma$", "deployed_ok", nd, pt["dev"]["deployed_ok"], cb["dev"]["deployed_ok"]),
            ("Typed $\\Gamma_{\\mathrm{T}}$", "typed_ok", nd, pt["dev"]["typed_ok"], cb["dev"]["typed_ok"]),
            ("LLM judge, failures rejected", "judge_ok", nd, pt["dev"]["judge_ok"], cb["dev"]["judge_ok"]),
            ("LLM judge, answered only", "judge_ok", pt["n_dev_answered"], pt["dev_judge_answered"],
             cb["dev"]["judge_answered"])):
        calls = "1" if key == "judge_ok" else "0"
        rows.append(f"{name} & {n} & {p[0]:.1f} ({ci(c['rec'])}) & {p[1]:.1f} ({ci(c['fpr'])}) & {calls}\\\\")
    (out / "tab_live.tex").write_text("\n".join(rows), encoding="utf-8")
    put("LiveUnsupCi", ci(cb["dev"]["unsup"]))
    for v, t in (("base", "Base"), ("noeta", "Noeta"), ("slots", "Slots")):
        put(f"Var{t}Ci", f"{cb['var'][v][0]:.1f}--{cb['var'][v][1]:.1f}")
    put("TypDepRecDiffCi", f"{cb['dev']['typed_minus_dep_rec'][0]:.1f} to {cb['dev']['typed_minus_dep_rec'][1]:.1f}")
    put("TypDepFprDiffCi", f"{cb['dev']['typed_minus_dep_fpr'][0]:.1f} to {cb['dev']['typed_minus_dep_fpr'][1]:.1f}")
    assert cb["dev"]["typed_minus_dep_fpr"][0] > 0, "text: typed guard adds false rejections (interval above zero)"

    # ---------------- Table IV (held-out) with clustered intervals (one reply per state)
    hrows = []
    for name, key in (("Deployed $\\Gamma$", "deployed_ok"), ("Typed $\\Gamma_{\\mathrm{T}}$", "typed_ok"),
                      ("Typed $\\Gamma_{\\mathrm{T}}^{(2)}$ (frozen)", "v2_ok")):
        d, h, c = pt["dev"][key], pt["heldout"][key], cb["heldout"][key]
        hrows.append(f"{name} & {d[0]:.1f} & {d[1]:.1f} & {h[0]:.1f} ({ci(c['rec'])}) & {h[1]:.1f} ({ci(c['fpr'])})\\\\")
    (out / "tab_heldout.tex").write_text("\n".join(hrows), encoding="utf-8")
    put("HoVtwoDepRecDiffCi", f"{cb['heldout']['v2_minus_dep_rec'][0]:.1f} to {cb['heldout']['v2_minus_dep_rec'][1]:.1f}")
    assert cb["heldout"]["v2_minus_dep_rec"][0] < 0 < cb["heldout"]["v2_minus_dep_rec"][1], \
        "text: recall difference v2 - deployed on the held-out model includes zero"

    # ---------------- taxonomy
    T = R3["taxonomy"]
    put("TaxN", f"{T['n_total']:,}")
    put("TaxUnsup", str(T["n_unsup_total"]))
    put("TaxNotDev", str(T["n_not_dev"]))
    put("TaxVarN", str(T["n"]["var"]))
    trows = []
    shown = [c for c in T["share"] if T["n_with"][c]["all"] > 0]
    assert "Rate" not in shown, "text: no rate of rise was flagged"
    for c in shown:
        s, p, n = T["share"][c], T["passed"][c], T["n_with"][c]
        cells = [f"{s[g]:.1f}" for g in ("gpt-oss-20b", "gpt-oss-120b", "allam", "var")]
        pas = [("--" if p[k] is None else f"{p[k]:.0f}") for k in ("deployed_ok", "typed_ok", "v2_ok")]
        trows.append(f"{c} & " + " & ".join(cells) + f" & {n['all']} & " + " & ".join(pas) + "\\\\")
    (out / "tab_taxonomy.tex").write_text("\n".join(trows), encoding="utf-8")
    sh = T["share"]
    put("TaxAllamHead", f1(sh["Head-count"]["allam"]))
    put("TaxAllamFact", f1(sh["Misquoted fact"]["allam"]))
    put("TaxAllamDur", f1(sh["Duration"]["allam"]))
    put("TaxOssEtaMin", f1(min(sh["ETA"]["gpt-oss-20b"], sh["ETA"]["gpt-oss-120b"])))
    put("TaxOssEtaMax", f1(max(sh["ETA"]["gpt-oss-20b"], sh["ETA"]["gpt-oss-120b"])))
    put("TaxAllamEta", f1(sh["ETA"]["allam"]))
    put("TaxFactPassDep", f"{T['passed']['Misquoted fact']['deployed_ok']:.0f}")
    put("TaxFactPassVtwo", f"{T['passed']['Misquoted fact']['v2_ok']:.0f}")
    put("TaxWordPassDep", f"{T['passed']['Number word']['deployed_ok']:.0f}")
    put("TaxEtaPassDep", f"{T['passed']['ETA']['deployed_ok']:.0f}")
    assert sh["Head-count"]["gpt-oss-20b"] == sh["Head-count"]["gpt-oss-120b"] == 0 < sh["Head-count"]["allam"], \
        "text: only the held-out model invented head-counts"
    assert sh["Misquoted fact"]["allam"] > 10 * max(sh["Misquoted fact"]["gpt-oss-20b"], sh["Misquoted fact"]["gpt-oss-120b"])
    assert T["passed"]["Misquoted fact"]["v2_ok"] >= T["passed"]["Misquoted fact"]["deployed_ok"], \
        "text: misquoted facts are the class every guard still passes"
    assert all(T["passed"][c]["v2_ok"] in (0.0, None) for c in ("Head-count", "Duration", "Coordinate", "Label or level",
                                                               "Number word")), "text: typed v2 passed none of these"
    assert T["passed"]["Number word"]["deployed_ok"] > 50, "text: the deployed guard passes most number-word errors"

    # ---------------- ablation of guard v2
    A, An = R3["ablation"], R3["ablation_n"]
    lab = {"full": "complete $\\Gamma_{\\mathrm{T}}^{(2)}$", "words": "-- number words", "clock": "-- clock rule",
           "unit": "-- unit binding", "eta": "-- ETA ban", "proc": "-- procedural list"}
    arows = []
    for k in ("full", "words", "clock", "unit", "eta", "proc"):
        a = A[k]
        arows.append(f"{lab[k]} & " + " & ".join(f"{a[s]['rec']:.1f} & {a[s]['fpr']:.1f}" for s in ("dev", "heldout", "var"))
                     + "\\\\")
        if k == "full":
            arows.append("\\midrule")
    (out / "tab_ablation.tex").write_text("\n".join(arows), encoding="utf-8")
    put("AbVarUnsup", str(An["var"]["unsup"]))
    put("AbVarSup", str(An["var"]["sup"]))
    put("AbEtaDevRec", f1(A["eta"]["dev"]["rec"]))
    put("AbEtaVarRec", f1(A["eta"]["var"]["rec"]))
    put("AbProcDevFpr", f1(A["proc"]["dev"]["fpr"]))
    put("AbProcHoFpr", f1(A["proc"]["heldout"]["fpr"]))
    put("AbClockHoRec", f1(A["clock"]["heldout"]["rec"]))
    put("AbFullVarRec", f1(A["full"]["var"]["rec"]))
    assert A["full"]["var"]["rec"] < A["full"]["dev"]["rec"], "text: below its development score"
    assert all(A["unit"][s] == A["full"][s] for s in ("dev", "heldout", "var")), "text: unit binding changed no verdict"
    assert A["eta"]["dev"]["rec"] < A["full"]["dev"]["rec"] - 10, "text: the ETA ban carries most of the dev recall"
    assert A["proc"]["dev"]["fpr"] > 10 and A["proc"]["dev"]["rec"] == A["full"]["dev"]["rec"], \
        "text: the procedural list only prevents false rejections"
    assert A["clock"]["heldout"]["rec"] < A["full"]["heldout"]["rec"] and A["clock"]["dev"] == A["full"]["dev"], \
        "text: the clock rule matters only on the held-out model"

    # ---------------- Eq. (4) against measured misses
    E = R3["eq4"]
    put("EqA", str(E["range"][0]))
    put("EqB", str(E["range"][1]))
    put("EqDigitN", str(E["n_digit_replies"]))
    put("EqPmissMean", f1(100 * E["p_miss_mean"]))
    put("EqPmissMax", f1(100 * E["p_miss_max"]))
    put("EqExpUni", f1(E["expected_uniform"]))
    put("EqExpEmp", f1(E["expected_empirical"]))
    put("EqMeas", nw(E["measured"]))
    put("EqMeasCap", nw(E["measured"], cap=True))
    k = E["dep_miss_kinds"]
    put("MissWordsN", nw(k["words"]))
    put("MissClockN", nw(k["clock"]))
    put("MissDigitN", nw(k["digit"]))
    put("MissOtherN", nw(k["other"]))
    put("MissRestN", nw(k["words"] + k["clock"] + k["other"]))
    assert k["digit"] == E["measured"] and sum(k.values()) == E["dep_miss_n"]
    assert abs(E["measured"] - E["expected_uniform"]) < 1.5, "text: Eq. (4) predicts the digit misses to within a few"
    assert k["words"] + k["clock"] > k["digit"], "text: most misses lie outside Eq. (4)"

    # ---------------- slots-only replies
    Sl = R3["slots"]
    assert len(Sl["residual"]) == 1, "text describes exactly one residual reply"
    r = Sl["residual"][0]
    assert r["flagged_are_state_values"] and r["doubled_unit"] and r["time_after_estimated"], \
        "text: the residual is a state value bound to the wrong quantity by the labelling rule, plus 'Estimated time {time}'"
    assert Sl["extra_number_words_in_passed"] == 0, "text: no number word outside the lexicon in passed replies"
    put("SlotsPassed", str(Sl["passed"]))
    put("SlotsParsed", str(Sl["parsed"]))

    # ---------------- gate break-even
    put("BeR", f"{BE['r_star']:.2f}")
    put("BeLo", f"{BE['boot']['ci'][0]:.2f}")
    put("BeHi", f"{BE['boot']['ci'][1]:.2f}")
    put("BeT", f"{BE['t_at_r_star']:.2f}")
    assert BE["single_crossing"] and BE["gate_beats_none_all_r"] and BE["boot"]["share_no_crossing_in_grid"] == 0
    assert 1 < BE["boot"]["ci"][0] and BE["boot"]["ci"][1] < 5, "text: break-even between the 1:1 and 1:5 settings"
    O = json.loads((work / "p2_offline.json").read_text(encoding="utf-8"))
    h = O["mcnemar"]["heldout_dep_vs_v2"]["unsupported"]
    put("HoDiffW", nw(h["b_only"] - h["a_only"]))
    assert h["b_only"] > h["a_only"]
    V = json.loads((work / "p2_r2_summary.json").read_text(encoding="utf-8"))["variants"]
    assert V["slots"]["words"] < V["base"]["words"] and V["slots"]["tokens"] > V["base"]["tokens"],         "text: placeholder replies shorter but more tokens per call"
    return {"count": count, "nw": nw}
