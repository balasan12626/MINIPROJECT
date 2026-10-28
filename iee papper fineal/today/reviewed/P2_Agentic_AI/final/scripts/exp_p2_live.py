"""P2 live LLM study -> <work>/p2_live.json.  Sends real requests to Groq (author-approved).

For the same 200 seeded states as exp_p2.py, calls the production prompt builder
backend.agents.dialogue._llm_turns() once per model, with the model fallback disabled, and
records every parsed reply, whether the deployed guard accepted it, and whether the
prototype typed guard would accept it. Unmatched numbers in rejected replies are stored so
they can be classified. Pacing keeps the request rate under the free-tier limit.
usage: .venv\\Scripts\\python.exe exp_p2_live.py <work> <n_states> <model>
Groq limits tokens per minute per model, so each model runs in its own process, calls are
paced, and an HTTP 429 is retried after a wait. Output: <work>/p2_live_<model-tag>.json
"""
import asyncio
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[4]))
from backend.agents import dialogue as D  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.ml.inference import predict_live  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
N = int(sys.argv[2]) if len(sys.argv) > 2 else 150
MODELS = [sys.argv[3]] if len(sys.argv) > 3 else ["openai/gpt-oss-20b"]
TAG = MODELS[0].split("/")[-1]
PACE_S = 14.0  # ~2k tokens per call against an 8k tokens-per-minute limit

# same state generator and seed as exp_p2.py
rng = random.Random(2026)


def make_ctx():
    rain = round(rng.uniform(5, 250), 1)
    month = rng.choice([6, 7, 8, 9])
    p = predict_live(rain, month=month, model_name="xgboost")["flood_probability"]
    rf = predict_live(rain, month=month, model_name="random_forest")["flood_probability"]
    hh, mm = rng.randint(0, 23), rng.randint(0, 59)
    return {"p": p, "rf": rf, "band": D.risk_band(p),
            "ctx": {"mode": "simulation", "pct": f"{p * 100:.1f}%", "rain": rain,
                    "river": round(rng.uniform(200.0, 208.5), 2), "dam_stage": round(rng.uniform(199.0, 206.0), 2),
                    "models": f"Random Forest {round(rf * 100, 1)}%, XGBoost {round(p * 100, 1)}%;",
                    "time_ist": f"{hh:02d}:{mm:02d} IST", "zone": "Yamuna Pushta / Geeta Colony",
                    "places": "Yamuna Pushta / Geeta Colony", "recent": [], "spike": {}}}


WORD_NUM = {"ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
            "eighty": 80, "ninety": 90, "hundred": 100}
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_SLOT = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent|mm\b|m\b|metres\b|meters\b)?")


def typed_guard(turns, c):  # identical to exp_p2.typed_guard
    x = c["ctx"]
    hh, mm = (int(v) for v in x["time_ist"].split()[0].split(":"))
    band_t = {"calm": [40.0], "watch": [40.0, 50.0], "admin": [50.0, 60.0], "auto": [60.0]}.get(c["band"], [])
    slots = {"prob": [c["p"] * 100, c["rf"] * 100] + band_t, "rain": [x["rain"]],
             "level": [x["river"], x["dam_stage"]]}

    def match(v, dec, pool):
        return any(abs(v - f) <= 0.5 * 10 ** (-dec) + 1e-9 for f in pool)

    for t in turns:
        s = t["text"].lower()
        for m in _TIME.finditer(s):
            if (int(m.group(1)), int(m.group(2))) != (hh, mm):
                return False
        s = _TIME.sub(" ", s)
        for w, n in WORD_NUM.items():
            s = re.sub(rf"\b{w}\b", str(n), s)
        for m in _SLOT.finditer(s):
            v, unit = float(m.group(1)), m.group(2)
            dec = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
            before = s[max(0, m.start() - 25):m.start()]
            if unit in ("%", "percent") or (unit is None and "probab" in before):
                pool = slots["prob"]
            elif unit == "mm" or (unit is None and "rain" in before):
                pool = slots["rain"]
            elif unit in ("m", "metres", "meters"):
                pool = slots["level"]
            else:
                return False
            if not match(v, dec, pool):
                return False
    return True


captured = {}
_real_grounded = D.grounded


def recording_grounded(turns, facts_text, extra=()):
    ok = _real_grounded(turns, facts_text, extra)
    facts = D._fact_numbers(facts_text)
    unmatched = []
    for t in turns or []:
        for m in D._NUM_RE.findall(str(t.get("text") or "")):
            v = float(m)
            dec = len(m.split(".")[1]) if "." in m else 0
            if not any(abs(v - f) <= 0.5 * 10 ** (-dec) + 1e-9 for f in facts):
                unmatched.append(m)
    captured.update({"turns": turns, "ok": ok, "unmatched": unmatched})
    return ok


D.grounded = recording_grounded
settings = get_settings()
ctxs = [make_ctx() for _ in range(N)]
OUT_F = WORK / f"p2_live_{TAG}.json"


def save(rows):  # checkpoint, so an interrupted run resumes instead of starting over
    out = {"date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "models": MODELS, "n_states": N,
           "temperature": 0.85, "rows": rows}
    OUT_F.write_text(json.dumps(out, indent=1), encoding="utf-8")


rows = json.loads(OUT_F.read_text(encoding="utf-8"))["rows"] if OUT_F.exists() else []
done = {(r["model"], r["i"]) for r in rows if r["parsed"] or not (r["error"] and "429" in r["error"])}
rows = [r for r in rows if (r["model"], r["i"]) in done]
for mi, model in enumerate(MODELS):
    settings.groq_model = model
    D.GROQ_MODELS = [model]  # no cross-model fallback: one request per (state, model)
    for i, c in enumerate(ctxs):
        if (model, i) in done:
            continue
        for attempt in range(4):
            captured.clear()
            t0 = time.perf_counter()
            turns, err = asyncio.run(D._llm_turns(c["band"], c["ctx"], ["Flood Risk Agent", "Administrator Agent"]))
            ms = (time.perf_counter() - t0) * 1000
            if not (err and "429" in err):
                break
            time.sleep(30)
        parsed = captured.get("turns")
        row = {"model": model, "i": i, "band": c["band"], "ms": round(ms, 1), "error": err, "attempts": attempt + 1,
               "parsed": parsed is not None, "accepted": turns is not None,
               "typed_ok": typed_guard(parsed, c) if parsed else None,
               "n_numbers": sum(len(D._NUM_RE.findall(t["text"])) for t in parsed) if parsed else None,
               "unmatched": captured.get("unmatched", []),
               "turns": parsed}
        rows.append(row)
        if i % 10 == 0:
            save(rows)
        if i % 20 == 0:
            print(f"{model} {i}/{N} accepted={row['accepted']} err={err}", flush=True)
        time.sleep(PACE_S)
rows.sort(key=lambda r: (r["model"], r["i"]))
save(rows)
for m in MODELS:
    rr = [r for r in rows if r["model"] == m]
    parsed = [r for r in rr if r["parsed"]]
    print(m, "parsed", len(parsed), "/", len(rr), "accepted", sum(r["accepted"] for r in rr),
          "typed_ok", sum(bool(r["typed_ok"]) for r in parsed), "http_err", sum(1 for r in rr if not r["parsed"]))
