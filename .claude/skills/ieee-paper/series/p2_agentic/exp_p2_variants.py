"""P2 revision: two prompt designs the reviewer asked for, on live models (author-approved Groq calls).

  base   - the production prompt, unchanged (first N_BASE states only: token cost and drift check)
  noeta  - the production prompt plus one rule that forbids arrival / travel times
  slots  - the narrator writes NO digits; it writes {slot} placeholders and the program renders every
           number from the state (the "do not let the LLM write numbers" design)

The production prompt is rebuilt here and checked, with a stubbed HTTP client, to be byte-identical to the
one backend.agents.dialogue._llm_turns() sends, so the variants differ from production only by the lines
added below. Same 150 seeded states as exp_p2_live.py, temperature 0.85, no cross-model fallback.
usage: .venv\\Scripts\\python.exe exp_p2_variants.py <work> <model> [n_states] [n_base]
Output: <work>/p2_var_<model-tag>.json (checkpointed; an interrupted run resumes).
"""
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE)]
from backend.agents import dialogue as D  # noqa: E402
from backend.config import get_settings  # noqa: E402
import random  # noqa: E402
from backend.ml.inference import predict_live  # noqa: E402

WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
MODEL = sys.argv[2] if len(sys.argv) > 2 else "openai/gpt-oss-20b"
N = int(sys.argv[3]) if len(sys.argv) > 3 else 150
N_BASE = int(sys.argv[4]) if len(sys.argv) > 4 else 50
TAG = MODEL.split("/")[-1]
PACE_S = float(os.environ.get("PACE_S", "14"))
OUT_F = WORK / f"p2_var_{TAG}.json"

NOETA_RULE = ("\nNever state an arrival time, ETA, travel time or 'X minutes away': the state contains none. "
              "Say 'en route' or 'on the way' instead.")
SLOTS = {"probability": "flood probability (policy model)", "rf_probability": "Random Forest probability",
         "xgb_probability": "XGBoost probability", "rain_mm": "rainfall", "river_m": "Yamuna river level",
         "barrage_m": "Yamuna barrage stage", "time": "time now", "threshold": "decision threshold of this band",
         "places": "named places"}
SLOT_RULE = ("\nIMPORTANT: write NO digits and no number words anywhere. Wherever you state a fact, write its slot "
             "name in braces and the program fills in the value. Slots: "
             + "; ".join(f"{{{k}}} = {v}" for k, v in SLOTS.items())
             + ". Do not state any quantity that has no slot (no arrival times, counts, distances or durations). "
               "Example: \"Probability is {probability}, above {threshold}. Move to {places}.\"")
BAND_T = {"calm": "40%", "watch": "50%", "admin": "60%", "auto": "60%"}


# ---- copied verbatim from exp_p2_live.py (that file runs its study on import)
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



def production_prompt(band, ctx, allowed):
    """Capture the exact prompt production builds, by stubbing the HTTP client (no network)."""
    got = {}

    class Stub:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            got["body"] = json
            raise RuntimeError("stub")

    real, D.httpx.AsyncClient = D.httpx.AsyncClient, Stub
    try:
        asyncio.run(D._llm_turns(band, ctx, allowed))
    finally:
        D.httpx.AsyncClient = real
    msgs = got["body"]["messages"]
    return msgs[0]["content"], msgs[1]["content"]


def facts_text(prompt):  # the guard's F: prompt up to the recent-history block (as in production)
    return prompt.split("Recent radio")[0]


