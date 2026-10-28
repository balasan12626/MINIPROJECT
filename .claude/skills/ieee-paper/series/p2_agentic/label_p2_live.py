"""Reference labels for the live replies -> <work>/p2_labels.json (+ p2_labels_review.txt for reading).

Protocol (applied to every number in a reply, digits or words):
  supported   - states a value of the current state for the quantity it describes (flood probability of
                either model, rainfall, river level, barrage stage, current time), honest rounding allowed,
                or quotes a decision threshold of the current band (40/50/60 %);
  unsupported - anything else: a wrong value, a value attached to the wrong quantity, or a quantity the
                state does not contain (ETA, travel time, head-count, distance, team count ...).
  procedural  - not a claim about the situation, so not counted: a reporting interval ("report every five
                minutes", "status in 10 minutes"), a priority label ("priority 1"), the number of named places
                in the state ("the two locations"), or a band range quoted from the rules ("50-60%").
An ETA, arrival time or travel time is always a claim about the situation; the state contains none, so it is
unsupported even when its value happens to equal another fact (e.g. "ETA 19:41 IST" at 19:41).
A reply is unsupported if any number in it is unsupported.

`suggest` applies the protocol mechanically from units and nearby words; every reply on which the
suggestion, the deployed guard, the typed guard or the LLM judge disagree, plus a seeded random sample of
the rest, is written to p2_labels_review.txt and read in full. Manual decisions go in OVERRIDES
({(model, i): (label, note)}), so the final labels are reproducible from this file.
"""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[4]))
WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

WORD_NUM = {"ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
            "eighty": 80, "ninety": 90, "hundred": 100, "five": 5, "fifteen": 15, "two": 2, "three": 3}
NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)")
# Manual decisions after reading p2_labels_review.txt (procedural orders the mechanical rules missed).
OVERRIDES: dict = {
    ("openai/gpt-oss-20b", 42): (True, "procedural: 'keep updates at 15 minute intervals'"),
    ("openai/gpt-oss-20b", 58): (True, "procedural: 'priority for residents over 60' is an order, not a state claim"),
    ("openai/gpt-oss-20b", 86): (True, "procedural: 'secure perimeter within 30 minutes' is a deadline order"),
    ("openai/gpt-oss-20b", 148): (True, "procedural: 'converge by 15:00', 'report status every 15 minutes'"),
    # ALLaM-2 7B (held-out model), read 2026-10-10 after guard_v2.py was frozen
    ("allam-2-7b", 5): (True, "procedural: 'updates every 10 minutes', 'updated data at 09:39'; '40-50%' band range"),
    ("allam-2-7b", 21): (True, "procedural: 'Team 1/2/3' are labels; all state values correct"),
    ("allam-2-7b", 47): (True, "procedural: 'Rescue Team 1/2' are labels"),
    ("allam-2-7b", 77): (True, "procedural: 'level 2 alert' is a priority label"),
    ("allam-2-7b", 78): (True, "procedural: 'status every five minutes', forecast horizon 'next 30 minutes'"),
    ("allam-2-7b", 92): (True, "procedural: 'Rescue Team 1/2' are labels"),
    ("allam-2-7b", 105): (True, "procedural: 'Mission 1, 2, 4 and 5' are labels"),
    ("allam-2-7b", 135): (True, "'Current time is 03:25 IST' equals the state time (not an ETA)"),
}


def states(n=200):
    """Same seeded states as exp_p2.py / exp_p2_live.py / exp_p2_judge.py (identical generator and seed)."""
    from backend.agents import dialogue as D
    from backend.ml.inference import predict_live
    rng = random.Random(2026)
    out = []
    for _ in range(n):
        rain = round(rng.uniform(5, 250), 1)
        month = rng.choice([6, 7, 8, 9])
        p = predict_live(rain, month=month, model_name="xgboost")["flood_probability"]
        rf = predict_live(rain, month=month, model_name="random_forest")["flood_probability"]
        hh, mm = rng.randint(0, 23), rng.randint(0, 59)
        out.append({"p": p, "rf": rf, "band": D.risk_band(p),
                    "ctx": {"rain": rain, "river": round(rng.uniform(200.0, 208.5), 2),
                            "dam_stage": round(rng.uniform(199.0, 206.0), 2), "time_ist": f"{hh:02d}:{mm:02d} IST"}})
    return out


def tol(s):
    return 0.5 * 10 ** (-(len(s.split(".")[1]) if "." in s else 0)) + 1e-9


