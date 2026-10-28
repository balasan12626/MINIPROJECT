"""F21 — hospitals (OSM only, beds null unless tagged) + medical triage on the one stage machine."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.geo import cities
from backend.services import person_ops as po
from backend.services import seed
from backend.services.seed import GRAPH_NODES, RESCUE_TEAMS

T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
TEAM = RESCUE_TEAMS[2]
CTX = {"teams": RESCUE_TEAMS}
AIIMS = {"hospital_id": "H01", "name": "Test Hospital near AIIMS", "lat": GRAPH_NODES["AIIMS"][0], "lon": GRAPH_NODES["AIIMS"][1],
         "osm": "node/1", "beds": None}


@pytest.fixture(autouse=True)
def legacy_city():
    cities.activate(cities.LEGACY)
    yield
    cities.activate(cities.LEGACY)


@pytest.fixture
def hospitals(monkeypatch):
    monkeypatch.setattr(seed, "HOSPITALS", [dict(AIIMS)])
    yield seed.HOSPITALS



def _row(name, medical=None, age=30, water="knee-deep", lat=28.651, lon=77.262, idx=1):
    row = {"citizen_name": name, "age": age, "water_level_note": water, "people": 1, "lat": lat, "lon": lon,
           "cluster_id": "C1", "assigned_team": TEAM["name"], "assigned_team_name": TEAM["name"]}
    if medical:
        row["medical"] = medical
    po.ensure_ops(row, idx, queue_position=1, at=T0)
    row["person_index"] = idx
    return row


@pytest.mark.parametrize("cid", [c for c in cities.available_ids() if c != cities.LEGACY])
def test_city_hospitals_are_osm_with_beds_only_when_tagged(cid):
    c = cities.load_city(cid)
    for h in c.get("hospitals") or []:
        assert h["osm"].split("/")[0] in ("node", "way", "relation") and h["name"]
        assert h["beds"] is None or (isinstance(h["beds"], int) and h["beds_source"] == "OSM beds tag")


def test_critical_goes_to_hospital_with_an_ambulance(hospitals):
    r = _row("Injured Person", medical="critical")
    assert r["needs_ambulance"] is True
    po.advance_all([r], CTX, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS + 0.5))
    assert r["ops_status"] == "assigned"
    assert r["destination_kind"] == "hospital" and r["shelter_name"] == AIIMS["name"]
    assert r["unit_role"] == "ambulance"
    assert r["decision"]["shelter"]["destination_kind"] == "hospital"
    assert r["decision"]["shelter"]["hospitals_considered"][0]["name"] == AIIMS["name"]


def test_critical_is_served_before_a_standard_row_when_ambulances_run_out(hospitals, monkeypatch):
    monkeypatch.setattr(po, "AMBULANCE_POOL", ["Ambulance Unit 1"])
    std = _row("Elderly First", age=80, water="chest-deep", idx=1)  # older SOS, ambulance case, no medical flag
    crit = _row("Critical Second", medical="critical", idx=2)
    rows = [std, crit]
    po.advance_all(rows, CTX, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS + 0.5))
    assert crit["ops_status"] == "assigned" and crit["unit_name"] == "Ambulance Unit 1"
    assert std["ops_status"] == "queued" and "busy" in (std.get("ops_wait_reason") or "")


def test_no_hospital_reachable_falls_back_to_a_shelter_with_alert(hospitals):
    r = _row("Cut Off", medical="injured")
    roads = [{**x, "blocked": True, "accessible": False} for x in seed.ROADS]
    po.advance_all([r], {**CTX, "roads": roads}, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS + 0.5))
    assert r["destination_kind"] == "shelter" and r["shelter_name"] in po.SHELTER_POOL
    assert "No hospital reachable" in r["hospital_alert"]["reason"]


def test_without_hospitals_or_medical_nothing_changes():
    old_hosp = list(seed.HOSPITALS)
    try:
        seed.HOSPITALS[:] = []
        a = _row("Plain", age=80, water="chest-deep")
        po.advance_all([a], CTX, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS + 0.5))
        assert a["destination_kind"] == "shelter" and a["shelter_name"] in po.SHELTER_POOL
        b = _row("Hurt, no hospital mapped", medical="injured")
        po.advance_all([b], CTX, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS + 0.5))
        assert b["destination_kind"] == "shelter"
        assert po.triage_rank(a) == 2 and po.dispatch_weight(a) == po.VULN_WEIGHT["elderly"]
    finally:
        seed.HOSPITALS[:] = old_hosp

