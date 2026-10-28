"""Deployed and typed guard verdicts on exactly the injected items the LLM judge saw -> <work>/p2_judge_match.json.

Offline. Rebuilds the first N_INJ seeded states and replies (same generator and seeds as exp_p2.py) and runs
each through the production backend.agents.dialogue._llm_turns() with the HTTP client replaced by a stub, as
exp_p2.py does, so the judge, the deployed guard and the typed guard are compared item for item.
usage: .venv\\Scripts\\python.exe exp_p2_judge_match.py <work> [n_inj]
"""
import asyncio
import json
import os
import random
import re
import sys
from pathlib import Path

os.environ["GROQ_API_KEY"] = "offline-stub"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[4]))
from backend.agents import dialogue as D  # noqa: E402
from backend.ml.inference import predict_live  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
N_INJ = int(sys.argv[2]) if len(sys.argv) > 2 else 40


class _Resp:
    status_code = 200

    def __init__(self, c):
        self._c = c

    def json(self):
        return {"choices": [{"message": {"content": self._c}}]}


class _Stub:
    reply = ""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        return _Resp(_Stub.reply)


D.httpx.AsyncClient = _Stub
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


ctxs = [make_ctx() for _ in range(200)]
sys.path.insert(0, str(HERE))
src = (HERE / "exp_p2_judge.py").read_text(encoding="utf-8")
# reuse the reply generator and the typed guard verbatim
ns = {"D": D, "random": random}
exec(src[src.index("def grounded_turns"):src.index("ctxs = [make_ctx")], ns)
src2 = (HERE / "exp_p2_live.py").read_text(encoding="utf-8")
ns["re"] = re
exec(src2[src2.index("WORD_NUM = {"):src2.index("captured = {}")], ns)


def deployed(c, turns):
    _Stub.reply = json.dumps({"turns": turns})
    res, _ = asyncio.run(D._llm_turns(c["band"], c["ctx"], ["Flood Risk Agent", "Administrator Agent"]))
    return res is not None


out = []
for i in range(N_INJ):
    c = ctxs[i]
    out.append({"i": i, "kind": "grounded", "deployed_ok": deployed(c, ns["grounded_turns"](c)),
                "typed_ok": ns["typed_guard"](ns["grounded_turns"](c), c)})
    r = random.Random(7000 + i)
    for k in ns["ERRORS"]:
        t = ns["inject"](c, k, r)
        out.append({"i": i, "kind": k, "deployed_ok": deployed(c, t), "typed_ok": ns["typed_guard"](t, c)})
(WORK / "p2_judge_match.json").write_text(json.dumps(out), encoding="utf-8")
print("items", len(out), "deployed rejects", sum(not x["deployed_ok"] for x in out),
      "typed rejects", sum(not x["typed_ok"] for x in out))
