"""Typed guard v2 on the live replies -> <work>/p2_guard_v2.json (offline; no network call).

Development set: gpt-oss-20b and gpt-oss-120b replies (labels from label_p2_live.py).
Held-out set: ALLaM-2 7B replies, read and labelled only after guard_v2.py was frozen; the SHA-256 of
guard_v2.py at freezing time is stored in FROZEN_SHA and checked here.
usage: .venv\\Scripts\\python.exe exp_p2_guard_v2.py <work> [--dev-only]
"""
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE)]
import guard_v2  # noqa: E402
from label_p2_live import states  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
FROZEN_SHA = "b8be86546f311ff21feb23c0a49bc3d4666f8fd6c4ed9598f02b1d075d890c43"  # frozen 2026-10-10T20:45, before any ALLaM reply was read

sha = hashlib.sha256((HERE / "guard_v2.py").read_bytes()).hexdigest()
if FROZEN_SHA is not None:
    assert sha == FROZEN_SHA, "guard_v2.py changed after it was frozen"
ctxs = states(150)
rows = []
for f in sorted(WORK.glob("p2_live_*.json")):
    for r in json.loads(f.read_text(encoding="utf-8"))["rows"]:
        if not r["parsed"]:
            continue
        c = ctxs[r["i"]]
        t0 = time.perf_counter()
        ok = guard_v2.check(r["turns"], c["p"], c["rf"], c["ctx"]["rain"], c["ctx"]["river"], c["ctx"]["dam_stage"],
                            c["ctx"]["time_ist"], c["band"])
        rows.append({"model": r["model"], "i": r["i"], "v2_ok": ok, "us": (time.perf_counter() - t0) * 1e6})
# injected-error set of exp_p2.py (200 states x 8 replies), built before guard v2 existed
src = (HERE / "exp_p2_judge.py").read_text(encoding="utf-8")
ns = {"random": __import__("random")}
from backend.agents import dialogue as D  # noqa: E402
ns["D"] = D
exec(src[src.index("def grounded_turns"):src.index("ctxs = [make_ctx")], ns)
import random  # noqa: E402
inj = {}
ctx200 = states(200)
for i in range(200):
    c = ctx200[i]
    full = {"p": c["p"], "rf": c["rf"], "band": c["band"],
            "ctx": {"pct": f"{c['p'] * 100:.1f}%", **c["ctx"]}}
    args = (c["p"], c["rf"], c["ctx"]["rain"], c["ctx"]["river"], c["ctx"]["dam_stage"], c["ctx"]["time_ist"], c["band"])
    inj.setdefault("grounded", []).append(guard_v2.check(ns["grounded_turns"](full), *args))
    r = random.Random(7000 + i)
    for k in ns["ERRORS"]:
        inj.setdefault(k, []).append(guard_v2.check(ns["inject"](full, k, r), *args))
inj_rate = {k: 100 * sum(not x for x in v) / len(v) for k, v in inj.items()}  # % rejected
print("injected:", {k: round(v, 1) for k, v in inj_rate.items()}, "(grounded = false-rejection %)")
(WORK / "p2_guard_v2.json").write_text(json.dumps({"sha256": sha, "frozen": FROZEN_SHA, "rows": rows,
                                                   "injected_detect_pct": inj_rate}), encoding="utf-8")
lab = {(x["model"], x["i"]): x["label_ok"] for x in json.loads((WORK / "p2_labels.json").read_text(encoding="utf-8"))["rows"]}
dev = [x for x in rows if "gpt-oss" in x["model"]]
u = [x for x in dev if not lab[(x["model"], x["i"])]]
s = [x for x in dev if lab[(x["model"], x["i"])]]
print("sha", sha[:12], "| dev replies", len(dev), "recall %.1f" % (100 * sum(not x["v2_ok"] for x in u) / len(u)),
      "false-rej %.1f" % (100 * sum(not x["v2_ok"] for x in s) / len(s)),
      "| mean us %.0f" % (sum(x["us"] for x in dev) / len(dev)))
if "--dev-only" in sys.argv:
    for x in dev:
        if (not x["v2_ok"]) == lab[(x["model"], x["i"])]:
            print("  disagree", x["model"][11:], x["i"], "v2_ok", x["v2_ok"], "label_ok", lab[(x["model"], x["i"])])
