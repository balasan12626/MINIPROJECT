"""P2 third revision: analyses of the stored replies only (no model call) -> <work>/p2_r3.json.

  1. error taxonomy over every stored reply (development, held-out, prompt-design run), categories assigned
     by keyword rules on the context of each number the labelling script flagged (no reading, no new labels)
  2. state-clustered bootstrap intervals (both development models answer the same states)
  3. component ablation of the frozen typed guard v2 (guard_v2_ablate, asserted equal to guard_v2 when complete)
  4. Eq. (4) miss probability of the deployed guard for the observed range of digit arrival times,
     against the measured misses
  5. the slots-only replies: the residual reply and a scan for number words outside the slot check's lexicon
usage: .venv\\Scripts\\python.exe exp_p2_r3.py <work>
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE)]
WORK = Path(sys.argv[1])

import guard_v2  # noqa: E402
import guard_v2_ablate as GA  # noqa: E402
from label_p2_live import states, suggest  # noqa: E402


def load(n):
    return json.loads((WORK / n).read_text(encoding="utf-8"))


S = states(150)
L_all = load("p2_labels.json")["rows"]
V2 = {(x["model"], x["i"]): x["v2_ok"] for x in load("p2_guard_v2.json")["rows"]}
jl = {(it["kind"], it["i"]): it["judge"] for it in load("p2_judge.json")["items"] if it["set"] == "live"}
for x in L_all:
    x["v2_ok"] = V2[(x["model"], x["i"])]
    x["judge_ok"] = jl.get((x["model"], x["i"]))
    x["set"] = "dev" if "gpt-oss" in x["model"] else "heldout"


def args(i):
    c = S[i]
    return (c["p"], c["rf"], c["ctx"]["rain"], c["ctx"]["river"], c["ctx"]["dam_stage"], c["ctx"]["time_ist"], c["band"])


VAR = []
for tag in ("gpt-oss-20b", "gpt-oss-120b"):
    for r in load(f"p2_var_{tag}.json")["rows"]:
        if (r["error"] or "").startswith("HTTP 429") or not r["parsed"]:
            continue
        bad = suggest(r["turns"], S[r["i"]])
        VAR.append({"model": r["model"], "i": r["i"], "band": r["band"], "set": "var_" + r["variant"],
                    "variant": r["variant"], "turns": r["turns"], "deployed_ok": r["deployed_ok"],
                    "typed_ok": r["typed_ok"], "v2_ok": guard_v2.check(r["turns"], *args(r["i"])),
                    "label_ok": not bad, "suggest_ok": not bad, "suggest_bad": bad,
                    "slot_violations": r.get("slot_violations")})
ALL = L_all + VAR
out = {"n": {"dev": sum(x["set"] == "dev" for x in ALL), "heldout": sum(x["set"] == "heldout" for x in ALL),
             "var": len(VAR)}}

# ---------------------------------------------------------------- 1. taxonomy
HEAD = re.compile(r"^\s*(?:[-+]\s*[\d,]+\s*)?(?:\)\s*)?(?:[a-z-]+\s+){0,2}(?:people|persons?|residents?|families|"
                  r"households|individuals|casualt\w*|affected|evacuees?|victims?|lives|injur\w*|dead|deaths?|"
                  r"stranded|civilians?|citizens?|inhabitants|homes|houses|children|elderly|patients|trapped|"
                  r"confirmed|reported|rescued|at\s+risk)\b")
HEAD_BEFORE = re.compile(r"(?:casualt\w*|residents|affected|stranded|people|total)[^.]{0,20}$")
RATE = re.compile(r"(?:per\s+hour|/\s*h(?:r|our)?\b|per\s+min|an\s+hour|cm/|m/|mm/)")
RATE_BEFORE = re.compile(r"(?:rate|rising|rise|risen|increas\w*|by)[^.]{0,12}$")
DUR = re.compile(r"^\s*(?:-\s*)?(?:min\w*|hours?|hrs?\b|h\b|sec\w*|days?)")
COORD = re.compile(r"(?:°|\blat\w*|\blon\w*|coordinat\w*|\bgps\b|^\s*[ns]\b|^\s*[ew]\b|,\s*7\d\.\d)")
LABEL_BEFORE = re.compile(r"\b(?:level|team|junction|stage|amb|mission|phase|unit|zone|sector|alert|category|"
                          r"grade|number|no)\b[\s:#-]*$")


def category(tok, why, turns):
    if why.startswith("ETA"):
        return "ETA"
    if why in ("probability/threshold", "rainfall", "water level", "wrong time", "wrong probability (words)"):
        return "Misquoted fact"
    if why == "number word, no state quantity":
        return "Number word"
    text = " ".join(t["text"] for t in turns).lower().replace(" ", " ")
    m = re.search(rf"(?<![\w.]){re.escape(tok)}(?![\d])", text)
    if not m:
        return "Other"
    after, before = text[m.end():m.end() + 25], text[max(0, m.start() - 25):m.start()]
    if COORD.search(after) or "coordinat" in before or re.search(r"\b(lat|lon)\w*", before):
        return "Coordinate"
    if LABEL_BEFORE.search(before):
        return "Label or level"
    if HEAD.search(after) or HEAD_BEFORE.search(before):
        return "Head-count"
    if RATE.search(after[:20]) or RATE_BEFORE.search(before):
        return "Rate"
    if DUR.search(after):
        return "Duration"
    return "Other"


CATS = ["ETA", "Head-count", "Rate", "Duration", "Coordinate", "Label or level", "Misquoted fact", "Number word", "Other"]
for x in ALL:
    x["cats"] = sorted({category(t, w, x["turns"]) for t, w in x["suggest_bad"]}) if not x["label_ok"] else []
    if len(x["cats"]) > 1 and "Other" in x["cats"]:
        x["cats"].remove("Other")  # "Other" only for a reply with no categorised number
    if not x["label_ok"] and not x["cats"]:
        x["cats"] = ["Other"]
groups = {"gpt-oss-20b": [x for x in L_all if x["model"].endswith("-20b")],
          "gpt-oss-120b": [x for x in L_all if x["model"].endswith("120b")],
          "allam": [x for x in L_all if "allam" in x["model"]], "var": VAR}
tax = {"n": {g: len(v) for g, v in groups.items()}, "share": {}, "passed": {}, "n_with": {}}
for c in CATS:
    tax["share"][c] = {g: 100 * sum(c in x["cats"] for x in v) / len(v) for g, v in groups.items()}
    w = [x for x in ALL if c in x["cats"]]
    w2 = [x for x in w if x["set"] != "dev"]  # replies not used to design guard v2
    tax["n_with"][c] = {"all": len(w), "not_dev": len(w2)}
    tax["passed"][c] = {"deployed_ok": 100 * sum(x["deployed_ok"] for x in w) / len(w) if w else None,
                        "typed_ok": 100 * sum(x["typed_ok"] for x in w) / len(w) if w else None,
                        "v2_ok": 100 * sum(x["v2_ok"] for x in w2) / len(w2) if w2 else None}
tax["n_unsup"] = {g: sum(not x["label_ok"] for x in v) for g, v in groups.items()}
tax["n_total"] = len(ALL)
tax["n_unsup_total"] = sum(not x["label_ok"] for x in ALL)
tax["n_not_dev"] = sum(x["set"] != "dev" for x in ALL)
out["taxonomy"] = tax

# ---------------------------------------------------------------- 2. state-clustered bootstrap
rng = np.random.default_rng(2026)
B = 2000


def rates(rows, key, lab="label_ok"):
    u = [x for x in rows if not x[lab]]
    s = [x for x in rows if x[lab]]
    rej = lambda x: x[key] is not True  # noqa: E731  no verdict fails closed
    return (100 * sum(map(rej, u)) / len(u) if u else np.nan, 100 * sum(map(rej, s)) / len(s) if s else np.nan)


def cluster_boot(rows, fn):
    by = {}
    for x in rows:
        by.setdefault(x["i"], []).append(x)
    keys = sorted(by)
    vals = []
    for _ in range(B):
        pick = rng.choice(keys, len(keys), replace=True)
        rr = [x for k in pick for x in by[k]]
        vals.append(fn(rr))
    vals = np.array(vals, dtype=float)
    return [float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))]


dev = [x for x in L_all if x["set"] == "dev"]
ho = [x for x in L_all if x["set"] == "heldout"]
dev_ans = [x for x in dev if x["judge_ok"] is not None]
cb = {"dev": {}, "heldout": {}, "var": {}}
cb["dev"]["unsup"] = cluster_boot(dev, lambda r: 100 * sum(not x["label_ok"] for x in r) / len(r))
for key in ("deployed_ok", "typed_ok", "v2_ok", "judge_ok"):
    cb["dev"][key] = {"rec": cluster_boot(dev, lambda r, k=key: rates(r, k)[0]),
                      "fpr": cluster_boot(dev, lambda r, k=key: rates(r, k)[1])}
cb["dev"]["judge_answered"] = {"rec": cluster_boot(dev_ans, lambda r: rates(r, "judge_ok")[0]),
                               "fpr": cluster_boot(dev_ans, lambda r: rates(r, "judge_ok")[1])}
cb["dev"]["typed_minus_dep_rec"] = cluster_boot(dev, lambda r: rates(r, "typed_ok")[0] - rates(r, "deployed_ok")[0])
cb["dev"]["typed_minus_dep_fpr"] = cluster_boot(dev, lambda r: rates(r, "typed_ok")[1] - rates(r, "deployed_ok")[1])
cb["heldout"]["unsup"] = cluster_boot(ho, lambda r: 100 * sum(not x["label_ok"] for x in r) / len(r))
for key in ("deployed_ok", "typed_ok", "v2_ok"):
    cb["heldout"][key] = {"rec": cluster_boot(ho, lambda r, k=key: rates(r, k)[0]),
                          "fpr": cluster_boot(ho, lambda r, k=key: rates(r, k)[1])}
cb["heldout"]["v2_minus_dep_rec"] = cluster_boot(ho, lambda r: rates(r, "v2_ok")[0] - rates(r, "deployed_ok")[0])
cb["heldout"]["v2_minus_dep_fpr"] = cluster_boot(ho, lambda r: rates(r, "v2_ok")[1] - rates(r, "deployed_ok")[1])
for v in ("base", "noeta", "slots"):
    rows = [x for x in VAR if x["variant"] == v]
    cb["var"][v] = cluster_boot(rows, lambda r: 100 * sum(not x["label_ok"] for x in r) / len(r))
out["cluster_boot"] = cb
out["point"] = {"dev": {k: rates(dev, k) for k in ("deployed_ok", "typed_ok", "v2_ok", "judge_ok")},
                "dev_judge_answered": rates(dev_ans, "judge_ok"),
                "heldout": {k: rates(ho, k) for k in ("deployed_ok", "typed_ok", "v2_ok")},
                "n_dev_answered": len(dev_ans)}

# ---------------------------------------------------------------- 3. ablation of guard v2
for x in ALL:
    assert GA.check(x["turns"], *args(x["i"])) == x["v2_ok"], "ablation module reproduces the frozen guard"
abl = {}
sets = {"dev": dev, "heldout": ho, "var": VAR}
for name, off in [("full", ())] + [(c, (c,)) for c in GA.COMPONENTS]:
    abl[name] = {}
    for sname, rows in sets.items():
        for x in rows:
            x["_ab"] = GA.check(x["turns"], *args(x["i"]), off=frozenset(off))
        rec, fpr = rates(rows, "_ab")
        abl[name][sname] = {"rec": rec, "fpr": fpr}
out["ablation"] = abl
out["ablation_n"] = {k: {"unsup": sum(not x["label_ok"] for x in v), "sup": sum(x["label_ok"] for x in v)}
                     for k, v in sets.items()}

# ---------------------------------------------------------------- 4. Eq. (4) for digit arrival times
import exp_p2_variants as EV  # noqa: E402
from backend.agents import dialogue as D  # noqa: E402

ctxs = [EV.make_ctx() for _ in range(150)]
facts = {}
for i in range(150):
    c = ctxs[i]
    assert abs(c["p"] - S[i]["p"]) < 1e-12 and c["ctx"]["river"] == S[i]["ctx"]["river"], "same seeded states"
    ft = EV.facts_text(EV.production_prompt(c["band"], c["ctx"], ["Flood Risk Agent", "Administrator Agent"])[1])
    fs = {float(m) for m in D._NUM_RE.findall(ft)}
    facts[i] = fs | {100 * f for f in fs} | {f / 100 for f in fs}
ETAD = re.compile(r"\b(?:eta|arriv\w*)\b[^.]{0,25}?\b(\d+)\s*(?:-\s*)?(?:min|minutes|mins)\b")
WORDETA = re.compile(r"\b(?:eta|arriv\w*)\b[^.]{0,25}?\b(five|ten|fifteen|twenty|thirty|forty)\b")


def passes(n, i):
    return any(abs(n - f) <= 0.5 + 1e-9 for f in facts[i])


unsup_dev = [x for x in dev if not x["label_ok"]]
digit = []
for x in unsup_dev:
    txt = " ".join(t["text"] for t in x["turns"]).lower()
    vals = [int(v) for v in ETAD.findall(txt)]
    whys = {w for _, w in x["suggest_bad"]}
    if vals and whys == {"ETA (duration)"} and not WORDETA.search(txt):
        digit.append((x, vals))
allv = [v for _, vs in digit for v in vs]
a, b = min(allv), max(allv)
pm = {i: sum(passes(n, i) for n in range(a, b + 1)) / (b - a + 1) for i in range(150)}
exp_uniform = sum(np.prod([pm[x["i"]]] * len(vs)) for x, vs in digit)
vals_u, cnt = np.unique(allv, return_counts=True)
freq = dict(zip(vals_u.tolist(), (cnt / cnt.sum()).tolist()))
exp_emp = sum(np.prod([sum(f for v, f in freq.items() if passes(v, x["i"]))] * len(vs)) for x, vs in digit)
meas = sum(x["deployed_ok"] for x, _ in digit)
dep_miss = [x for x in unsup_dev if x["deployed_ok"]]


def miss_kind(x):
    whys = {w for _, w in x["suggest_bad"]}
    txt = " ".join(t["text"] for t in x["turns"]).lower()
    if "ETA (clock time)" in whys:
        return "clock"
    if WORDETA.search(txt):
        return "words"
    if whys == {"ETA (duration)"} and ETAD.search(txt):
        return "digit"
    return "other"


out["eq4"] = {"range": [a, b], "n_digit_replies": len(digit), "n_values": len(allv),
              "p_miss_mean": float(np.mean([pm[x["i"]] for x, _ in digit])),
              "p_miss_min": float(min(pm[x["i"]] for x, _ in digit)),
              "p_miss_max": float(max(pm[x["i"]] for x, _ in digit)),
              "expected_uniform": float(exp_uniform), "expected_empirical": float(exp_emp), "measured": int(meas),
              "top_values": sorted(freq.items(), key=lambda kv: -kv[1])[:5],
              "dep_miss_kinds": {k: sum(miss_kind(x) == k for x in dep_miss) for k in ("words", "clock", "digit", "other")},
              "dep_miss_n": len(dep_miss)}

# ---------------------------------------------------------------- 5. slots-only replies
slots = [x for x in VAR if x["variant"] == "slots"]
passed = [x for x in slots if not x["slot_violations"]]
resid = [x for x in passed if not x["label_ok"]]
EXTRA = re.compile(r"\b(eleven|twelve|thirteen|fourteen|sixteen|seventeen|eighteen|nineteen|seventy|eighty|ninety|"
                   r"thousand|million|lakh|crore|dozens?|couple|half|quarter)\b", re.I)
raw = {}
for tag in ("gpt-oss-20b", "gpt-oss-120b"):
    for r in load(f"p2_var_{tag}.json")["rows"]:
        if r["variant"] == "slots" and r["parsed"]:
            raw[(r["model"], r["i"])] = r["raw_turns"]
rd = []
for x in resid:
    c = S[x["i"]]["ctx"]
    state_vals = [S[x["i"]]["p"] * 100, S[x["i"]]["rf"] * 100, c["rain"], c["river"], c["dam_stage"]]
    rd.append({"model": x["model"], "i": x["i"], "flags": x["suggest_bad"],
               "flagged_are_state_values": all(any(abs(float(t) - v) < 1e-6 for v in state_vals)
                                               for t, _ in x["suggest_bad"]),
               "doubled_unit": any(re.search(r"\}\s*(mm|metres|meters|m)\b", t["text"]) for t in raw[(x["model"], x["i"])]),
               "time_after_estimated": any(re.search(r"estimated time\s*\{time\}", t["text"], re.I)
                                           for t in raw[(x["model"], x["i"])])})
out["slots"] = {"parsed": len(slots), "passed": len(passed), "residual": rd,
                "extra_number_words_in_passed": sum(any(EXTRA.search(t["text"]) for t in raw[(x["model"], x["i"])])
                                                    for x in passed),
                "extra_words_examples": [t["text"] for x in passed for t in raw[(x["model"], x["i"])]
                                         if EXTRA.search(t["text"])][:6]}
(WORK / "p2_r3.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
print(json.dumps(out, indent=1, default=float)[:9000])
if "--show-other" in sys.argv:
    for x in ALL:
        if "Other" in x["cats"]:
            print(x["set"], x["model"], x["i"], x["suggest_bad"])
