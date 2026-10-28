"""AI tab: retrieval is grounded in the simulation state (no network)."""

import asyncio

import pytest

from backend.services import ai_assistant as ai
from backend.services.dam_risk import list_dams

STATE = {
    "status": "running",
    "scenario": "heavy_rainfall",
    "current": {"flood_probability": 0.62},
    "history": [{"rainfall_mm": 120.0, "river_m": 205.1, "dam_m": 200.2}],
    "multi_agent": {"tier_label": "CRITICAL", "agents": [], "messages": []},
    "citizens": [
        {
            "citizen_name": "Priya Sharma",
            "age": 29,
            "people": 3,
            "lat": 28.651,
            "lon": 77.262,
            "water_level_note": "knee-deep",
            "vulnerability": "standard",
            "ops_status": "en_route",
            "unit_name": "Delhi Fire Service HQ",
            "unit_role": "rescue",
            "unit_base_name": "Delhi Fire Service HQ",
            "driver_accepted": True,
            "accepted_at": "2026-10-08T10:00:05+00:00",
            "shelter_name": "Talkatora Indoor Stadium",
            "route_to_person": {"km": 4.2, "sim_minutes": 18.0, "method": "qaoa-flood"},
            "timestamps": {"queued": "2026-10-08T10:00:00+00:00", "accepted": "2026-10-08T10:00:05+00:00"},
        }
    ],
    "fleet_board": {"ambulances": [], "ambulances_free": 7, "ambulances_total": 10, "ambulances_busy": 3, "waiting_for_ambulance": [], "rescue_units_active": []},
    "shelter_allocation": [
        {"name": "Talkatora Indoor Stadium", "capacity": 1200, "seats_left": 1150, "allocated_this_run": 3, "delivered_this_run": 0}
    ],
}


def test_finds_a_person_and_reports_from_state():
    r = ai.retrieve("give me the full report of priya sharma", STATE, [])
    card = next(c for c in r["cards"] if c["type"] == "person")
    assert card["shelter"] == "Talkatora Indoor Stadium"
    assert card["near"] == "Yamuna Pushta / Geeta Colony"
    assert card["driver_accepted"] == "15:30:05 IST"
    assert "unit driving to them" in r["facts"][0]


def test_pronoun_follows_the_last_person_named():
    r = ai.retrieve("where is she now", STATE, [], history=[{"role": "user", "text": "report for Priya Sharma"}])
    assert any(c["type"] == "person" and c["name"] == "Priya Sharma" for c in r["cards"])


def test_unknown_person_is_reported_not_invented():
    r = ai.retrieve("where is Rahul Kapoor", STATE, [])
    assert r["missing"] and not any(c["type"] == "person" for c in r["cards"])


def test_dam_question_uses_the_registry_and_mettur_gauge():
    r = ai.retrieve("full capacity of mettur dam", STATE, list_dams())
    card = next(c for c in r["cards"] if c["type"] == "dam")
    assert card["gauge_full_ft"] == 120.0 and card["live_capacity_tmc"] == pytest.approx(93.47, abs=0.01)


def test_counts_question_brings_fleet_and_shelters():
    r = ai.retrieve("how many ambulances and shelter seats are left", STATE, [])
    kinds = {c["type"] for c in r["cards"]}
    assert {"fleet", "shelters"} <= kinds
    assert any("7 of 10 free" in f for f in r["facts"])


def test_answer_falls_back_to_facts_when_llm_unavailable(monkeypatch):
    async def no_llm(*_a, **_k):
        return None, "GROQ_API_KEY missing"

    monkeypatch.setattr(ai, "_llm", no_llm)
    out = asyncio.run(ai.answer("How many ambulances left? Where is Priya Sharma?", STATE, []))
    assert out["source"] == "rules"
    assert "7 of 10 free" in out["answer"] and "Talkatora" in out["answer"]
