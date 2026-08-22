"""Tamil Gemini voice SOS — ask ONLY the name, then auto-assign team + shelter."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from backend.config import get_settings
from backend.services.seed import SHELTERS
from backend.utils.geo import haversine_km, jsonable

SYSTEM = """நீங்கள் டெல்லி யமுனா வெள்ள மீட்பு குரல் முகவர் (Flood Response Voice Agent).
எப்போதும் தமிழில் மட்டும் பேசுங்கள். சுருக்கமாக (1–2 வாக்கியங்கள்).

உங்கள் ஒரே கேள்வி: அழைப்பாளரின் முழுப் பெயர் மட்டும்.
பெயர் கிடைத்தவுடன் உடனே submit_flood_sos கருவியை அழைக்கவும்.
latitude, longitude, people, water depth ஆகியவை சாதன GPS / அமைப்பு இயல்புநிலையில் இருந்து வரும் — அவற்றை கேட்க வேண்டாம்.

கருவி பதிலுக்குப் பிறகு: ஆம்புலன்ஸ்/மீட்பு குழு + தங்குமிடம் பெயரை தமிழில் தெளிவாகச் சொல்லுங்கள்.
ஆங்கிலத்தில் கேள்விகள் கேட்க வேண்டாம். பெயர் மட்டும் கேளுங்கள்.
"""

TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "submit_flood_sos",
                "description": "பெயர் கிடைத்தவுடன் SOS பதிவு செய்து மீட்பு குழு + தங்குமிடம் ஒதுக்கவும்.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "citizen_name": {"type": "string", "description": "அழைப்பாளரின் முழுப் பெயர்"},
                    },
                    "required": ["citizen_name"],
                },
            }
        ]
    }
]

DEFAULT_CTX = {
    "lat": 28.651,
    "lon": 77.262,
    "people": 2,
    "water_level_note": "knee-deep",
    "age": None,
}


def _nearest_shelter(lat: float, lon: float) -> dict[str, Any]:
    best = min(
        SHELTERS,
        key=lambda s: haversine_km(lat, lon, float(s["lat"]), float(s["lon"])),
    )
    free = int(best.get("capacity") or 0) - int(best.get("occupancy") or 0)
    return {
        "shelter_id": best.get("shelter_id"),
        "shelter_name": best.get("name"),
        "lat": best.get("lat"),
        "lon": best.get("lon"),
        "free_seats": free,
        "distance_km": round(haversine_km(lat, lon, float(best["lat"]), float(best["lon"])), 2),
    }


def voice_status() -> dict[str, Any]:
    s = get_settings()
    key = (s.gemini_api_key or "").strip()
    return {
        "available": bool(key),
        "model": s.gemini_model or "gemini-3.6-flash",
        "live_model": s.gemini_live_model or "gemini-3.1-flash-live-preview",
        "language": "ta-IN",
        "mode": "name_only_tamil",
        "message": "தமிழ் குரல் முகவர் தயார்" if key else "Set GEMINI_API_KEY in .env",
    }


def _extract_text(data: dict) -> str:
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = (((cands[0] or {}).get("content") or {}).get("parts")) or []
    return " ".join(str(p.get("text") or "") for p in parts if isinstance(p, dict) and p.get("text")).strip()


def _extract_function_calls(data: dict) -> list[dict[str, Any]]:
    cands = data.get("candidates") or []
    if not cands:
        return []
    parts = (((cands[0] or {}).get("content") or {}).get("parts")) or []
    out = []
    for p in parts:
        fc = p.get("functionCall") if isinstance(p, dict) else None
        if not fc:
            continue
        args = fc.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:  # noqa: BLE001
                args = {}
        out.append({"name": fc.get("name"), "args": args})
    return out


def _sanitize_part(part: Any) -> dict[str, Any] | None:
    if not isinstance(part, dict):
        return None
    if part.get("text") is not None:
        return {"text": str(part.get("text") or "")}
    if part.get("functionCall"):
        fc = part["functionCall"] or {}
        args = fc.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:  # noqa: BLE001
                args = {}
        return {"functionCall": {"name": fc.get("name"), "args": args}}
    if part.get("functionResponse"):
        fr = part["functionResponse"] or {}
        resp = fr.get("response")
        if not isinstance(resp, dict):
            resp = {"result": resp}
        return {"functionResponse": {"name": fr.get("name"), "response": resp}}
    return None


def _sanitize_contents(contents: list[dict[str, Any]] | None, *, drop_leading_model: bool = True) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for turn in contents or []:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        if role not in ("user", "model"):
            role = "model" if clean and clean[-1].get("role") == "user" else "user"
        parts = []
        for p in turn.get("parts") or []:
            sp = _sanitize_part(p)
            if sp:
                parts.append(sp)
        if not parts:
            continue
        clean.append({"role": role, "parts": parts})
    if drop_leading_model:
        while clean and clean[0].get("role") == "model":
            clean.pop(0)
    return clean


def _model_turn_from_response(data: dict[str, Any]) -> dict[str, Any] | None:
    raw = ((data.get("candidates") or [{}])[0].get("content")) or {}
    parts = []
    for p in raw.get("parts") or []:
        sp = _sanitize_part(p)
        if sp:
            parts.append(sp)
    if not parts:
        txt = _extract_text(data)
        if txt:
            parts = [{"text": txt}]
    if not parts:
        return None
    return {"role": "model", "parts": parts}


def _merge_ctx(ctx: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_CTX)
    if not ctx:
        return out
    for k in ("lat", "lon", "people", "water_level_note", "age"):
        if ctx.get(k) is not None and ctx.get(k) != "":
            out[k] = ctx[k]
    try:
        out["lat"] = float(out["lat"])
        out["lon"] = float(out["lon"])
        out["people"] = int(out["people"] or 2)
    except Exception:  # noqa: BLE001
        out.update({"lat": 28.651, "lon": 77.262, "people": 2})
    return out


def _guess_name(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    # English patterns
    m = re.search(r"(?:name is|i am|i'm|my name)\s+([A-Za-z][A-Za-z.\s]{1,40})", t, re.I)
    if m:
        return m.group(1).strip(" .,")
    # Tamil: "என் பெயர் X" / "பெயர் X"
    m = re.search(r"(?:என்\s*)?பெயர்\s*([^\n,.]{2,40})", t)
    if m:
        return m.group(1).strip(" .,")
    # If short utterance without question words, treat whole as name
    bad = ("எத்தனை", "latitude", "longitude", "water", "people", "how many", "where")
    if len(t) <= 40 and not any(b in t.lower() for b in bad):
        return t
    return None


async def _gemini_generate(contents: list[dict], *, with_tools: bool = True) -> dict[str, Any]:
    s = get_settings()
    key = (s.gemini_api_key or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing")
    models = [(s.gemini_model or "gemini-3.6-flash").strip()]
    for alt in ("gemini-3.5-flash-lite", "gemini-flash-latest"):
        if alt not in models:
            models.append(alt)
    body_base: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": _sanitize_contents(contents, drop_leading_model=True),
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 512},
    }
    if with_tools:
        body_base["tools"] = TOOLS
    last_err = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json", "X-goog-api-key": key},
                json=body_base,
            )
            if resp.status_code < 400:
                return resp.json()
            last_err = resp.text[:500] or f"Gemini HTTP {resp.status_code}"
            if resp.status_code not in (404, 429):
                break
    raise RuntimeError(last_err or "Gemini unavailable")


def _local_tamil_confirm(assignment: dict[str, Any]) -> str:
    return (
        f"{assignment.get('citizen_name')} அவர்களுக்கான SOS பதிவு ஆனது. "
        f"மீட்பு குழு: {assignment.get('ambulance_or_team')}. "
        f"தங்குமிடம்: {assignment.get('shelter_name')} "
        f"({assignment.get('shelter_distance_km')} கி.மீ)."
    )


async def _execute_sos(name: str, ctx: dict[str, Any]) -> dict[str, Any]:
    from backend.simulation.engine import engine

    citizen_name = (name or "Citizen").strip() or "Citizen"
    lat = float(ctx["lat"])
    lon = float(ctx["lon"])
    people = int(ctx.get("people") or 2)
    water = str(ctx.get("water_level_note") or "knee-deep")
    age = ctx.get("age")

    st = await engine.add_citizen_sos(
        {
            "citizen_name": citizen_name,
            "people": people,
            "lat": lat,
            "lon": lon,
            "water_level_note": water,
            "age": age,
            "mode": "simulation",
        }
    )
    shelter = _nearest_shelter(lat, lon)
    cit = next(
        (c for c in (st.get("citizens") or []) if str(c.get("citizen_name") or "").lower() == citizen_name.lower()),
        None,
    )
    log = next(
        (r for r in (st.get("contact_log") or []) if str(r.get("citizen_name") or "").lower() == citizen_name.lower()),
        None,
    )
    team = (cit or {}).get("assigned_team_name") or (cit or {}).get("assigned_team") or (log or {}).get("assigned_team")
    assignment = {
        "citizen_name": citizen_name,
        "people": people,
        "lat": lat,
        "lon": lon,
        "water_level_note": water,
        "ambulance_or_team": team or "மீட்பு குழு நிலுவையில்",
        "shelter_id": shelter["shelter_id"],
        "shelter_name": shelter["shelter_name"],
        "shelter_distance_km": shelter["distance_km"],
        "free_seats": shelter["free_seats"],
        "cluster_id": (cit or {}).get("cluster_id") or (log or {}).get("cluster_id"),
        "ops_status": (cit or {}).get("ops_status") or (log or {}).get("status") or "queued",
        "message": (
            f"{citizen_name} அவர்களுக்கான SOS பதிவு செய்யப்பட்டது. "
            f"குழு: {team or 'நிலுவை'}. தங்குமிடம்: {shelter['shelter_name']} "
            f"({shelter['distance_km']} கி.மீ)."
        ),
    }
    return {"ok": True, "assignment": assignment, "sim": jsonable(st)}


async def handle_turn(
    history: list[dict[str, Any]],
    user_text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ctx = _merge_ctx(context)
    contents = _sanitize_contents(history, drop_leading_model=True)
    ctx_note = (
        f"[அமைப்பு: GPS lat={ctx['lat']}, lon={ctx['lon']}, people={ctx['people']}, "
        f"water={ctx['water_level_note']}. பெயர் மட்டும் கேட்டு submit_flood_sos அழைக்கவும்.]"
    )
    contents.append({"role": "user", "parts": [{"text": f"{ctx_note}\n\nஅழைப்பாளர்: {user_text}"}]})

    assignment = None
    sim = None
    reply = ""
    name = _guess_name(user_text)
    gemini_ok = True

    try:
        data = await _gemini_generate(contents, with_tools=True)
        fcs = _extract_function_calls(data)
        model_turn = _model_turn_from_response(data)
        if model_turn:
            contents.append(model_turn)
        reply = _extract_text(data)
        if fcs:
            for fc in fcs:
                if fc.get("name") == "submit_flood_sos":
                    name = str((fc.get("args") or {}).get("citizen_name") or "").strip() or name
                    break
    except Exception as exc:  # noqa: BLE001
        gemini_ok = False
        if not name:
            return jsonable(
                {
                    "reply": "வணக்கம். உங்கள் முழுப் பெயரை மட்டும் சொல்லுங்கள்.",
                    "history": _sanitize_contents(contents, drop_leading_model=False),
                    "draft": {k: ctx[k] for k in ("lat", "lon", "people", "water_level_note")},
                    "assignment": None,
                    "sim": None,
                    "done": False,
                    "language": "ta-IN",
                    "fallback": True,
                    "warning": str(exc)[:200],
                }
            )

    if name:
        result = await _execute_sos(name, ctx)
        assignment = result.get("assignment")
        sim = result.get("sim")
        if gemini_ok:
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": "submit_flood_sos",
                                "response": assignment or {"ok": False},
                            }
                        }
                    ],
                }
            )
            try:
                data2 = await _gemini_generate(contents, with_tools=False)
                reply2 = _extract_text(data2)
                if reply2:
                    reply = reply2
                    contents.append({"role": "model", "parts": [{"text": reply2}]})
                else:
                    reply = _local_tamil_confirm(assignment)
            except Exception:  # noqa: BLE001
                reply = _local_tamil_confirm(assignment)
        else:
            reply = _local_tamil_confirm(assignment)

    if not reply:
        reply = (
            _local_tamil_confirm(assignment)
            if assignment
            else "வணக்கம். உங்கள் முழுப் பெயரை மட்டும் சொல்லுங்கள்."
        )

    draft = {"citizen_name": name} if name else {}
    draft.update({k: ctx[k] for k in ("lat", "lon", "people", "water_level_note")})

    return jsonable(
        {
            "reply": reply,
            "history": _sanitize_contents(contents, drop_leading_model=False),
            "draft": draft,
            "assignment": assignment,
            "sim": sim,
            "done": bool(assignment),
            "language": "ta-IN",
            "fallback": not gemini_ok,
        }
    )


async def opening_line(context: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = _merge_ctx(context)
    return {
        "reply": "வணக்கம். வெள்ள மீட்பு குரல் முகவர் இங்கே. உங்கள் முழுப் பெயரை மட்டும் சொல்லுங்கள்.",
        "history": [],
        "draft": {k: ctx[k] for k in ("lat", "lon", "people", "water_level_note")},
        "assignment": None,
        "done": False,
        "language": "ta-IN",
    }
