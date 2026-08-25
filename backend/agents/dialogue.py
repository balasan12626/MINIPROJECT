"""Threshold-based agent radio talk driven by Groq LLM."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from backend.agents.graph import graph
from backend.config import get_settings
from backend.utils.geo import jsonable, utcnow
from backend.websocket.hub import hub

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Prefer current Groq catalog IDs; legacy Llama IDs kept last for older keys.
GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

_state: dict[str, dict[str, Any]] = {
    "live": {"band": None, "history": [], "last_at": 0.0, "latest": None, "rescue_check": None},
    "simulation": {"band": None, "history": [], "last_at": 0.0, "latest": None, "rescue_check": None},
}

_NAME_MAP = {
    "rescue": "Rescue Agent",
    "rescue agent": "Rescue Agent",
    "ambulance": "Ambulance Agent",
    "ambulance agent": "Ambulance Agent",
    "disaster": "Disaster Team Agent",
    "disaster team": "Disaster Team Agent",
    "disaster team agent": "Disaster Team Agent",
    "ndrf": "Disaster Team Agent",
    "administrator": "Administrator Agent",
    "administrator agent": "Administrator Agent",
    "admin": "Administrator Agent",
    "flood risk": "Flood Risk Agent",
    "flood risk agent": "Flood Risk Agent",
    "weather": "Weather Agent",
    "weather agent": "Weather Agent",
    "monitor": "Card Monitor Agent",
    "card monitor agent": "Card Monitor Agent",
}


def risk_band(probability: float | None) -> str:
    if probability is None:
        return "unknown"
    p = float(probability)
    if p < 0.40:
        return "calm"
    if p < 0.50:
        return "watch"
    if p < 0.60:
        return "admin"
    return "auto"


def speakers_for(band: str) -> list[str]:
    if band == "auto":
        return ["Rescue Agent", "Ambulance Agent", "Disaster Team Agent"]
    if band == "admin":
        return ["Administrator Agent", "Flood Risk Agent"]
    if band == "watch":
        return ["Flood Risk Agent", "Administrator Agent"]
    if band == "spike":
        return ["Card Monitor Agent", "Flood Risk Agent"]
    return ["Weather Agent", "Flood Risk Agent"]


def reset_conversation(mode: str = "simulation") -> None:
    _state[mode] = {"band": None, "history": [], "last_at": 0.0, "latest": None, "rescue_check": None}


def last_conversation(mode: str = "live") -> dict[str, Any]:
    slot = _state.get(mode) or {}
    return slot.get("latest") or {
        "available": False,
        "mode": mode,
        "band": None,
        "turns": [],
        "history": [],
        "message": "No agent conversation yet",
    }


def _canon(name: str) -> str:
    return _NAME_MAP.get(str(name or "").strip().lower(), str(name or "").strip())


def _scripted(band: str, pct: str, zone: str, places: str) -> list[dict[str, str]]:
    dest = places or zone
    if band == "auto":
        return [
            {"from": "Rescue Agent", "to": "Ambulance Agent", "text": f"Flood has occurred. Probability {pct}, above 60 percent. Deploy now to {dest}."},
            {"from": "Ambulance Agent", "to": "Rescue Agent", "text": f"Ambulance moving with you to {dest}. Medical ready for water-related injuries."},
            {"from": "Disaster Team Agent", "to": "Rescue Agent", "text": "NDRF / disaster cell copied. We are opening the flood ground and pulling people out."},
            {"from": "Rescue Agent", "to": "Disaster Team Agent", "text": "Good. Sweep streets, then confirm with command if residents are rescued."},
        ]
    if band == "admin":
        if "hold auto-dispatch" in (places or "").lower() or "vs xgboost" in (places or "").lower() or "vs XGBoost" in (places or ""):
            return [
                {"from": "Administrator Agent", "to": "Flood Risk Agent", "text": f"Stop. {places}. I cannot auto-dispatch until both models agree, or an operator overrides."},
                {"from": "Flood Risk Agent", "to": "Administrator Agent", "text": "Copy. Publishing both scores. Rescue stays staged, not rolling."},
                {"from": "Administrator Agent", "to": "Rescue Agent", "text": "Rescue, hold at the cluster edge. Do not enter until I clear disagreement."},
            ]
        return [
            {"from": "Administrator Agent", "to": "Flood Risk Agent", "text": f"Probability {pct} is 50 to 60 percent. I cannot auto-predict. Hold full rescue."},
            {"from": "Flood Risk Agent", "to": "Administrator Agent", "text": f"Grey zone at {zone}. We escalate the second it crosses 60 percent."},
        ]
    if band == "watch":
        return [
            {"from": "Flood Risk Agent", "to": "Administrator Agent", "text": f"{pct} — under 50. Watching {zone}, no rescue call yet."},
            {"from": "Administrator Agent", "to": "Flood Risk Agent", "text": "Keep me on the net. Call if it climbs."},
        ]
    return [
        {"from": "Weather Agent", "to": "Flood Risk Agent", "text": f"{pct} is below 40 percent. Do not worry for now around {zone}."},
        {"from": "Flood Risk Agent", "to": "Weather Agent", "text": "Copy. If it rises we will call rescue and ambulance."},
    ]


def _parse_turns(raw: str, allowed: set[str]) -> list[dict[str, str]] | None:
    text = (raw or "").strip()
    if "```" in text:
        chunk = text.split("```", 2)[1]
        text = re.sub(r"^json", "", chunk, flags=re.I).strip()
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict):
        return None
    turns = data.get("turns")
    if not isinstance(turns, list) or len(turns) < 2:
        return None
    allowed = set(allowed or [])
    clean = []
    for row in turns[:20]:
        if not isinstance(row, dict):
            continue
        src = _canon(row.get("from"))
        dst = _canon(row.get("to"))
        msg = str(row.get("text") or "").strip()
        if src not in allowed:
            if "agent" not in src.lower():
                allowed.add(src)
            else:
                src = next(iter(allowed))
        if dst not in allowed:
            dst = next((x for x in allowed if x != src), src)
        if not msg:
            continue
        clean.append({"from": src, "to": dst, "text": msg})
    return clean if len(clean) >= 2 else None


async def _llm_turns(band: str, ctx: dict[str, Any], allowed: list[str]) -> tuple[list[dict[str, str]] | None, str | None]:
    settings = get_settings()
    key = (settings.groq_api_key or "").strip()
    if not key:
        return None, "GROQ_API_KEY missing"
    names = ", ".join(allowed)
    recent = ctx.get("recent") or []
    recent_txt = "\n".join(f"{t.get('from')}: {t.get('text')}" for t in recent[-4:]) or "(none)"
    spike = ctx.get("spike")
    spike_txt = ""
    if spike and spike.get("sudden"):
        bits = [f"{a['label']} {a['from_value']}→{a['to_value']} in {a['seconds']}s ({a['direction']})" for a in spike.get("alerts") or []]
        spike_txt = "SUDDEN CARD CHANGE: " + "; ".join(bits)
    rules = {
        "calm": "Below 40%: reassure, do not worry, call if it rises.",
        "watch": "40-50%: watch only, no rescue.",
        "admin": "50-60%: administrator cannot auto-predict, no full rescue yet.",
        "auto": "Above 60%: flood occurred. Rescue tells ambulance AND disaster/NDRF team to go rescue people at the named places now. Sound like a real ops radio, not a template.",
        "confirm": "Operator will answer whether people were rescued. Ask clearly, then wait.",
        "rescued_yes": "Operator confirmed YES — people rescued. Stand teams down, report all clear.",
        "rescued_no": "Operator said NO — keep searching, ambulance stay on scene.",
        "spike": "A KPI card jumped suddenly. Report which metric, old vs new, and how many seconds the change took.",
    }
    prompt = (
        f"Speakers (use these exact names): {names}\n"
        f"Situation: {rules.get(band, '')}\n"
        f"Flood probability {ctx.get('pct')}. Rain {ctx.get('rain')} mm. River {ctx.get('river')} m. "
        f"Zone {ctx.get('zone')}. Places {ctx.get('places')}. Mode {ctx.get('mode')}.\n"
        f"{spike_txt}\n"
        f"Recent radio:\n{recent_txt}\n"
        "Write a NEW spoken conversation (do not copy the recent lines). 4-6 short turns, 1-2 sentences, like humans on radio.\n"
        'JSON only: {"turns":[{"from":"...","to":"...","text":"..."}]}'
    )
    models = [settings.groq_model] + [m for m in GROQ_MODELS if m != settings.groq_model]
    last_err = None
    for model in models:
        if not model:
            continue
        body = {
            "model": model,
            "temperature": 0.85,
            "max_tokens": 700,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You write realistic multi-agent emergency radio dialogue. JSON only."},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=body)
                if resp.status_code >= 400:
                    last_err = f"{model} HTTP {resp.status_code}"
                    continue
                content = (((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
            turns = _parse_turns(content, set(allowed))
            if turns:
                return turns, None
            last_err = f"{model} unusable JSON"
        except Exception as exc:  # noqa: BLE001
            last_err = f"{model}: {exc}"
            continue
    return None, last_err or "LLM unavailable"


def _pack(mode: str, band: str, probability, turns, source, err, dispatch, extra=None) -> dict[str, Any]:
    slot = _state.setdefault(mode, {"band": None, "history": [], "last_at": 0.0, "latest": None, "rescue_check": None})
    history = list(slot.get("history") or [])
    history.extend(turns)
    history = history[-60:]
    speakers = speakers_for(band if band not in {"confirm", "rescued_yes", "rescued_no", "spike"} else ("auto" if "rescue" in band or band.startswith("rescu") else band))
    if band in {"confirm", "rescued_yes", "rescued_no"}:
        speakers = speakers_for("auto")
    if band == "spike":
        speakers = speakers_for("spike")
    entry = {
        "available": True,
        "mode": mode,
        "band": slot.get("band") or band,
        "flood_probability": probability,
        "speakers": speakers,
        "turns": turns,
        "source": source,
        "llm_error": err,
        "dispatch": dispatch or {},
        "timestamp": utcnow(),
        "rescue_check": slot.get("rescue_check"),
        "spike": (extra or {}).get("spike"),
        "policy_hint": {
            "calm": "P < 40% — stand down, call if it rises",
            "watch": "40–50% — watch, no rescue call",
            "admin": "50–60% — administrator, cannot auto-predict",
            "auto": "P ≥ 60% — auto call rescue + ambulance + disaster team",
        }.get(slot.get("band") or band),
        "history": history,
    }
    slot["history"] = history
    slot["last_at"] = time.monotonic()
    slot["latest"] = jsonable(entry)
    return slot["latest"]


async def _emit_turns(turns: list[dict[str, str]], band: str) -> None:
    keys = {
        "Rescue Agent": "rescue",
        "Ambulance Agent": "ambulance",
        "Disaster Team Agent": "disaster",
        "Administrator Agent": "administrator",
        "Flood Risk Agent": "flood_risk",
        "Weather Agent": "weather",
        "Card Monitor Agent": "monitor",
    }
    for turn in turns[:2]:
        await graph.emit(keys.get(turn["from"], "flood_risk"), "AGENT_TALK", turn["text"], "talk on operations net", {"band": band, "peer": turn.get("to")})


async def converse(
    mode: str,
    probability: float | None,
    weather: dict[str, Any],
    river: dict[str, Any],
    incident: dict[str, Any],
    dispatch: dict[str, Any] | None = None,
    force: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    band = risk_band(probability)
    slot = _state.setdefault(mode, {"band": None, "history": [], "last_at": 0.0, "latest": None, "rescue_check": None})
    now = time.monotonic()
    spike = (extra or {}).get("spike") or {}
    if spike.get("sudden"):
        force = True
    if not force and slot.get("band") == band and slot.get("latest") and (now - float(slot.get("last_at") or 0)) < 14:
        latest = slot["latest"]
        if latest:
            latest["rescue_check"] = slot.get("rescue_check")
        return latest

    pct = "unknown" if probability is None else f"{probability * 100:.1f}%"
    zone = incident.get("zone_name") or "Yamuna Pushta / Geeta Colony"
    places = ", ".join((p.get("name") for p in (dispatch or {}).get("places") or [])) or zone
    dual = (extra or {}).get("dual") or {}
    talk_band = "spike" if spike.get("sudden") else band
    if dual.get("disagree") and not (dispatch or {}).get("called"):
        talk_band = "admin"
        band = "admin"
        rf_pct = None if dual.get("random_forest") is None else round(float(dual["random_forest"]) * 100, 1)
        xgb_pct = None if dual.get("xgboost") is None else round(float(dual["xgboost"]) * 100, 1)
        places = f"RF {rf_pct}% vs XGBoost {xgb_pct}% — hold auto-dispatch"
    allowed = speakers_for(talk_band)
    ctx = {
        "mode": mode,
        "pct": pct,
        "rain": weather.get("rainfall_mm"),
        "river": river.get("value_m"),
        "zone": zone,
        "places": places,
        "recent": slot.get("history") or [],
        "spike": spike,
    }
    turns, err = await _llm_turns(talk_band, ctx, allowed)
    source = "groq"
    if not turns:
        turns = _scripted(band, pct, zone, places)
        if spike.get("sudden"):
            alert = (spike.get("alerts") or [{}])[0]
            turns = [
                {
                    "from": "Card Monitor Agent",
                    "to": "Flood Risk Agent",
                    "text": f"Isolation monitor: {alert.get('label', 'a card')} jumped {alert.get('from_value')} to {alert.get('to_value')} in {alert.get('seconds')} seconds ({alert.get('direction')}).",
                },
                {"from": "Flood Risk Agent", "to": "Card Monitor Agent", "text": "Copied. Recalculating policy from the new card values now."},
            ] + turns[:2]
        source = "scripted_fallback"
    if band == "auto" and (slot.get("band") != "auto" or force):
        slot["rescue_check"] = {
            "status": "pending",
            "ask_after_sec": 8,
            "dispatched_at": utcnow().isoformat(),
            "answered": None,
        }
    if band != "auto":
        slot["rescue_check"] = None
    slot["band"] = band
    packed = _pack(mode, talk_band, probability, turns, source, err, dispatch, extra)
    await _emit_turns(turns, band)
    await hub.broadcast("agent_talk", packed)
    return packed


async def confirm_rescue(mode: str, rescued: bool, context: dict[str, Any] | None = None) -> dict[str, Any]:
    slot = _state.setdefault(mode, {"band": None, "history": [], "last_at": 0.0, "latest": None, "rescue_check": None})
    band = "rescued_yes" if rescued else "rescued_no"
    ctx = {
        "mode": mode,
        "pct": context.get("pct") if context else "",
        "rain": None,
        "river": None,
        "zone": (context or {}).get("zone") or "Yamuna floodplain",
        "places": (context or {}).get("places") or "",
        "recent": slot.get("history") or [],
    }
    turns, err = await _llm_turns(band, ctx, speakers_for("auto"))
    if not turns:
        if rescued:
            turns = [
                {"from": "Rescue Agent", "to": "Disaster Team Agent", "text": "Operator confirmed YES. People are rescued. Mark the ground clear."},
                {"from": "Ambulance Agent", "to": "Rescue Agent", "text": "Medical copy. Casualties transferred. We can stand down."},
                {"from": "Disaster Team Agent", "to": "Rescue Agent", "text": "Disaster cell closing the sweep. All accounted."},
            ]
        else:
            turns = [
                {"from": "Rescue Agent", "to": "Ambulance Agent", "text": "Operator said NO — not rescued yet. Keep searching the waterlogged streets."},
                {"from": "Ambulance Agent", "to": "Rescue Agent", "text": "Staying on scene. Send another boat if you have one."},
                {"from": "Disaster Team Agent", "to": "Rescue Agent", "text": "NDRF continuing the sweep until we get a yes."},
            ]
        err = err or "scripted confirm"
        source = "scripted_fallback"
    else:
        source = "groq"
    slot["rescue_check"] = {"status": "answered", "answered": "yes" if rescued else "no", "ask_after_sec": 8}
    packed = _pack(mode, band, (context or {}).get("p"), turns, source, err, (slot.get("latest") or {}).get("dispatch"))
    await _emit_turns(turns, band)
    if rescued:
        await graph.emit("rescue", "RESCUE_RESPONSE", "Operator confirmed people rescued", "stand down", {"rescued": True})
        await graph.emit("ambulance", "RESCUE_RESPONSE", "Medical stand-down after yes", "return to base", {"rescued": True})
        await graph.emit("disaster", "RESCUE_RESPONSE", "Disaster team sweep complete", "close incident ground", {"rescued": True})
    else:
        await graph.emit("rescue", "RESCUE_RESPONSE", "Operator said not rescued — continue", "keep searching", {"rescued": False})
    await hub.broadcast("agent_talk", packed)
    return packed


async def talk_with_citizen(mode: str, citizen: dict[str, Any], weather: dict[str, Any] | None = None) -> dict[str, Any]:
    slot = _state.setdefault(mode, {"band": None, "history": [], "last_at": 0.0, "latest": None, "rescue_check": None})
    name = str(citizen.get("citizen_name") or "Citizen").strip() or "Citizen"
    lat = citizen.get("lat")
    lon = citizen.get("lon")
    water = citizen.get("water_level_note") or "not described"
    people = int(citizen.get("people") or 1)
    rain = (weather or {}).get("rainfall_mm")
    loc = f"{float(lat):.5f}, {float(lon):.5f}" if lat is not None and lon is not None else "unknown GPS"
    allowed = ["Rescue Agent", "Ambulance Agent", name]
    turns, err = await _llm_citizen(name, loc, people, water, rain, allowed, slot.get("history") or [])
    source = "groq"
    if not turns:
        turns = [
            {"from": "Rescue Agent", "to": name, "text": f"{name}, this is Rescue. We have your live location {loc}. How high is the rainwater around you — ankle, knee, or waist?"},
            {"from": name, "to": "Rescue Agent", "text": f"Please help — water is {water}. There are {people} of us here."},
            {"from": "Ambulance Agent", "to": name, "text": f"{name}, ambulance is moving to your GPS pin. Stay together and avoid flowing water."},
            {"from": "Rescue Agent", "to": "Ambulance Agent", "text": f"Copy. Disaster cell notified for {name} at {loc}."},
        ]
        source = "scripted_fallback"
    packed = _pack(mode, slot.get("band") or "auto", None, turns, source, err, {"called": True, "citizen": citizen})
    packed["policy_hint"] = f"SOS — talking with {name}"
    packed["speakers"] = allowed
    slot["latest"] = packed
    await graph.emit("rescue", "SOS", f"Talking with citizen {name} at {loc}", "citizen SOS response", jsonable(citizen))
    await hub.broadcast("agent_talk", packed)
    return packed


async def _llm_citizen(name, loc, people, water, rain, allowed, recent):
    settings = get_settings()
    key = (settings.groq_api_key or "").strip()
    if not key:
        return None, "GROQ_API_KEY missing"
    recent_txt = "\n".join(f"{t.get('from')}: {t.get('text')}" for t in (recent or [])[-3:]) or "(none)"
    prompt = (
        f"Speakers (exact names): Rescue Agent, Ambulance Agent, {name}.\n"
        f"{name} pressed SOS. Live GPS {loc}. {people} people. Water report: {water}. Command rainfall {rain} mm.\n"
        f"Rescue must use the name {name}, ask rainwater depth, confirm the live location, and send ambulance.\n"
        f"Recent radio:\n{recent_txt}\n"
        'JSON only: {"turns":[{"from":"...","to":"...","text":"..."}]}'
    )
    body = {
        "model": settings.groq_model or GROQ_MODELS[0],
        "temperature": 0.8,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Emergency radio between rescue teams and a named citizen. JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=body)
            resp.raise_for_status()
            content = (((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        return _parse_turns(content, set(allowed)), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


async def talk_with_queue(
    mode: str,
    citizens: list[dict[str, Any]],
    clusters: dict[str, Any] | None = None,
    weather: dict[str, Any] | None = None,
    dual: dict[str, Any] | None = None,
    bilingual: bool = False,
) -> dict[str, Any]:
    slot = _state.setdefault(mode, {"band": None, "history": [], "last_at": 0.0, "latest": None, "rescue_check": None})
    from backend.services.priority import rank_citizens

    ordered = (clusters or {}).get("priority_global") or rank_citizens(citizens)
    roster = list(ordered)
    names = [str(c.get("citizen_name") or "Citizen") for c in roster]
    order_lines = []
    for i, c in enumerate(roster, start=1):
        order_lines.append(
            f"Person {i}: {c.get('citizen_name')} age {c.get('age', '?')} "
            f"({c.get('vulnerability') or 'standard'}) water={c.get('water_level_note')} "
            f"team={c.get('assigned_team_name') or c.get('assigned_team') or 'unassigned'} "
            f"GPS {c.get('lat')},{c.get('lon')}"
        )
    cluster_txt = ""
    for cl in (clusters or {}).get("clusters") or []:
        q = ", ".join(f"{p.get('citizen_name')}({p.get('vulnerability')})" for p in (cl.get("priority_queue") or []))
        cluster_txt += f" {cl.get('cluster_id')} → {cl.get('assigned_team_name') or cl.get('assigned_team')} first: {q};"
    allowed = ["Administrator Agent", "Flood Risk Agent", "Rescue Agent", "Ambulance Agent", "Disaster Team Agent"] + names
    rain = (weather or {}).get("rainfall_mm")
    hold = bool((dual or {}).get("disagree"))
    turns, err = await _llm_queue(names, order_lines, cluster_txt, rain, allowed, hold, dual)
    source = "groq"
    if not turns:
        turns = _scripted_queue(roster, cluster_txt, hold, dual, bilingual=bilingual)
        source = "scripted_fallback"
    packed = _pack(mode, "admin" if hold else "auto", None, turns[:28], source, err, {"called": not hold, "queue": names, "held": hold})
    packed["policy_hint"] = (
        "RF vs XGBoost disagree — Administrator holds auto-dispatch"
        if hold
        else f"Vulnerable-first queue ({len(roster)}) — status check each person"
    )
    packed["speakers"] = allowed
    if not hold:
        slot["rescue_check"] = {
            "status": "pending",
            "ask_after_sec": 8,
            "dispatched_at": utcnow().isoformat(),
            "answered": None,
        }
    packed["rescue_check"] = slot["rescue_check"]
    slot["latest"] = packed
    await graph.emit("rescue", "SOS", f"Multi-citizen SOS queue {len(roster)}", "vulnerable-first status net", {"names": names})
    await hub.broadcast("agent_talk", packed)
    return packed


def _scripted_queue(roster, cluster_txt, hold, dual, bilingual=False):
    turns = []
    if hold:
        rf = dual.get("random_forest") if dual else None
        xgb = dual.get("xgboost") if dual else None
        turns.append({
            "from": "Administrator Agent",
            "to": "Flood Risk Agent",
            "text": f"Hold auto-dispatch. Random Forest {None if rf is None else round(rf*100,1)}% vs XGBoost {None if xgb is None else round(xgb*100,1)}%. They do not agree.",
        })
        turns.append({
            "from": "Flood Risk Agent",
            "to": "Administrator Agent",
            "text": "Copy. We still check every citizen status, but teams stay staged until override.",
        })
    first = roster[0] if roster else {}
    second = roster[1] if len(roster) > 1 else {}
    if first:
        turns.append({
            "from": "Rescue Agent",
            "to": "Ambulance Agent",
            "text": (
                f"Vulnerable-first: {first.get('citizen_name')}, age {first.get('age')}, first. "
                f"{second.get('citizen_name')}, {second.get('age')}, second. K-means:{cluster_txt or ' nearest team'}."
            ),
        })
    for i, c in enumerate(roster, start=1):
        nm = c.get("citizen_name")
        turns.append({
            "from": "Rescue Agent",
            "to": nm,
            "text": (
                f"Person {i}, {nm}, age {c.get('age')}. This is Rescue. What is your status right now — "
                f"trapped, moving to roof, or injured? Water last reported {c.get('water_level_note')}."
            ),
        })
        vuln = c.get("vulnerability") or "standard"
        if bilingual:
            if vuln == "child":
                reply = f"This is {nm}. Main child hoon. Paani {c.get('water_level_note')} hai. Hum {c.get('people')} log phanse hain. Pehle aao."
            elif vuln == "elderly":
                reply = f"This is {nm}. Meri umar {c.get('age')} hai. Paani {c.get('water_level_note')}. Status: boat ka wait."
            elif vuln == "chest-deep":
                reply = f"This is {nm}. Paani seene tak. Status: furniture pe khade hain, nikal nahi sakte."
            else:
                reply = f"This is {nm}. Status: wait. Paani {c.get('water_level_note')}. {c.get('people')} log yahan hain."
        elif vuln == "child":
            reply = f"This is {nm}. I am a child, we are {c.get('water_level_note')}, {c.get('people')} of us. We are trapped. Please come first."
        elif vuln == "elderly":
            reply = f"This is {nm}. I am {c.get('age')}. Water is {c.get('water_level_note')}. I cannot move fast. Status: waiting for boat."
        elif vuln == "chest-deep":
            reply = f"This is {nm}. Chest-deep water. Status: standing on furniture, cannot leave."
        else:
            reply = f"This is {nm}. Status: waiting. Water {c.get('water_level_note')}. {c.get('people')} people here."
        turns.append({"from": nm, "to": "Rescue Agent", "text": reply})
        turns.append({
            "from": "Ambulance Agent",
            "to": nm,
            "text": f"{nm}, ambulance copied person {i}. Team {c.get('assigned_team_name') or c.get('assigned_team') or 'nearest'} is assigned.",
        })
    turns.append({"from": "Disaster Team Agent", "to": "Rescue Agent", "text": "NDRF copying every named person in vulnerable-first order. Sweep cluster by cluster."})
    return turns


async def _llm_queue(names, lines, cluster_txt, rain, allowed, hold=False, dual=None):
    settings = get_settings()
    key = (settings.groq_api_key or "").strip()
    if not key:
        return None, "GROQ_API_KEY missing"
    dual_txt = ""
    if dual and dual.get("available"):
        dual_txt = f"RF={dual.get('random_forest')} XGB={dual.get('xgboost')} disagree={dual.get('disagree')}."
    hold_txt = "Administrator MUST speak first and forbid auto-dispatch." if hold else "Rescue may treat this as an active rescue net."
    prompt = (
        f"Speakers (exact names): Administrator Agent, Flood Risk Agent, Rescue Agent, Ambulance Agent, Disaster Team Agent, citizens: {', '.join(names)}.\n"
        f"Command rainfall {rain} mm. {dual_txt} {hold_txt}\n"
        f"K-means + vulnerable-first:{cluster_txt}\n"
        f"Call EACH person by Person N + full name. Ask STATUS (trapped / moving / injured). They must answer.\n"
        f"Announce first two vulnerable names like: '{names[0] if names else 'Name'}, age …, first.'\n"
        + "\n".join(lines) + "\n"
        'JSON only: {"turns":[{"from":"...","to":"...","text":"..."}]}'
    )
    body = {
        "model": settings.groq_model or GROQ_MODELS[0],
        "temperature": 0.6,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Emergency radio. Vulnerable-first. Ask each person their live status. JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=22.0) as client:
            resp = await client.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=body)
            resp.raise_for_status()
            content = (((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        return _parse_turns(content, set(allowed)), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)

