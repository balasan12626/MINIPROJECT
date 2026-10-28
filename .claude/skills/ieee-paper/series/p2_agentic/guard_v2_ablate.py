"""Component ablation of the frozen typed guard v2 (guard_v2.py is not modified; it stays frozen by hash).

check(..., off=set()) is guard_v2.check with named components switched off. With off=set() it must return the
same verdict as guard_v2.check on every reply; exp_p2_r3.py asserts this before any ablation is reported.
Components:
  "words"  - number words are converted to digits (off: number words are invisible, as in the deployed guard)
  "clock"  - a clock time must equal the current time (off: clock times are dropped unchecked)
  "unit"   - a number is checked only against the quantity its unit or preceding word names
             (off: every number is checked against the union of all state values and thresholds; a number that
             names no quantity is then accepted if it matches any of them)
  "eta"    - any arrival time is rejected (off: no ETA rule)
  "proc"   - procedural numbers are removed before checking (off: they are checked like any other number)
"""
import re

from guard_v2 import ETA, NUM, PROC, SLOT_WORDS, WORDS, _W, CLEAN, _close

COMPONENTS = ("words", "clock", "unit", "eta", "proc")


def check(turns, p, rf, rain, river, dam, time_ist, band, off=frozenset()):
    hh, mm = (int(x) for x in time_ist.split()[0].split(":"))
    thr = {"calm": [40.0], "watch": [40.0, 50.0], "admin": [50.0, 60.0], "auto": [60.0]}.get(band, [])
    pools = {"prob": [p * 100, rf * 100] + thr, "rain": [rain], "level": [river, dam]}
    union = pools["prob"] + pools["rain"] + pools["level"]
    for t in turns:
        s = str(t.get("text") or "").lower().translate(CLEAN)
        if "eta" not in off and ETA.search(s):
            return False
        if "proc" not in off:
            for rx in PROC:
                s = rx.sub(" ", s)
        if "clock" not in off:
            for m in re.finditer(r"\b(\d{1,2}):(\d{2})\b", s):
                if (int(m.group(1)), int(m.group(2))) != (hh, mm):
                    return False
        s = re.sub(r"\b\d{1,2}:\d{2}\b", " ", s)
        if "words" not in off:
            s = re.sub(rf"\b({_W})\b", lambda m: str(WORDS[m.group(1)]), s)
        for m in re.finditer(NUM + r"\s*(%|percent|mm\b|millimet\w*|m\b|metres?\b|meters?\b)?", s):
            v, unit = float(m.group(1)), m.group(2)
            dec = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
            if "unit" in off:
                if not _close(v, dec, union):
                    return False
                continue
            before = s[max(0, m.start() - 28):m.start()]
            if unit in ("%", "percent"):
                pool = pools["prob"]
            elif unit and (unit.startswith("mm") or unit.startswith("millimet")):
                pool = pools["rain"]
            elif unit:
                pool = pools["level"]
            else:
                last = max(((before.rfind(w), k) for k, ws in SLOT_WORDS.items() for w in ws), default=(-1, None))
                if last[0] < 0:
                    return False
                pool = pools[last[1]]
            if not _close(v, dec, pool):
                return False
    return True