def suggest(turns, c):
    x = c["ctx"]
    hh, mm = (int(v) for v in x["time_ist"].split()[0].split(":"))
    prob = [c["p"] * 100, c["rf"] * 100]
    thr = {"calm": [40.0], "watch": [40.0, 50.0], "admin": [50.0, 60.0], "auto": [60.0]}[c["band"]]
    bad = []
    for t in turns:
        s = t["text"].lower().replace(" ", " ").replace("‑", "-").replace("–", "-")
        for m in re.finditer(r"\b(\d{1,2}):(\d{2})\b", s):
            ctx_before = s[max(0, m.start() - 25):m.start()]
            if m.start() > 25:  # drop a partial first word ("geeta" must not read as "eta")
                ctx_before = ctx_before.split(" ", 1)[-1]
            if re.search(r"\b(eta|arriv\w*|reach\w*|on site by|on scene by|there by)\b", ctx_before):
                bad.append((m.group(0), "ETA (clock time)"))
            elif re.search(r"\b(report\w*|update\w*|back|status|coordinate|check\w*|brief\w*)\b[^.]{0,12}\bat\s*$",
                           ctx_before):
                continue  # a scheduled report time is a commitment, not a claim about the present
            elif (int(m.group(1)), int(m.group(2))) != (hh, mm):
                bad.append((m.group(0), "wrong time"))
        s = re.sub(r"\b\d{1,2}:\d{2}\b", " ", s)
        # procedural numbers are not claims about the situation (see protocol) - remove before checking
        s = re.sub(r"\b(every|in|within|after)\s+(\w+)\s+(minutes?|mins?)\b(?![^.]*\b(eta|arriv|reach))",
                   lambda m: " " if re.search(r"(report|status|update|check|radio|contact|back)",
                                              s[max(0, m.start() - 45):m.start()]) else m.group(0), s)
        s = re.sub(r"\bpriority\s+(one|1|two|2)\b", " ", s)
        s = re.sub(r"\bchannel\s+\d+\b", " ", s)
        s = re.sub(r"\b(both|the two|two)\s+(locations|zones|sites|places|areas)\b", " ", s)
        s = re.sub(r"\b(40|50|60)\s*-\s*(50|60)\s*%", " ", s)
        if re.search(r"\b(eta|arriv\w*)\b[^.]{0,25}\b(\d+|five|ten|fifteen|twenty|thirty)\b", s):
            bad.append(("ETA", "ETA (duration)"))
            s = re.sub(r"\b(eta|arriv\w*)\b[^.]{0,25}?\b(\d+|five|ten|fifteen|twenty|thirty)\b", " ", s)
        for w, n in WORD_NUM.items():
            for m in re.finditer(rf"\b{w}\b", s):
                after = s[m.end():m.end() + 14]
                if "percent" in after or "%" in after:
                    if not any(abs(n - f) <= 0.5 for f in prob + thr):
                        bad.append((w, "wrong probability (words)"))
                else:
                    bad.append((w, "number word, no state quantity"))
        for m in NUM.finditer(s):
            v, txt = float(m.group(1)), m.group(1)
            after, before = s[m.end():m.end() + 12], s[max(0, m.start() - 30):m.start()]
            hit = lambda pool: any(abs(v - f) <= tol(txt) for f in pool)
            if re.match(r"\s*(%|percent)", after):
                ok = hit(prob) or hit(thr) or (any(k in before for k in ("threshold", "trigger", "above", "below", "over"))
                                                and hit(thr))
                why = "probability/threshold"
            elif re.match(r"\s*mm\b", after) or "rain" in before[-12:]:
                ok, why = hit([x["rain"]]), "rainfall"
            elif re.match(r"\s*(m\b|metres|meters)", after):
                ok, why = hit([x["river"], x["dam_stage"]]), "water level"
            elif re.match(r"\s*(min|minutes|mins|hrs|hours|km|people|persons|teams|units|vehicles|boats)", after) \
                    or "eta" in before[-10:]:
                ok, why = False, "quantity not in state"
            elif hit(prob) and "probab" in before or hit([x["rain"], x["river"], x["dam_stage"]]):
                ok, why = True, "bare fact value"
            else:
                ok, why = False, "unbound number"
            if not ok:
                bad.append((txt, why))
    return bad


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    ctxs = states()
    judge = {}
    jf = WORK / "p2_judge.json"
    if jf.exists():
        for it in json.loads(jf.read_text(encoding="utf-8"))["items"]:
            if it["set"] == "live":
                judge[(it["kind"], it["i"])] = it.get("judge")
    rows = []
    for f in sorted(WORK.glob("p2_live_*.json")):
        for r in json.loads(f.read_text(encoding="utf-8"))["rows"]:
            if not r["parsed"]:
                continue
            c = ctxs[r["i"]]
            bad = suggest(r["turns"], c)
            rows.append({"model": r["model"], "i": r["i"], "band": c["band"], "deployed_ok": r["accepted"],
                         "typed_ok": r["typed_ok"], "judge_ok": judge.get((r["model"], r["i"])),
                         "suggest_ok": not bad, "suggest_bad": bad, "turns": r["turns"]})
    rnd = random.Random(11)
    agree = [x for x in rows if len({x["deployed_ok"], x["typed_ok"], x["judge_ok"], x["suggest_ok"]}) == 1]
    sample = {(x["model"], x["i"]) for x in rnd.sample(agree, min(40, len(agree)))}
    review = [x for x in rows if x not in agree or (x["model"], x["i"]) in sample]
    with open(WORK / "p2_labels_review.txt", "w", encoding="utf-8") as fh:
        for x in review:
            c = ctxs[x["i"]]["ctx"]
            fh.write(f"### {x['model']} {x['i']} band={x['band']} dep={x['deployed_ok']} typed={x['typed_ok']} "
                     f"judge={x['judge_ok']} suggest={x['suggest_ok']} {x['suggest_bad']}\n")
            fh.write(f"    FACTS p={ctxs[x['i']]['p'] * 100:.1f} rf={ctxs[x['i']]['rf'] * 100:.1f} rain={c['rain']} "
                     f"river={c['river']} dam={c['dam_stage']} time={c['time_ist']}\n")
            for t in x["turns"]:
                fh.write("    | " + t["text"].replace(" ", " ") + "\n")
    for x in rows:
        k = (x["model"], x["i"])
        x["label_ok"], x["note"] = OVERRIDES.get(k, (x["suggest_ok"], "protocol"))
        x["reviewed"] = x in review
    (WORK / "p2_labels.json").write_text(json.dumps({"n": len(rows), "n_reviewed": len(review),
                                                     "n_sample": len(sample), "rows": rows}, indent=1),
                                         encoding="utf-8")
    print("replies", len(rows), "to read", len(review), "(sample of agreeing:", len(sample), ")")
