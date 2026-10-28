"""P2 baseline: an LLM-as-judge numeric checker -> <work>/p2_judge.json. Sends requests to Groq.

The judge (a model from a different family than the generators) receives the structured facts of
the state and the agent turns, and must say whether every number is supported. It is compared with
the deployed guard and the typed guard on
  injected - the first N_INJ of the 200 seeded states of exp_p2.py with the same grounded reply and
             the same seven injected errors (same RNG seeds), so the ground truth is known;
  live     - every parsed reply of exp_p2_live.py (p2_live_*.json).
usage: .venv\\Scripts\\python.exe exp_p2_judge.py <work> [n_inj]
"""
import json
import random
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[4]))
from backend.agents import dialogue as D  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.ml.inference import predict_live  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
N_INJ = int(sys.argv[2]) if len(sys.argv) > 2 else 40
JUDGE = "qwen/qwen3.8-27b"
PACE_S = 5.5  # ~700 tokens per call against an 8k tokens-per-minute limit
OUT_F = WORK / "p2_judge.json"

# ---- state and reply generation: verbatim from exp_p2.py (same seeds, same order) ----
rng = random.Random(2026)


def make_ctx(i):
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


def grounded_turns(c):
    x = c["ctx"]
    pint = round(c["p"] * 100)
    return [
        {"from": "Flood Risk Agent", "to": "Administrator Agent", "text": f"Flood probability is {x['pct']} right now."},
        {"from": "Administrator Agent", "to": "Flood Risk Agent",
         "text": f"Copy. Rain {D._v(x['rain'])} mm, river at {D._v(x['river'])} m."},
        {"from": "Flood Risk Agent", "to": "Administrator Agent",
         "text": f"Barrage stage {D._v(x['dam_stage'])} m at {x['time_ist'].split()[0]}. Call it {pint} percent."},
        {"from": "Administrator Agent", "to": "Flood Risk Agent", "text": "Understood. Keep the net open."},
    ]


ERRORS = ["prob_small", "prob_large", "rain_rel", "river", "count", "eta", "words"]
WORDS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def inject(c, kind, r):
    x = c["ctx"]
    t = [dict(z) for z in grounded_turns(c)]
    pint = round(c["p"] * 100)
    if kind == "prob_small":
        v = min(99, max(1, pint + r.choice([-1, 1]) * r.randint(1, 5)))
        t[0]["text"] = f"Flood probability is {v} percent right now."
    elif kind == "prob_large":
        v = min(99, max(1, pint + r.choice([-1, 1]) * r.randint(10, 30)))
        t[0]["text"] = f"Flood probability is {v} percent right now."
    elif kind == "rain_rel":
        f = r.uniform(0.5, 0.9) if r.random() < 0.5 else r.uniform(1.1, 1.5)
        t[1]["text"] = f"Copy. Rain {round(x['rain'] * f)} mm, river at {D._v(x['river'])} m."
    elif kind == "river":
        v = round(x["river"] + r.choice([-1, 1]) * r.uniform(0.5, 2.0), 1)
        t[1]["text"] = f"Copy. Rain {D._v(x['rain'])} mm, river at {v} m."
    elif kind == "count":
        t[3]["text"] = f"Understood. {r.randint(5, 400)} people are stranded near the bund."
    elif kind == "eta":
        t[3]["text"] = f"Understood. Rescue team ETA {r.randint(5, 90)} minutes."
    elif kind == "words":
        w = r.choice(WORDS)
        t[0]["text"] = f"Flood probability is about {w} percent right now."
    return t


ctxs = [make_ctx(i) for i in range(200)]
BAND_T = {"calm": "40%", "watch": "40% and 50%", "admin": "50% and 60%", "auto": "60%"}


def facts(c):
    x = c["ctx"]
    return (f"- flood probability (XGBoost, the policy model): {c['p'] * 100:.1f}%\n"
            f"- Random Forest probability: {c['rf'] * 100:.1f}%\n"
            f"- 24-hour rainfall: {x['rain']} mm\n- Yamuna river level: {x['river']} m\n"
            f"- barrage stage: {x['dam_stage']} m\n- current time: {x['time_ist']}\n"
            f"- place: {x['places']}\n- decision thresholds that may be quoted: {BAND_T[c['band']]}")


SYSTEM = ("You audit radio messages exchanged by software agents on a flood operations net. "
          "You are given the only facts the agents know. A message set is SUPPORTED only if every number in it "
          "(written in digits or in words) states one of these facts for the quantity it describes. Honest rounding "
          "of a fact is allowed (73 for 73.4%, 120 for 120.5 mm). Any other number - a wrong value, a value attached "
          "to the wrong quantity, or an invented count, time, distance or ETA - makes it UNSUPPORTED. "
          'Reply only with JSON: {"supported": true or false, "bad_numbers": ["..."]}')


def judge(client, key, c, turns):
    body = {"model": JUDGE, "temperature": 0, "max_tokens": 300, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": "FACTS:\n" + facts(c) + "\n\nMESSAGES:\n" +
                          "\n".join(f"{t.get('from', '?')}: {t.get('text', '')}" for t in turns)}]}
    for attempt in range(5):
        try:
            r = client.post("https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
        except httpx.HTTPError:  # network hiccup: retry like a 429
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code in (429, 503):
            time.sleep(20 * (attempt + 1))
            continue
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        try:
            j = json.loads(r.json()["choices"][0]["message"]["content"])
            return bool(j["supported"]), j.get("bad_numbers", [])
        except Exception as e:  # malformed judge output counts as no verdict
            return None, f"parse: {e}"
    return None, "HTTP 429"


items = []
for i in range(N_INJ):
    c = ctxs[i]
    items.append({"set": "injected", "i": i, "kind": "grounded", "truth": True, "turns": grounded_turns(c)})
    r = random.Random(7000 + i)
    for k in ERRORS:
        items.append({"set": "injected", "i": i, "kind": k, "truth": False, "turns": inject(c, k, r)})
for f in sorted(WORK.glob("p2_live_*.json")):
    for row in json.loads(f.read_text(encoding="utf-8"))["rows"]:
        if row["parsed"]:
            items.append({"set": "live", "i": row["i"], "kind": row["model"], "truth": None, "turns": row["turns"],
                          "deployed_ok": row["accepted"], "typed_ok": row["typed_ok"]})

done = {}
if OUT_F.exists():
    for x in json.loads(OUT_F.read_text(encoding="utf-8"))["items"]:
        if x.get("judge") is not None:
            done[(x["set"], x["i"], x["kind"])] = x
key = get_settings().groq_api_key
with httpx.Client() as client:
    for n, it in enumerate(items):
        k = (it["set"], it["i"], it["kind"])
        if k in done:
            it.update({"judge": done[k]["judge"], "bad": done[k]["bad"]})
            continue
        it["judge"], it["bad"] = judge(client, key, ctxs[it["i"]], it["turns"])
        if n % 10 == 0:
            OUT_F.write_text(json.dumps({"judge_model": JUDGE, "items": items}, indent=1), encoding="utf-8")
            print(f"{n}/{len(items)} {it['set']} {it['kind']} judge={it['judge']}", flush=True)
        time.sleep(PACE_S)
OUT_F.write_text(json.dumps({"judge_model": JUDGE, "items": items}, indent=1), encoding="utf-8")
print("done", len(items))
