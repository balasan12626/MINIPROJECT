"""Slot-typed numeric guard, version 2 (prototype, not deployed).

Designed only from the gpt-oss-20b / gpt-oss-120b live replies (development set). It is frozen before the
ALLaM replies are read: exp_p2_guard_v2.py records the SHA-256 of this file next to the results.

Changes from the first typed guard (exp_p2.typed_guard):
  * procedural numbers are not claims about the situation and are skipped: reporting intervals
    ("report every 5 minutes", "status in 10 minutes"), scheduled report times ("update at 10:15 IST"),
    priority labels, radio channels, the count of named places ("the two locations"), band ranges
    ("50-60%") and deadlines given as orders ("within 30 minutes", "by 15:00");
  * any arrival time is unsupported, as a duration or a clock time, in digits or words, because the state
    holds none ("ETA 10 minutes", "arrive by 23:25", "ETA about ten minutes");
  * a number without a unit binds to the quantity named just before it ("barrage 202.26", "probability 80.5").
"""
import re

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
         "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}
_W = "|".join(sorted(WORDS, key=len, reverse=True))
NUM = r"(\d+(?:\.\d+)?)"
CLEAN = str.maketrans({" ": " ", "‑": "-", "–": "-", "—": "-", " ": " "})

ETA = re.compile(rf"\b(eta|e\.t\.a|arriv\w*|reach\w* (?:the )?(?:site|scene|zone|location|colony|pushta)|"
                 rf"on (?:site|scene) (?:by|in)|there (?:by|in)|expected (?:in|by)|"
                 rf"estimated time of arrival)\b[^.;!?]{{0,30}}?\b(\d{{1,2}}:\d{{2}}|{NUM[1:-1]}|{_W})\b")
PROC = [
    re.compile(rf"\b(report\w*|update\w*|status|check\w*|back|contact|radio)\b[^.;!?]{{0,30}}?"
               rf"\b(every|in|within|after|at)\s+(?:\d{{1,2}}:\d{{2}}(?:\s*ist)?|\d+(?:\.\d+)?|{_W})"
               rf"(?:\s*-?\s*(?:minutes?|mins?|min\b|hours?))?"),
    re.compile(rf"\b(every|at)\s+(?:\d+|{_W})\s*-?\s*(?:minute|min)\s+intervals?\b"),
    re.compile(rf"\b\d+\s*-\s*minute\s+intervals?\b"),
    re.compile(rf"\bpriority\s+(?:\d|{_W})\b"),
    re.compile(r"\bchannel\s+\d+\b"),
    re.compile(rf"\b(?:both|the\s+two|two|all\s+two)\s+(?:locations|zones|sites|places|areas|colonies)\b"),
    re.compile(r"\b(?:40|50|60)\s*-\s*(?:50|60)\s*%"),
    re.compile(rf"\b(within|in)\s+(?:\d+|{_W})\s*-?\s*(?:minutes?|mins?)\b"),
    re.compile(r"\bby\s+\d{1,2}:\d{2}\b"),
    re.compile(rf"\b(?:residents|people|persons|those)\s+(?:over|above|under)\s+\d+\b"),
]
SLOT_WORDS = {"prob": ("probab", "risk", "chance", "xgboost", "forest", "model", "confidence", "score"),
              "rain": ("rain",), "level": ("river", "yamuna", "barrage", "level", "stage", "dam")}


def _close(v, dec, pool):
    return any(abs(v - f) <= 0.5 * 10 ** (-dec) + 1e-9 for f in pool)


def check(turns, p, rf, rain, river, dam, time_ist, band):
    """True if every number in the turns is a supported fact or procedural; False otherwise."""
    hh, mm = (int(x) for x in time_ist.split()[0].split(":"))
    thr = {"calm": [40.0], "watch": [40.0, 50.0], "admin": [50.0, 60.0], "auto": [60.0]}.get(band, [])
    pools = {"prob": [p * 100, rf * 100] + thr, "rain": [rain], "level": [river, dam]}
    for t in turns:
        s = str(t.get("text") or "").lower().translate(CLEAN)
        if ETA.search(s):
            return False
        for rx in PROC:
            s = rx.sub(" ", s)
        for m in re.finditer(r"\b(\d{1,2}):(\d{2})\b", s):
            if (int(m.group(1)), int(m.group(2))) != (hh, mm):
                return False
        s = re.sub(r"\b\d{1,2}:\d{2}\b", " ", s)
        s = re.sub(rf"\b({_W})\b", lambda m: str(WORDS[m.group(1)]), s)
        for m in re.finditer(NUM + r"\s*(%|percent|mm\b|millimet\w*|m\b|metres?\b|meters?\b)?", s):
            v, unit = float(m.group(1)), m.group(2)
            dec = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
            before = s[max(0, m.start() - 28):m.start()]
            if unit in ("%", "percent"):
                pool = pools["prob"]
            elif unit and (unit.startswith("mm") or unit.startswith("millimet")):
                pool = pools["rain"]
            elif unit:
                pool = pools["level"]
            else:  # bind a unit-less number to the quantity named just before it
                last = max(((before.rfind(w), k) for k, ws in SLOT_WORDS.items() for w in ws), default=(-1, None))
                if last[0] < 0:
                    return False
                pool = pools[last[1]]
            if not _close(v, dec, pool):
                return False
    return True
