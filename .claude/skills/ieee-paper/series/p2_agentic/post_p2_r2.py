"""Second-revision numbers for P2 -> macros for nums.tex and the generated tables tab_design.tex, tab_gatecost.tex.

Inputs (work dir): p2_offline.json (exp_p2_offline.py), p2_gate2.json (exp_p2_gate2.py), p2_var_<model>.json
(exp_p2_variants.py, live calls), p2_claim_freeze.json. Variant replies are labelled with the same written
protocol as the development replies (label_p2_live.suggest), applied mechanically: no reply of the variant run
was relabelled by hand. Called from post_p2.py; every claim the text makes about these data is asserted here.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE)]
MODELS = (("openai/gpt-oss-20b", "gpt-oss-20b"), ("openai/gpt-oss-120b", "gpt-oss-120b"))
NUMWORD = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty|fifty|sixty|"
                     r"hundred)\b", re.I)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


def pct(a, b):
    return 100 * a / b if b else float("nan")


def f1(x):
    return f"{x:.1f}"


def extend(put, work, out):
    from claim_guard import claim_ok
    from label_p2_live import suggest, states

    frz = json.loads((work / "p2_claim_freeze.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((HERE / "claim_guard.py").read_bytes()).hexdigest() == frz["sha256"], "claim guard frozen"
    O = json.loads((work / "p2_offline.json").read_text(encoding="utf-8"))
    G2 = json.loads((work / "p2_gate2.json").read_text(encoding="utf-8"))

    # ------------------------------------------------ judge with and without failed calls
    ja, jo = O["judge"]["all"], O["judge"]["answered_only"]
    put("JudFailN", str(O["judge"]["n_failed"]))
    put("JudFailSup", str(O["judge"]["failed_supported"]))
    put("JudFailUnsup", str(O["judge"]["failed_unsupported"]))
    put("JudAnsN", str(jo["nu"] + jo["ns"]))
    put("JudAnsRec", f1(jo["rec"]))
    put("JudAnsFpr", f1(jo["fpr"]))
    put("JudAnsMiss", str(jo["nu"] - jo["tp"]))
    ga = O["judge"]["guards_on_answered"]
    put("JudAnsDepFpr", f1(ga["deployed_ok"]["fpr"]))
    put("JudAnsTypFpr", f1(ga["typed_ok"]["fpr"]))
    put("JudAnsDepRec", f1(ga["deployed_ok"]["rec"]))
    put("JudAnsTypRec", f1(ga["typed_ok"]["rec"]))
    put("JudAllCiLo", f"{ja['ci'][0]:.0f}")
    put("JudAllCiHi", f"{ja['ci'][1]:.0f}")
    assert jo["fpr"] < ga["typed_ok"]["fpr"], "text: without failed calls the judge rejects fewer supported replies than the typed guard"
    assert ja["fpr"] > ga["typed_ok"]["fpr"], "text: counting failures as rejections inflates the judge's false rejections"
    assert O["judge"]["failed_supported"] > O["judge"]["failed_unsupported"]

    # ------------------------------------------------ paired tests
    M = O["mcnemar"]
    h = M["heldout_dep_vs_v2"]
    put("McVtwoRecOnly", str(h["unsupported"]["b_only"]))
    put("McDepRecOnly", str(h["unsupported"]["a_only"]))
    put("McVtwoRecP", f"{h['unsupported']['p']:.2f}")
    put("McVtwoFpOnly", str(h["supported"]["b_only"]))
    put("McVtwoFpP", f"{h['supported']['p']:.2f}")
    d = M["dev_dep_vs_typed"]
    put("McDevTypRecP", f"{d['unsupported']['p']:.3f}")
    put("McDevTypFpP", f"{d['supported']['p']:.3f}")
    assert h["unsupported"]["p"] > 0.05 and h["supported"]["p"] > 0.05, "text: v2 vs deployed not significant on held-out"
    assert d["supported"]["p"] < 0.05 < d["unsupported"]["p"], "text: typed adds false rejections significantly, recall not"

    # ------------------------------------------------ fallback rates and the held-out model's failed calls
    fb = O["fallback"]
    put("FbTwenty", f1(fb["openai/gpt-oss-20b"]["fallback_pct"]))
    put("FbOneTwenty", f1(fb["openai/gpt-oss-120b"]["fallback_pct"]))
    put("FbAllam", f1(fb["allam-2-7b"]["fallback_pct"]))
    ab = fb["allam-2-7b"]["by_band"]
    put("AllamFailAuto", str(ab["auto"][1]))
    put("AllamAutoCalls", str(ab["auto"][0]))
    put("AllamOtherCalls", str(sum(v[0] for k, v in ab.items() if k != "auto")))
    assert sum(v[1] for k, v in ab.items() if k != "auto") == 0, "text: every failed ALLaM call was in the automated band"

    # ------------------------------------------------ x100 rule and protocol-only labels
    assert O["redeployed_matches_stored"] == O["n_rows"], "re-implemented deployed guard matches stored verdicts"
    ns = O["noscale"]
    put("NsDevRec", f1(ns["dev"]["noscale"]["rec"]))
    put("NsDevFpr", f1(ns["dev"]["noscale"]["fpr"]))
    put("NsHoRec", f1(ns["heldout"]["noscale"]["rec"]))
    put("NsHoFpr", f1(ns["heldout"]["noscale"]["fpr"]))
    po = O["protocol_only"]
    put("PoDevUnsup", str(po["unsup"]["dev"]))
    put("PoHoUnsup", str(po["unsup"]["heldout"]))
    for grp, tag in (("dev", "Dev"), ("heldout", "Ho")):
        for k, t in (("deployed_ok", "Dep"), ("typed_ok", "Typ"), ("v2_ok", "Vtwo")):
            put(f"Po{tag}{t}Rec", f1(po[grp][k]["rec"]))
            put(f"Po{tag}{t}Fpr", f1(po[grp][k]["fpr"]))
    assert po["heldout"]["v2_ok"]["fpr"] == 0.0 and po["heldout"]["deployed_ok"]["fpr"] == 0.0, \
        "text: under protocol-only labels neither guard falsely rejects a held-out reply"

    # ------------------------------------------------ qualitative over-claims (dev, held-out)
    oc = O["overclaim"]
    put("OcDev", str(oc["dev"]["overclaims"]))
    put("OcDevPct", f1(pct(oc["dev"]["overclaims"], oc["dev"]["n"])))
    put("OcDevPassDep", str(oc["dev"]["pass"]["deployed_ok"]))
    put("OcDevPassTyp", str(oc["dev"]["pass"]["typed_ok"]))
    put("OcDevPassVtwo", str(oc["dev"]["pass"]["v2_ok"]))
    put("OcDevPassJud", str(oc["dev"]["pass"]["judge_ok"]))
    put("OcDevPassDepPct", f"{pct(oc['dev']['pass']['deployed_ok'], oc['dev']['overclaims']):.0f}")
    put("OcDevPassJudPct", f"{pct(oc['dev']['pass']['judge_ok'], oc['dev']['overclaims']):.0f}")
    put("OcHo", str(oc["heldout"]["overclaims"]))
    assert oc["dev"]["bands"] == ["auto"] and oc["heldout"]["bands"] == ["auto"], "text: over-claims only in the automated band"

    # ------------------------------------------------ the composed check, decomposed
    e = O["e2e_classes"]
    put("EtoEHigh", str(e["p_values_ge_tau"]))
    put("SweepAuto", str(O["sweep_exposure"]["xgb_auto"]))
    put("SweepAutoRel", str(O["sweep_exposure"]["xgb_auto_not_held"]))
    put("SweepN", str(O["sweep_exposure"]["n"]))
    assert e["policy_cases"] == 1002 * 8 * 2 and e["e2e_cases"] == 1001 * 8 * 2 * 2

    # ------------------------------------------------ gate: recall of errors, cost, baselines
    R = G2["rules"]
    rows = []
    lab = {"none": "no gate", "deployed": "$\\delta=0.15$ (deployed)", "delta95": "$\\delta_{95}$ (train CV)",
           "straddle": "straddle only", "calibrated_1_5": "calibrated, $t^{\\ast}$ (no gate)"}
    for k in ("none", "deployed", "delta95", "straddle", "calibrated_1_5"):
        r = R[k]
        ci = r["ci"]["err_recall_pct"]
        rec = f"{r['err_recall_pct']:.1f} ({ci[0]:.0f}--{ci[1]:.0f})" if r["holds"] else "0"
        rows.append(f"{lab[k]} & {r['hold_pct']:.1f} & {rec} & {r['fd']} & {r['md']} & "
                    f"{r['cost_1_1_0.2']:.1f} & {r['cost_1_5_0.2']:.1f}\\\\")
    (out / "tab_gatecost.tex").write_text("\n".join(rows), encoding="utf-8")
    put("GtErrN", str(R["deployed"]["errors"]))
    put("GtDepCaught", str(R["deployed"]["caught"]))
    put("GtDepRecall", f1(R["deployed"]["err_recall_pct"]))
    put("GtStCaught", str(R["straddle"]["caught"]))
    put("GtStRecall", f1(R["straddle"]["err_recall_pct"]))
    put("GtStHolds", str(R["straddle"]["holds"]))
    put("GtDepHolds", str(R["deployed"]["holds"]))
    sm = G2["straddle_minus_deployed_errors_reaching"]
    put("GtMore", str(sm["value"]))
    put("GtMoreLo", f"{sm['ci'][0]:.0f}")
    put("GtMoreHi", f"{sm['ci'][1]:.0f}")
    put("GtCalT", f"{R['calibrated_1_5']['threshold']:.2f}")
    put("GtCostDepFive", f1(R["deployed"]["cost_1_5_0.2"]))
    put("GtCostCalFive", f1(R["calibrated_1_5"]["cost_1_5_0.2"]))
    put("GtCostDepOne", f1(R["deployed"]["cost_1_1_0.2"]))
    put("GtCostNoneOne", f1(R["none"]["cost_1_1_0.2"]))
    assert R["straddle"]["err_recall_pct"] < R["deployed"]["err_recall_pct"] / 2, "text: straddle catches far fewer errors"
    assert sm["ci"][0] > 0, "text: replacing the gap rule lets significantly more errors through"
    assert R["calibrated_1_5"]["cost_1_5_0.2"] < min(R[k]["cost_1_5_0.2"] for k in ("none", "deployed", "delta95", "straddle")), \
        "text: when misses cost 5x, a calibrated single model with a cost threshold beats every gate"
    assert R["deployed"]["cost_1_1_0.2"] == min(R[k]["cost_1_1_0.2"] for k in R), "text: at equal costs the deployed gate is cheapest"
    dt = G2["data"]
    put("ClsEvents", f"{dt['n_events']:,}")
    put("ClsGauges", str(dt["n_gauges"]))
    put("ClsNum", str(dt["n_numeric"]))
    put("ClsCat", str(dt["n_categorical"]))
    put("ClsPos", f"{100 * dt['pos_rate_train']:.1f}")
    put("ClsAucRf", f"{dt['auc']['random_forest']:.3f}")
    put("ClsAucXgb", f"{dt['auc']['xgboost']:.3f}")
    put("ClsAccXgb", f"{100 * dt['acc_at_tau']['xgboost']:.1f}")
    put("ClsAccRf", f"{100 * dt['acc_at_tau']['random_forest']:.1f}")
    put("ClsTOneP", f"{dt['t1d_train_pct']['99']:.0f}")
    put("SweepAboveP", f"{100 * G2['sweep']['share_rain_above_train_p99']:.0f}")

    # ------------------------------------------------ prompt designs (live variant run)
    S = states(150)
    V = []
    for m, _ in MODELS:
        tag = m.split("/")[-1]
        V += json.loads((work / f"p2_var_{tag}.json").read_text(encoding="utf-8"))["rows"]
    labels = json.loads((work / "p2_labels.json").read_text(encoding="utf-8"))["rows"]
    base_old = [x for x in labels if "gpt-oss" in x["model"]]
    stats = {}
    for v in ("base", "noeta", "slots"):
        rr = [r for r in V if r["variant"] == v and not (r["error"] or "").startswith("HTTP 429")]  # rate limit: not a reply
        par = [r for r in rr if r["parsed"]]
        for r in par:
            bad = suggest(r["turns"], S[r["i"]])
            r["label_ok"] = not bad
            r["eta"] = any(w.startswith("ETA") for _, w in bad)
            r["claim_ok"] = claim_ok(r["turns"])
            if v == "slots":
                r["slot_ok"] = not r["slot_violations"]
        unsup = [r for r in par if not r["label_ok"]]
        s = {"calls": len(rr), "parsed": len(par), "unsup": len(unsup), "unsup_pct": pct(len(unsup), len(par)),
             "unsup_ci": wilson(len(unsup), len(par)),
             "eta_pct": pct(sum(r["eta"] for r in par), len(par)),
             "dep_rej_pct": pct(sum(not r["deployed_ok"] for r in par), len(par)),
             "fallback_pct": pct(sum((not r["parsed"]) or (not r["deployed_ok"]) for r in rr), len(rr)),
             "claim_pct": pct(sum(not r["claim_ok"] for r in par), len(par)),
             "tokens": float(np.mean([r["usage"]["total_tokens"] for r in rr if r["usage"]])),
             "out_tokens": float(np.mean([r["usage"]["completion_tokens"] for r in rr if r["usage"]])),
             "words": float(np.mean([sum(len(t["text"].split()) for t in r["turns"]) for r in par])),
             "dep_miss": sum(r["deployed_ok"] for r in unsup)}
        if v == "slots":
            s["slot_viol_pct"] = pct(sum(not r["slot_ok"] for r in par), len(par))
            s["fallback_slot_pct"] = pct(sum(bool((not r["parsed"]) or r["slot_violations"]) for r in rr), len(rr))
            s["unsup_after_slotcheck"] = sum(1 for r in par if r["slot_ok"] and not r["label_ok"])
        stats[v] = s
    put("VarN", str(stats["noeta"]["calls"]))
    put("VarStates", str(len({r["i"] for r in V if r["variant"] == "noeta"})))
    put("VarBaseN", str(stats["base"]["calls"]))
    for v, t in (("base", "Base"), ("noeta", "Noeta"), ("slots", "Slots")):
        s = stats[v]
        put(f"Var{t}Unsup", f1(s["unsup_pct"]))
        put(f"Var{t}Eta", f1(s["eta_pct"]))
        put(f"Var{t}Fb", f1(s["fallback_pct"]))
        put(f"Var{t}Claim", f1(s["claim_pct"]))
        put(f"Var{t}Tok", f"{s['tokens']:.0f}")
        put(f"Var{t}Words", f"{s['words']:.0f}")
        put(f"Var{t}Parsed", str(s["parsed"]))
    put("VarSlotsViol", f1(stats["slots"]["slot_viol_pct"]))
    put("VarSlotsFbSlot", f1(stats["slots"]["fallback_slot_pct"]))
    put("VarSlotsResid", str(stats["slots"]["unsup_after_slotcheck"]))
    old_unsup = pct(sum(not x["suggest_ok"] for x in base_old), len(base_old))
    put("VarOldProtoUnsup", f1(old_unsup))
    rows = []
    names = {"base": "production prompt$^\\ast$", "noeta": "+ no arrival times", "slots": "slots only"}
    for v in ("base", "noeta", "slots"):
        s = stats[v]
        fb = s["fallback_slot_pct"] if v == "slots" else s["fallback_pct"]
        rows.append(f"{names[v]} & {s['calls']} & {s['unsup_pct']:.1f} & {s['eta_pct']:.1f} & {fb:.1f} & "
                    f"{s['claim_pct']:.1f} & {s['tokens']:.0f} & {s['words']:.0f}\\\\")
    (out / "tab_design.tex").write_text("\n".join(rows), encoding="utf-8")
    b, n, sl = stats["base"], stats["noeta"], stats["slots"]
    resid = sl["unsup_after_slotcheck"]
    words = ["no", "one", "two", "three", "four", "five"]
    put("VarSlotsResidW", words[resid] if resid < 6 else str(resid))
    put("VarSlotsResidWCap", (words[resid] if resid < 6 else str(resid)).capitalize())
    put("VarNoetaTokDiff", f"{n['tokens'] - b['tokens']:.0f}")
    cl = {v: stats[v]["claim_pct"] for v in stats}
    assert resid == 1, "text: exactly one slots-only reply passed the slot check and was flagged by the script"
    out_json = {"variants": stats}
    (work / "p2_r2_summary.json").write_text(json.dumps(out_json, indent=1, default=float), encoding="utf-8")
    return stats