def render(turns, c):
    x = c["ctx"]
    vals = {"probability": x["pct"], "rf_probability": f"{round(c['rf'] * 100, 1)}%",
            "xgb_probability": f"{round(c['p'] * 100, 1)}%", "rain_mm": f"{D._v(x['rain'])} mm",
            "river_m": f"{D._v(x['river'])} m", "barrage_m": f"{D._v(x['dam_stage'])} m", "time": x["time_ist"],
            "threshold": BAND_T[c["band"]], "places": x["places"]}
    bad = []
    out = []
    for t in turns:
        s = t["text"]
        for name in re.findall(r"\{([^{}]*)\}", s):
            if name not in vals:
                bad.append(("unknown slot", name))
        if re.search(r"\d", re.sub(r"\{[^{}]*\}", "", s)):
            bad.append(("digit in raw text", s))
        if re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty|fifty|sixty|"
                     r"hundred)\b", s, re.I):
            bad.append(("number word in raw text", s))
        out.append({**t, "text": re.sub(r"\{([^{}]*)\}", lambda m: vals.get(m.group(1), m.group(0)), s)})
    return out, bad


async def call(system, user):
    key = get_settings().groq_api_key.strip()
    body = D.groq_body(MODEL, 0.85, 700, [{"role": "system", "content": system}, {"role": "user", "content": user}])
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(D.GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=body)
    ms = (time.perf_counter() - t0) * 1000
    if r.status_code >= 400:
        return None, None, ms, f"HTTP {r.status_code}"
    js = r.json()
    content = ((js.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return content, js.get("usage") or {}, ms, None


def main():
    ctxs = [make_ctx() for _ in range(N)]
    allowed = ["Flood Risk Agent", "Administrator Agent"]
    rows = json.loads(OUT_F.read_text(encoding="utf-8"))["rows"] if OUT_F.exists() else []
    done = {(r["variant"], r["i"]) for r in rows if not (r["error"] or "").startswith("HTTP 429")}
    rows = [r for r in rows if (r["variant"], r["i"]) in done]
    jobs = [("noeta", i) for i in range(N)] + [("slots", i) for i in range(N)] + [("base", i) for i in range(N_BASE)]
    jobs.sort(key=lambda v: (v[1], v[0]))  # interleave variants, so a stopped run is still balanced
    for variant, i in jobs:
        if (variant, i) in done:
            continue
        c = ctxs[i]
        system, prompt = production_prompt(c["band"], c["ctx"], allowed)
        head, tail = prompt.rsplit("\nJSON only:", 1)
        if variant == "noeta":
            prompt = head + NOETA_RULE + "\nJSON only:" + tail
        elif variant == "slots":
            prompt = head + SLOT_RULE + "\nJSON only:" + tail
        for attempt in range(4):
            content, usage, ms, err = asyncio.run(call(system, prompt))
            if not (err and "429" in err):
                break
            time.sleep(30)
        turns = D._parse_turns(content, set(allowed)) if content else None
        row = {"variant": variant, "model": MODEL, "i": i, "band": c["band"], "ms": round(ms, 1), "error": err,
               "usage": usage, "parsed": turns is not None, "raw_turns": turns}
        if turns:
            if variant == "slots":
                rendered, bad = render(turns, c)
                row.update({"slot_violations": bad, "turns": rendered})
            else:
                row["turns"] = turns
            ft = facts_text(production_prompt(c["band"], c["ctx"], allowed)[1])
            row["deployed_ok"] = D.grounded(row["turns"], ft)
            row["typed_ok"] = typed_guard(row["turns"], c)
        rows.append(row)
        if len(rows) % 10 == 0:
            save(rows)
            print(f"{TAG} {variant} {i} parsed={row['parsed']} err={err}", flush=True)
        time.sleep(PACE_S)
    rows.sort(key=lambda r: (r["variant"], r["i"]))
    save(rows)
    for v in ("base", "noeta", "slots"):
        rr = [r for r in rows if r["variant"] == v]
        print(v, "calls", len(rr), "parsed", sum(r["parsed"] for r in rr))


def save(rows):
    OUT_F.write_text(json.dumps({"date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "model": MODEL, "temperature": 0.85, "noeta_rule": NOETA_RULE,
                                 "slot_rule": SLOT_RULE, "rows": rows}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
