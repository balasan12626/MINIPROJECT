"""AI assistant for the /simulation AI tab — grounded question answering.

Questions about people, places, dams, shelters, ambulances and the flood are
answered ONLY from the live simulation state (and the dam registry):

1. Retrieval: find the people / dams / shelters / zones / units the question
   names (a pronoun follows the last person named in the conversation) and
   the topics it asks about (ambulances left, shelter seats, risk, ...).
2. Facts: each hit becomes plain sentences built from state values, plus a
   structured card the UI renders (person report, dam, fleet, shelters).
3. Answer: Groq phrases a reply from those facts only. The reply is rejected
   if it contains any number that is not in the facts (agents.dialogue.
   grounded), and then the facts themselves are the answer ("rules").

Nothing is invented: an unknown person or place is reported as not found.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend.utils.geo import haversine_km

IST = timezone(timedelta(hours=5, minutes=30))
STAGE_TEXT = {
    "queued": "waiting in the SOS queue",
    "assigned": "unit allocated, request sent to the driver",
    "en_route": "unit driving to them",
    "to_shelter": "picked up, on the way to the shelter",
    "rescued": "safe at the shelter",
}
PRONOUN = re.compile(r"\b(he|she|him|her|his|hers|they|them|their|this person|that person)\b")


def _ist(v: Any) -> str | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%H:%M:%S IST")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def _has(q: str, *words: str) -> bool:
    return any(re.search(rf"\b{w}", q) for w in words)


# ---------------------------------------------------------------- retrieval
def _find_people(q: str, citizens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    qn = f" {_norm(q)} "
    full = [c for c in citizens if f" {_norm(c.get('citizen_name') or '')} " in qn]
    if full:
        return full
    hits = []
    for c in citizens:
        toks = [t for t in _norm(c.get("citizen_name") or "").split() if len(t) > 2]
        if toks and any(f" {t} " in qn for t in toks):
            hits.append(c)
    return hits[:5]


def _find_named(q: str, items: list[dict[str, Any]], key: str = "name") -> list[dict[str, Any]]:
    qn = f" {_norm(q)} "
    out = []
    for it in items:
        words = [w for w in _norm(it.get(key) or "").split() if len(w) > 3 and w not in {"dam", "stadium", "complex", "shelter", "sports", "hall"}]
        if words and any(f" {w} " in qn for w in words):
            out.append(it)
    return out


def _nearest(lat: float, lon: float, places: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float | None]:
    best, dist = None, None
    for p in places:
        d = haversine_km(lat, lon, float(p["lat"]), float(p["lon"]))
        if dist is None or d < dist:
            best, dist = p, d
    return best, dist


# ------------------------------------------------------------------ facts
def person_card(c: dict[str, Any], zones: list[dict[str, Any]]) -> dict[str, Any]:
    ts = c.get("timestamps") or {}
    lat, lon = c.get("lat"), c.get("lon")
    zone, zkm = (None, None)
    if lat is not None and lon is not None:
        zone, zkm = _nearest(float(lat), float(lon), zones)
    leg1 = c.get("route_to_person") or {}
    leg2 = c.get("route_to_shelter") or {}
    stage = c.get("ops_status") or "queued"
    return {
        "type": "person",
        "name": c.get("citizen_name"),
        "age": c.get("age"),
        "people": c.get("people"),
        "priority": c.get("vulnerability") or "standard",
        "water": c.get("water_level_note"),
        "stage": stage,
        "stage_text": STAGE_TEXT.get(stage, stage),
        "lat": lat,
        "lon": lon,
        "near": zone.get("name") if zone else None,
        "near_km": round(zkm, 2) if zkm is not None else None,
        "unit": c.get("unit_name") if stage != "queued" else None,
        "unit_role": c.get("unit_role"),
        "unit_from": c.get("unit_base_name"),
        "driver_accepted": _ist(c.get("accepted_at")) if c.get("driver_accepted") else None,
        "shelter": c.get("shelter_name"),
        "cluster": c.get("cluster_id"),
        "wait_reason": c.get("ops_wait_reason"),
        "source": c.get("source"),
        "photo_url": c.get("photo_url"),
        "decision": c.get("decision"),
        "leg1": {"km": leg1.get("km"), "min": leg1.get("sim_minutes"), "method": leg1.get("method")} if leg1 else None,
        "leg2": {"km": leg2.get("km"), "min": leg2.get("sim_minutes")} if leg2 else None,
        "times": {k: _ist(ts.get(k)) for k in ("queued", "assigned", "accepted", "en_route", "to_shelter", "rescued") if ts.get(k)},
        "journey": [
            {"at": _ist(j.get("at")), "agent": j.get("agent"), "text": j.get("detail") or j.get("event")}
            for j in (c.get("journey") or [])[-6:]
        ],
    }


def person_facts(p: dict[str, Any]) -> str:
    bits = [f"{p['name']}: age {p['age']}, {p['people']} people, priority {p['priority']}, water {p['water']}."]
    bits.append(f"Status: {p['stage_text']}.")
    if p.get("near"):
        bits.append(f"Location: GPS {p['lat']}, {p['lon']}, about {p['near_km']} km from {p['near']}.")
    if p.get("unit"):
        bits.append(f"Unit: {p['unit']} ({p['unit_role']}) from {p['unit_from']}.")
    if p.get("driver_accepted"):
        bits.append(f"Driver accepted at {p['driver_accepted']}.")
    if p.get("shelter"):
        bits.append(f"Shelter: {p['shelter']}.")
    if p.get("leg1") and p["leg1"].get("km") is not None:
        bits.append(f"Route to them: {p['leg1']['km']} km, {p['leg1']['min']} min.")
    if p.get("leg2") and p["leg2"].get("km") is not None:
        bits.append(f"Route to shelter: {p['leg2']['km']} km, {p['leg2']['min']} min.")
    if p.get("wait_reason") and p["stage"] == "queued":
        bits.append(f"Waiting because: {p['wait_reason']}.")
    if p.get("times"):
        bits.append("Times: " + ", ".join(f"{k} {v}" for k, v in p["times"].items()) + ".")
    d = p.get("decision") or {}
    if d:  # F13: why the allocator chose this unit / shelter
        q, u, s = d.get("queue") or {}, d.get("unit") or {}, d.get("shelter") or {}
        why = [f"Why: queue rank {q.get('rank')} ({q.get('vulnerability')}, vulnerable-first)"]
        if u.get("name"):
            pol = (u.get("choice") or {}).get("policy")
            why.append(f"{u['name']} because it {u.get('why')}" + (f", dispatch policy {pol}" if pol else ""))
        if s.get("chosen"):
            why.append(f"{s['chosen']} as the nearest open shelter with seats and an open road")
        bits.append("; ".join(why) + ".")
    return " ".join(bits)


def dam_card(d: dict[str, Any]) -> dict[str, Any]:
    frl, dead, now = d.get("full_reservoir_level_m"), d.get("dead_storage_level_m"), d.get("current_level_m")
    card = {
        "type": "dam",
        "name": d.get("name"),
        "river": d.get("river"),
        "state": d.get("state"),
        "frl_m": frl,
        "dead_m": dead,
        "level_m": now,
        "live_capacity_mcm": d.get("live_capacity_mcm"),
        "live_capacity_tmc": round(d["live_capacity_mcm"] / 28.3168, 2) if d.get("live_capacity_mcm") else None,
        "fill_pct": d.get("fill_percentage"),
        "status": d.get("status"),
        "downstream": d.get("downstream_region"),
        "note": d.get("capacity_note"),
    }
    if d.get("gauge_unit") == "ft" and d.get("gauge_zero_m") is not None:
        z = float(d["gauge_zero_m"])
        card["gauge_full_ft"] = d.get("gauge_full")
        card["level_ft"] = round((float(now) - z) / 0.3048, 1) if now is not None else None
    return card


def dam_facts(c: dict[str, Any]) -> str:
    full = f"{c['gauge_full_ft']} ft on its own gauge (= {c['frl_m']} m MSL)" if c.get("gauge_full_ft") else f"{c['frl_m']} m MSL"
    s = (
        f"{c['name']} ({c['river']}, {c['state']}): full capacity level {full}, "
        f"dead storage {c['dead_m']} m, level now {c['level_m']} m, {c['fill_pct']}% filled ({c['status']}), "
        f"live capacity {c['live_capacity_mcm']} MCM ({c['live_capacity_tmc']} TMC)."
    )
    if c.get("gauge_full_ft"):
        s += f" Gauge reading now {c['level_ft']} ft."
    if c.get("downstream"):
        s += f" Downstream: {c['downstream']}."
    return s


def _summary(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    rows = state.get("citizens") or []
    by = {k: sum(1 for c in rows if (c.get("ops_status") or "queued") == k) for k in STAGE_TEXT}
    ma = state.get("multi_agent") or {}
    last = (state.get("history") or [{}])[-1] if state.get("history") else {}
    p = (state.get("current") or {}).get("flood_probability")
    card = {
        "type": "summary",
        "run_status": state.get("status"),
        "scenario": state.get("scenario"),
        "probability_pct": round(p * 100, 1) if p is not None else None,
        "tier": ma.get("tier_label"),
        "rain_mm": round(last["rainfall_mm"], 1) if last.get("rainfall_mm") is not None else None,
        "river_m": last.get("river_m"),
        "barrage_m": last.get("dam_m"),
        "sos": len(rows),
        "by_stage": by,
        "people_safe": sum(int(c.get("people") or 1) for c in rows if c.get("ops_status") == "rescued"),
    }
    if not state.get("run_id") or card["probability_pct"] is None:
        return (
            f"No scenario has produced a flood probability yet (run {card['run_status'] or 'idle'}). "
            "Run a scenario on the Setup tab to get live answers.",
            card,
        )
    text = (
        f"Run {card['run_status']} (scenario {card['scenario']}). Flood probability {card['probability_pct']}%; "
        f"response: {card['tier']}. Rain {card['rain_mm']} mm/24 h, river gauge {card['river_m']} m, barrage {card['barrage_m']} m. "
        f"{card['sos']} SOS: {by['queued']} waiting, {by['assigned']} allocated, {by['en_route']} unit driving, "
        f"{by['to_shelter']} going to shelter, {by['rescued']} safe ({card['people_safe']} people safe)."
    )
    city = state.get("city") or {}
    if city.get("name"):
        text += (f" City: {city['name']} ("
                 + ("river gauge " + str((city.get("gauge") or {}).get("station")) if city.get("flood_driver") == "river"
                    else "rainfall-driven, no river gauge") + ").")
    v2 = ((state.get("pipeline") or {}).get("prediction") or {}).get("v2") or {}
    u = v2.get("uncertainty") or {}
    if u and v2.get("predicted_peak_flood_level_m") is not None:
        cov = u.get("measured_coverage")
        text += (
            f" Model peak level {v2['predicted_peak_flood_level_m']} m, {u.get('level')} {u.get('peak_level_low_m')} to "
            f"{u.get('peak_level_high_m')} m (measured coverage {round(cov * 100, 1) if cov is not None else 'n/a'}% on held-out gauges)."
            " The flood probability itself is an operational blend with no interval."
        )
    return text, card


def _fleet(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    f = state.get("fleet_board") or {}
    busy = [a for a in f.get("ambulances") or [] if a.get("status") == "busy"]
    text = (
        f"Ambulances: {f.get('ambulances_free')} of {f.get('ambulances_total')} free, {f.get('ambulances_busy')} on jobs"
        + (": " + "; ".join(f"{a['name']} → {a.get('job', {}).get('citizen_name', 'busy')} ({a.get('job', {}).get('stage', 'active')})" for a in busy if a.get("job")) if any(a.get("job") for a in busy) else "")
        + f". {len(f.get('waiting_for_ambulance') or [])} SOS waiting for an ambulance. "
        f"{len(f.get('rescue_units_active') or [])} rescue teams on jobs."
    )
    return text, {"type": "fleet", **{k: f.get(k) for k in ("ambulances_free", "ambulances_total", "ambulances_busy")}, "busy": busy, "waiting": f.get("waiting_for_ambulance") or []}


def _shelters(state: dict[str, Any], only: list[dict[str, Any]] | None = None) -> tuple[str, dict[str, Any]]:
    sh = only or state.get("shelter_allocation") or []
    free = sum(s.get("seats_left") or 0 for s in sh)
    closed = [s["name"] for s in sh if s.get("closed")]
    full = [s["name"] for s in sh if (s.get("seats_left") or 0) == 0 and not s.get("closed")]
    text = (
        f"Shelters: {free} seats free across {len(sh)} shelters. "
        + " ".join(
            f"{s['name']}: CLOSED by the operator, {s['allocated_this_run']} allocated this run, {s['delivered_this_run']} arrived before closing."
            if s.get("closed")
            else f"{s['name']}: open, {s['seats_left']} of {s['capacity']} free, {s['allocated_this_run']} allocated this run, {s['delivered_this_run']} arrived."
            for s in sh
        )
        + (f" Closed: {', '.join(closed)}." if closed else "")
        + (f" Full: {', '.join(full)}." if full else "")
    )
    return text, {"type": "shelters", "seats_free": free, "items": sh}


# ------------------------------------------------------------------- core
def retrieve(question: str, state: dict[str, Any], dams: list[dict[str, Any]], history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from backend.services.seed import ZONES

    q = _norm(question)
    citizens = state.get("citizens") or []
    facts: list[str] = []
    cards: list[dict[str, Any]] = []
    found_any = False

    people = _find_people(question, citizens)
    if not people and PRONOUN.search(q):
        for h in reversed(history or []):
            people = _find_people(str(h.get("text") or ""), citizens)
            if people:
                break
    for c in people[:3]:
        card = person_card(c, ZONES)
        cards.append(card)
        facts.append(person_facts(card))
        found_any = True

    for d in _find_named(question, dams)[:2]:
        card = dam_card(d)
        cards.append(card)
        facts.append(dam_facts(card))
        found_any = True

    named_shelters = _find_named(question, state.get("shelter_allocation") or [])
    if named_shelters:
        t, card = _shelters(state, named_shelters)
        facts.append(t)
        cards.append(card)
        found_any = True

    for z in _find_named(question, ZONES):
        near = [c for c in citizens if c.get("lat") is not None and haversine_km(float(c["lat"]), float(c["lon"]), z["lat"], z["lon"]) <= 1.5]
        facts.append(
            f"{z['name']} (zone {z['zone_id']}, population {z['population']}): {len(near)} SOS within 1.5 km"
            + (": " + ", ".join(f"{c['citizen_name']} ({STAGE_TEXT.get(c.get('ops_status') or 'queued')})" for c in near[:8]) if near else "")
            + "."
        )
        found_any = True

    m = re.search(r"ambulance unit (\d+)|unit (\d+)", q)
    if m:
        name = f"Ambulance Unit {m.group(1) or m.group(2)}"
        a = next((x for x in (state.get("fleet_board") or {}).get("ambulances") or [] if x["name"] == name), None)
        if a:
            facts.append(
                f"{name} is {a['status']}"
                + (f", on {a['job']['citizen_name']} ({a['job']['stage']}) to {a['job']['shelter_name']}" if a.get("job") else "")
                + f"; {a['trips_completed']} trips done."
            )
            found_any = True

    if _has(q, "ambulance", "vehicle", "unit", "driver", "free", "available", "left") and not m:
        t, card = _fleet(state)
        facts.append(t)
        cards.append(card)
    if _has(q, "shelter", "seat", "capacity", "camp", "left", "space") and not named_shelters and not _find_named(question, dams):
        t, card = _shelters(state)
        facts.append(t)
        cards.append(card)
    if _has(q, "dam", "reservoir") and not _find_named(question, dams):
        facts.append("Dams in the registry: " + "; ".join(f"{d['name']} ({d['state']}) {d.get('fill_percentage')}% filled" for d in dams) + ".")
    if _has(q, "probab", "risk", "flood", "rain", "river", "status", "summary", "overall", "how many", "situation", "tier", "alert", "rescued", "safe", "waiting") or not found_any:
        t, card = _summary(state)
        facts.append(t)
        cards.append(card)
    if _has(q, "agent", "message", "notification", "doing", "action", "playbook"):
        ma = state.get("multi_agent") or {}
        acts = "; ".join(f"{a['name']}: {a.get('action')}" for a in ma.get("agents") or [] if a.get("action"))
        recent = "; ".join(f"{x['from_name']}: {x['text']}" for x in (ma.get("messages") or [])[:5])
        facts.append(f"Agents now ({ma.get('tier_label')}): {acts}. Latest messages: {recent}.")

    if _has(q, "what if", "what-if", "whatif", "if we add", "more ambulance", "extra ambulance", "planner", "option"):
        from backend.services.whatif import facts as whatif_facts

        w = whatif_facts(state.get("tick"))
        if w:
            facts.append(
                f"Last what-if ({w['label']} Taken at tick {w['taken_at_tick']}, {w['runs']} runs, next {w['horizon_min']} sim min"
                + (", now STALE — the run has moved on" if w["stale"] else "") + "): "
                + "; ".join(f"{o['option']}: mean {o['mean_min_to_safe']} min to safe, p90 {o['p90_min_to_safe']}, "
                            f"{o['still_waiting_per_run']} still waiting per run"
                            + (f", {o['diff_vs_no_change_min']:+} min vs no change" if o["diff_vs_no_change_min"] is not None else "")
                            for o in w["options"]) + "."
            )
            cards.append({"type": "whatif", **w})
        else:
            facts.append("No what-if has been run for this scenario yet (Agents tab → What-if planner).")

    missing = []
    if not people and re.search(r"\b(where is|where's|who is|report (for|on|of)|details? (for|of|on))\b", q) and not PRONOUN.search(q):
        missing.append("I could not find that person in this run's SOS list.")
    return {"facts": facts, "cards": cards, "missing": missing}


def _split(question: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\?|\n|;", question) if p.strip()]
    return parts or [question.strip()]


async def _llm(question: str, facts_text: str, history: list[dict[str, Any]], enforce_grounding: bool = True) -> tuple[str | None, str | None]:
    from backend.agents.dialogue import GROQ_MODELS, GROQ_URL, _primary_model, groq_body, grounded
    from backend.config import get_settings

    settings = get_settings()
    key = (settings.groq_api_key or "").strip()
    if not key:
        return None, "GROQ_API_KEY missing"
    convo = "\n".join(f"{h.get('role')}: {h.get('text')}" for h in (history or [])[-6:])
    prompt = (
        f"FACTS (live flood simulation state):\n{facts_text}\n\n"
        f"Conversation so far:\n{convo or '(none)'}\n\n"
        f"Question: {question}\n\n"
        "Answer every part of the question in short, clear sentences, using ONLY the facts. "
        "Use only numbers that appear in the facts. For a dam's full capacity give the full level (in ft when a gauge is given) "
        "and the live capacity. If a part is not in the facts, say so once in one short sentence. "
        'Reply as JSON: {"answer": "<your answer>"}'
    )
    first = _primary_model(settings)
    for model in [first] + [m for m in GROQ_MODELS if m != first]:
        body = groq_body(model, 0.2, 500, [
            {"role": "system", "content": "You are the operations assistant of a flood digital twin. Answer in JSON."},
            {"role": "user", "content": prompt},
        ])
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=body)
            if resp.status_code >= 400:
                continue
            raw = (((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
            try:
                text = str(json.loads(raw).get("answer") or "").strip()
            except (ValueError, AttributeError):
                text = raw.strip()
            if text:
                if not enforce_grounding or grounded([{"text": text}], facts_text):
                    return text, model
        except Exception:  # noqa: BLE001
            continue
    return None, "LLM reply not grounded in the facts"


async def answer(question: str, state: dict[str, Any], dams: list[dict[str, Any]], history: list[dict[str, Any]] | None = None, enforce_grounding: bool = True) -> dict[str, Any]:
    question = (question or "").strip()[:600]
    if not question:
        return {"available": False, "answer": "Ask me about a person, a place, a dam, ambulances or shelters."}
    sections = []
    all_facts: list[str] = []
    cards: list[dict[str, Any]] = []
    for part in _split(question)[:5]:
        r = retrieve(part, state, dams, history)
        sections.append({"question": part, "facts": r["facts"], "missing": r["missing"]})
        for f in r["facts"]:
            if f not in all_facts:
                all_facts.append(f)
        for c in r["cards"]:
            if c not in cards:
                cards.append(c)
    facts_text = "\n".join(all_facts)
    rules = "\n\n".join(
        (f"Q: {s['question']}\n" if len(sections) > 1 else "") + " ".join(s["missing"] + s["facts"]) for s in sections
    )
    misses = [m for s in sections for m in s["missing"]]
    # Every part asks about an unknown person: skip the LLM, it only padded
    # the reply with "No information available."
    text, how = (None, "person not found") if sections and all(s["missing"] for s in sections) else await _llm(question, facts_text, history or [], enforce_grounding=enforce_grounding)
    if text and misses:
        text = " ".join(misses) + "\n\n" + text
    if how == "person not found":
        rules = " ".join(misses)
    return {
        "available": True,
        "answer": text or rules,
        "source": "groq" if text else "rules",
        "model": how if text else None,
        "fallback_reason": None if text else how,
        "facts": all_facts,
        "cards": cards[:6],
        "asked_at": datetime.now(timezone.utc).isoformat(),
    }
