"""F24 — parse the compact SOS text the phone page builds for an SMS.

    SOS <lat>,<lon> P<people> W<ANKLE|KNEE|WAIST|CHEST|RISING> [M<INJURED|CRITICAL>] <name>

Built by frontend/src/i18n/phonePages.js `smsText` — keep both in step. There is
no SMS gateway: the control room pastes a received text into
POST /api/public/sos/sms-text (operator only) and it joins the run like any SOS.
"""

from __future__ import annotations

import re
from typing import Any

WATER = {"ANKLE": "ankle-deep", "KNEE": "knee-deep", "WAIST": "waist-deep", "CHEST": "chest-deep", "RISING": "water rising fast"}
MEDICAL = {"INJURED": "injured", "CRITICAL": "critical"}
PATTERN = re.compile(
    r"^\s*SOS\s+(?P<lat>-?\d{1,2}(?:\.\d+)?)\s*,\s*(?P<lon>-?\d{1,3}(?:\.\d+)?)\s+P(?P<people>\d{1,2})\s+"
    r"W(?P<water>[A-Z]+)(?:\s+M(?P<medical>[A-Z]+))?\s*(?P<name>.*)$",
    re.IGNORECASE,
)


class SmsParseError(ValueError):
    pass


def parse(text: str) -> dict[str, Any]:
    m = PATTERN.match(text or "")
    if not m:
        raise SmsParseError("not an SOS text (expected: SOS <lat>,<lon> P<people> W<water> [M<medical>] <name>)")
    water = m.group("water").upper()
    if water not in WATER:
        raise SmsParseError(f"unknown water level {water}")
    med = (m.group("medical") or "").upper()
    if med and med not in MEDICAL:
        raise SmsParseError(f"unknown medical code {med}")
    people = int(m.group("people"))
    if not 1 <= people <= 50:
        raise SmsParseError("people must be 1 to 50")
    lat, lon = float(m.group("lat")), float(m.group("lon"))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise SmsParseError("bad coordinates")
    name = " ".join(m.group("name").split())[:60] or "SMS caller"
    return {"citizen_name": name, "lat": lat, "lon": lon, "people": people, "water_level_note": WATER[water],
            "medical": MEDICAL.get(med, "none")}
