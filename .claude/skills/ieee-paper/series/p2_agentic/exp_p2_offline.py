"""P2 revision analyses that need no new model call -> <work>/p2_offline.json.

From the stored live replies, labels, judge verdicts and frozen guard v2:
  - judge scored with and without the calls that failed (counted as rejections in the paper)
  - paired McNemar tests (exact, two-sided) between guards on the same replies
  - deployed template-fallback rate per model (HTTP/parse failures + guard rejections)
  - where the held-out model's failed calls fall (band)
  - the deployed guard without the x100 / /100 rule, on the live replies
  - every guard scored against the mechanical protocol alone (no manual relabelling)
  - qualitative over-claims: which pass each numeric guard; the frozen claim guard
  - the composed dispatch check decomposed into its equivalence classes, and the sweep's exposure
usage: python exp_p2_offline.py <work>
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE)]
WORK = Path(sys.argv[1])
from claim_guard import claim_ok  # noqa: E402


def load(name):
    return json.loads((WORK / name).read_text(encoding="utf-8"))


def mcnemar(a, b):
    """Exact two-sided McNemar on paired booleans (a[i], b[i] = check i rejected?)."""
    n01 = sum(1 for x, y in zip(a, b) if x and not y)
    n10 = sum(1 for x, y in zip(a, b) if y and not x)
    n = n01 + n10
    if n == 0:
        return {"a_only": 0, "b_only": 0, "p": 1.0}
    k = min(n01, n10)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"a_only": n01, "b_only": n10, "p": p}


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [100 * (c - h), 100 * (c + h)]


def rates(rows, key, lab="label_ok"):
    u = [x for x in rows if not x[lab]]
    s = [x for x in rows if x[lab]]
    rej = lambda x: x[key] is not True  # noqa: E731
    tp, fp = sum(map(rej, u)), sum(map(rej, s))
    return {"rec": 100 * tp / len(u), "fpr": 100 * fp / len(s), "tp": tp, "nu": len(u), "fp": fp, "ns": len(s),
            "ci": wilson(tp, len(u))}


out = {}
L_all = load("p2_labels.json")["rows"]
J = load("p2_judge.json")
V = {(x["model"], x["i"]): x["v2_ok"] for x in load("p2_guard_v2.json")["rows"]}
jl = {(it["kind"], it["i"]): it["judge"] for it in J["items"] if it["set"] == "live"}
for x in L_all:
    x["judge_ok"] = jl.get((x["model"], x["i"]), "missing")
    x["v2_ok"] = V[(x["model"], x["i"])]
L = [x for x in L_all if "gpt-oss" in x["model"]]
H = [x for x in L_all if "allam" in x["model"]]

# ---- judge with / without failed calls
ok = [x for x in L if x["judge_ok"] is not None]
failed = [x for x in L if x["judge_ok"] is None]
out["judge"] = {"all": rates(L, "judge_ok"), "answered_only": rates(ok, "judge_ok"),
                "n_failed": len(failed), "failed_unsupported": sum(not x["label_ok"] for x in failed),
                "failed_supported": sum(x["label_ok"] for x in failed),
                "guards_on_answered": {k: rates(ok, k) for k in ("deployed_ok", "typed_ok")}}

# ---- paired tests
def paired(rows, k1, k2):
    u = [x for x in rows if not x["label_ok"]]
    s = [x for x in rows if x["label_ok"]]
    r = lambda x, k: x[k] is not True  # noqa: E731
    return {"unsupported": mcnemar([r(x, k1) for x in u], [r(x, k2) for x in u]),
            "supported": mcnemar([r(x, k1) for x in s], [r(x, k2) for x in s])}


out["mcnemar"] = {"heldout_dep_vs_v2": paired(H, "deployed_ok", "v2_ok"),
                  "heldout_dep_vs_typed": paired(H, "deployed_ok", "typed_ok"),
                  "dev_dep_vs_typed": paired(L, "deployed_ok", "typed_ok"),
                  "dev_judge_vs_typed_answered": paired(ok, "judge_ok", "typed_ok")}

# ---- template fallback per model and failed calls by band
fb = {}
for f in sorted(WORK.glob("p2_live_*.json")):
    rows = json.loads(f.read_text(encoding="utf-8"))["rows"]
    m = rows[0]["model"]
    bands = {}
    for r in rows:
        bands.setdefault(r["band"], [0, 0])
        bands[r["band"]][0] += 1
        bands[r["band"]][1] += (not r["parsed"])
    fb[m] = {"calls": len(rows), "failed": sum(not r["parsed"] for r in rows),
             "rejected": sum(r["parsed"] and not r["accepted"] for r in rows),
             "fallback_pct": 100 * sum(not r["accepted"] for r in rows) / len(rows), "by_band": bands}
out["fallback"] = fb

# ---- deployed guard without the x100 rule, and protocol-only labels
from backend.agents import dialogue as D  # noqa: E402
import exp_p2_variants as EV  # noqa: E402  (functions only; main() is guarded)

ctxs = [EV.make_ctx() for _ in range(150)]
allowed = ["Flood Risk Agent", "Administrator Agent"]
ft = {}
for x in L_all:
    if x["i"] not in ft:
        c = ctxs[x["i"]]
        ft[x["i"]] = EV.facts_text(EV.production_prompt(c["band"], c["ctx"], allowed)[1])
    facts = {float(m) for m in D._NUM_RE.findall(ft[x["i"]])}

    def plain(turns, facts=facts):
        for t in turns:
            for m in D._NUM_RE.findall(t["text"]):
                dec = len(m.split(".")[1]) if "." in m else 0
                if not any(abs(float(m) - f) <= 0.5 * 10 ** (-dec) + 1e-9 for f in facts):
                    return False
        return True

    x["noscale_ok"] = plain(x["turns"])
    x["redep_ok"] = D.grounded(x["turns"], ft[x["i"]])
out["redeployed_matches_stored"] = sum(x["redep_ok"] == x["deployed_ok"] for x in L_all)
out["n_rows"] = len(L_all)
out["noscale"] = {"dev": {"deployed": rates(L, "deployed_ok"), "noscale": rates(L, "noscale_ok")},
                  "heldout": {"deployed": rates(H, "deployed_ok"), "noscale": rates(H, "noscale_ok")}}
out["protocol_only"] = {
    grp: {k: rates(rows, k, "suggest_ok") for k in ("deployed_ok", "typed_ok", "v2_ok")}
    for grp, rows in (("dev", L), ("heldout", H))}
out["protocol_only"]["dev"]["judge_ok"] = rates(L, "judge_ok", "suggest_ok")
out["protocol_only"]["n_changed"] = {"dev": sum(x["label_ok"] != x["suggest_ok"] for x in L),
                                     "heldout": sum(x["label_ok"] != x["suggest_ok"] for x in H)}
out["protocol_only"]["unsup"] = {"dev": sum(not x["suggest_ok"] for x in L), "heldout": sum(not x["suggest_ok"] for x in H)}

# ---- qualitative over-claims
oc = {}
for grp, rows in (("dev", L), ("heldout", H)):
    over = [x for x in rows if not claim_ok(x["turns"])]
    oc[grp] = {"n": len(rows), "overclaims": len(over), "bands": sorted({x["band"] for x in over}),
               "pass": {k: sum(x[k] is True for x in over) for k in ("deployed_ok", "typed_ok", "v2_ok", "judge_ok")},
               "numeric_ok_overclaims": sum(x["label_ok"] for x in over)}
out["overclaim"] = oc

# ---- composed dispatch check: equivalence classes and sweep exposure
p2 = load("p2.json")
e2e = p2["e2e"]
n_high = sum(1 for k in range(1001) if k / 1000 >= 0.60)
out["e2e_classes"] = {"p_values_ge_tau": n_high, "health_combos_failed": 7,
                      "product": n_high * 7, "viol_before": e2e["viol_before"],
                      "policy_cases": p2["policy"]["cases"], "e2e_cases": e2e["cases"]}
assert n_high * 7 == e2e["viol_before"], "2,807 = 401 p-values x 7 failed-health combinations"
rows = p2["dual"]["rows"]
out["sweep_exposure"] = {"n": len(rows), "xgb_auto": sum(r["xgb"] >= 0.6 for r in rows),
                         "xgb_auto_not_held": sum(r["xgb"] >= 0.6 and not r["hold"] for r in rows)}
(WORK / "p2_offline.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items()}, indent=1)[:6000])
