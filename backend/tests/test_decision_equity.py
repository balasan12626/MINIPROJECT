"""F13 — the allocator records why; F14 — fairness board from the stage machine's timestamps."""
from datetime import datetime, timedelta, timezone

from backend.services import person_ops as po
from backend.services.seed import RESCUE_TEAMS

T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
TEAM = RESCUE_TEAMS[2]


def _queued(name="Priya", age=80, index=1):
    row = {"citizen_name": name, "age": age, "water_level_note": "knee-deep", "people": 2, "lat": 28.651, "lon": 77.262,
           "cluster_id": "C1", "assigned_team": TEAM["name"], "assigned_team_name": TEAM["name"]}
    po.ensure_ops(row, index, queue_position=1, at=T0)
    row["person_index"] = index
    return row


def test_assign_records_why_with_only_real_alternatives():
    closed = po.SHELTER_POOL[0]
    ctx = {"teams": RESCUE_TEAMS, "dispatch_policy": "greedy", "shelter_overrides": {closed: {"closed": True}}}
    other = _queued("Earlier", age=30, index=1)
    row = _queued("Priya", age=80, index=2)
    po.advance_all([other, row], ctx, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS))
    d = row["decision"]
    assert d["queue"]["rank"] == 2 and d["queue"]["people_ahead"] == 1 and d["queue"]["vulnerability"] == "elderly"
    assert d["unit"]["name"] == row["unit_name"] and d["unit"]["choice"]["policy"] == "greedy"
    assert d["unit"]["choice"]["considered"], "greedy lists the ambulances it compared"
    assert d["shelter"]["chosen"] == row["shelter_name"]
    assert row["shelter_name"] not in [s["name"] for s in d["shelter"]["next_options"]]
    assert closed in d["shelter"]["closed"] and closed not in [s["name"] for s in d["shelter"]["next_options"]]
    assert d["route"]["km"] == row["route_to_person"]["km"]


def _done(name, vuln, cluster, safe_min, pickup_min=None):
    q = T0
    scale = 60.0 / po.TIME_SCALE  # sim minutes → wall seconds
    ts = {"queued": po._iso(q), "rescued": po._iso(q + timedelta(seconds=safe_min * scale))}
    if pickup_min is not None:
        ts["to_shelter"] = po._iso(q + timedelta(seconds=pickup_min * scale))
    return {"citizen_name": name, "vulnerability": vuln, "cluster_id": cluster, "ops_status": "rescued", "timestamps": ts}


def test_equity_board_flags_a_slow_group_and_counts_waiting_people():
    rows = [_done(f"s{i}", "standard", "C1", 20 + i, 10) for i in range(5)]
    rows += [_done(f"e{i}", "elderly", "C2", 60 + i, 40) for i in range(3)]
    waiting = {"citizen_name": "w", "vulnerability": "child", "cluster_id": "C2", "ops_status": "queued",
               "timestamps": {"queued": po._iso(T0)}}
    rows.append(waiting)
    now = T0 + timedelta(seconds=30)  # 30 wall s = 60 sim minutes waiting
    eq = po.equity_board(rows, now=now)
    assert eq["overall"]["served"] == 8 and eq["overall"]["people"] == 9
    v = {g["group"]: g for g in eq["by_vulnerability"]}
    assert v["standard"]["safe_p50"] == 22.0 and not v["standard"]["flag"]
    assert v["elderly"]["flag"] is True  # median 61 ≥ 1.5 × overall median
    assert v["child"]["served"] == 0 and v["child"]["still_waiting"] == 1
    assert v["child"]["longest_wait_min"] == 60.0
    assert any("elderly" in f for f in eq["flagged"])
    c = {g["group"]: g for g in eq["by_cluster"]}
    assert c["C2"]["people"] == 4


def test_small_groups_are_not_flagged():
    rows = [_done(f"s{i}", "standard", "C1", 20) for i in range(5)] + [_done("e", "elderly", "C1", 90)]
    eq = po.equity_board(rows, now=T0)
    assert not {g["group"]: g for g in eq["by_vulnerability"]}["elderly"]["flag"]
