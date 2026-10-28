"""Simulated-QAOA route choice and the multi-agent response tiers."""

import numpy as np
import pytest

from backend.agents.mas import MultiAgentSystem, tier_for
from backend.optimization.qaoa_route import _energies, _state, qaoa_choose
from backend.thresholds import ESCALATION_FIELD, ESCALATION_READY


def test_qaoa_state_is_normalised_and_mixer_is_unitary():
    energy = _energies(np.array([0.0, 0.5, 1.0]))
    psi = _state(energy, 3, [0.7, 1.1], [0.4, 0.2])
    assert np.sum(np.abs(psi) ** 2) == pytest.approx(1.0)


def test_one_hot_states_are_the_qubo_minimum():
    costs = np.array([0.3, 0.1, 0.9])
    energy = _energies(costs)
    assert int(np.argmin(energy)) == 1 << 1  # bitstring with only route 1 set
    for s in range(8):
        if bin(s).count("1") != 1:
            assert energy[s] > costs.max()


@pytest.mark.parametrize("seed", range(6))
def test_qaoa_picks_the_cheapest_route(seed):
    rng = np.random.default_rng(seed)
    costs = list(rng.random(4))
    out = qaoa_choose(costs)
    assert out["chosen"] == out["exhaustive_best"] == int(np.argmin(costs))
    assert out["matches_exhaustive"] is True
    assert sum(out["route_probabilities"]) <= 1.0 + 1e-9
    assert out["feasible_probability"] > 0.5  # penalty keeps mass on one-hot states
    assert out["expected_energy"] >= out["ground_energy"] - 1e-9


def test_tiers_follow_the_thresholds():
    assert tier_for(None) == "WAITING"
    assert tier_for(ESCALATION_READY - 0.01) == "ADMIN"
    assert tier_for(ESCALATION_READY) == "READY"
    assert tier_for(ESCALATION_FIELD) == "FIELD"


def _update(mas, p, rain=40.0):
    fleet = {"ambulances": [{"name": "Ambulance Unit 1", "status": "free"}], "ambulances_total": 1, "ambulances_free": 1, "ambulances_busy": 0}
    return mas.update(
        run_id="r1",
        status="running",
        probability=p,
        last={"rainfall_mm": rain, "river_m": 204.0, "dam_m": 199.0},
        rows=[],
        fleet=fleet,
        shelters=[{"name": "S1", "seats_left": 100, "allocated_this_run": 0}],
    )


def test_manager_escalates_and_notifies_units():
    mas = MultiAgentSystem()
    v = _update(mas, 0.40)
    assert v["tier"] == "ADMIN"
    assert any(m["from"] == "manager" and m["to"] == ["administrator"] for m in v["messages"])

    v = _update(mas, 0.62, rain=120.0)
    assert v["tier"] == "READY"
    crit = [m for m in v["messages"] if m["kind"] == "critical"]
    assert crit and {"ambulance", "shelter", "rescue"} <= set(crit[0]["to"])
    assert {n["type"] for n in v["notified"]} == {"ambulance", "shelter"}

    v = _update(mas, 0.81, rain=300.0)
    assert v["tier"] == "FIELD"
    assert [h["tier"] for h in v["tier_history"]] == ["ADMIN", "READY", "FIELD"]
    assert all(n["status"] in ("deployed", "on job", "intake open") for n in v["notified"])


def test_messages_are_not_repeated_on_every_poll():
    mas = MultiAgentSystem()
    _update(mas, 0.62)
    n = len(mas.messages)
    for _ in range(5):
        _update(mas, 0.62)
    assert len(mas.messages) == n


def test_new_run_resets_the_board():
    mas = MultiAgentSystem()
    _update(mas, 0.8)
    v = mas.update(run_id="r2", status="running", probability=None, last=None, rows=[], fleet={}, shelters=[])
    assert v["tier"] == "WAITING" and v["messages"] == []


def test_every_message_has_a_traffic_light_severity():
    mas = MultiAgentSystem()
    for p in (0.40, 0.62, 0.81):
        v = _update(mas, p)
    assert {m["severity"] for m in v["messages"]} <= {"green", "yellow", "red"}
    sev = {m["title"]: m["severity"] for m in v["messages"]}
    assert sev["ALL ON FIELD"] == "red"
    assert sev["CRITICAL — be ready"] == "yellow"
    assert sev["Handed to Administrator"] == "green"
    assert v["severity_counts"]["red"] >= 1


def test_sudden_rise_runs_the_playbook_once():
    mas = MultiAgentSystem()
    prev = {"tick": 3, "flood_probability": 0.40, "rainfall_mm": 10.0}
    last = {"tick": 4, "flood_probability": 0.81, "rainfall_mm": 50.0, "sim_time_sec": 8}
    kw = dict(run_id="r1", status="running", probability=0.81, rows=[], fleet={}, shelters=[])
    for _ in range(3):  # repeated polls of the same tick
        v = mas.update(last=last, prev=prev, **kw)
    sudden = [m for m in v["messages"] if m["kind"] == "sudden"]
    assert len(sudden) == 1 and sudden[0]["severity"] == "red"
    assert "40.0% → 81.0%" in sudden[0]["text"]
    acts = [m for m in v["messages"] if m["title"] == "SUDDEN RISE · action"]
    assert {m["from"] for m in acts} >= {"probability", "ambulance", "shelter"}


def test_playbook_edits_change_what_agents_say_and_reset_restores():
    from backend.agents import mas as M

    try:
        M.set_playbook({"actions": {"READY": {"ambulance": "Fuel up and wait at Gate 2."}}, "sudden_rise_points": 25})
        assert M.get_playbook()["sudden_rise_points"] == 25
        bot = MultiAgentSystem()
        v = _update(bot, 0.6)
        assert any(m["from"] == "ambulance" and m["text"] == "Fuel up and wait at Gate 2." for m in v["messages"])
        assert next(a for a in v["agents"] if a["key"] == "ambulance")["action"] == "Fuel up and wait at Gate 2."
    finally:
        M.set_playbook({"reset": True})
    assert M.get_playbook() == M.DEFAULT_PLAYBOOK
