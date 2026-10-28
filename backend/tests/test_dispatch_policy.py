"""F8 — ambulance positions + greedy / optimal dispatch; F9 — pre-positioning."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import person_ops as po
from backend.services.seed import GRAPH_NODES, RESCUE_TEAMS

T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
TEAM = RESCUE_TEAMS[2]


def _queued(name, node, age=80, index=1):
    lat, lon = GRAPH_NODES[node]
    row = {"citizen_name": name, "age": age, "water_level_note": "chest-deep", "people": 1, "lat": lat, "lon": lon,
           "cluster_id": "C1", "assigned_team": TEAM["name"], "assigned_team_name": TEAM["name"]}
    po.ensure_ops(row, index, queue_position=1, at=T0)
    row["person_index"] = index
    return row


def _dropped(amb, node, at):
    """A finished job that leaves `amb` at the shelter placed on `node`."""
    lat, lon = GRAPH_NODES[node]
    return {"citizen_name": f"done-{amb}", "ops_status": "rescued", "ambulance_name": amb, "unit_name": amb,
            "shelter_name": f"S@{node}", "shelter_lat": lat, "shelter_lon": lon, "lat": lat, "lon": lon,
            "timestamps": {"rescued": po._iso(at)}, "people": 1}


def test_positions_are_home_depot_then_last_drop_off():
    pos = po.ambulance_positions([], {"teams": RESCUE_TEAMS}, T0)
    home0 = po.ambulance_home(po.AMBULANCE_POOL[0], RESCUE_TEAMS)
    assert pos[po.AMBULANCE_POOL[0]]["lat"] == home0["lat"] and pos[po.AMBULANCE_POOL[0]]["kind"] == "depot"
    # round-robin over depots
    assert po.ambulance_home(po.AMBULANCE_POOL[1], RESCUE_TEAMS)["place"] == RESCUE_TEAMS[1]["name"]
    rows = [_dropped(po.AMBULANCE_POOL[0], "IIT", T0)]
    pos = po.ambulance_positions(rows, {"teams": RESCUE_TEAMS}, T0)
    assert pos[po.AMBULANCE_POOL[0]]["kind"] == "shelter"
    assert (pos[po.AMBULANCE_POOL[0]]["lat"], pos[po.AMBULANCE_POOL[0]]["lon"]) == GRAPH_NODES["IIT"]


def test_greedy_sends_the_ambulance_that_is_closest_by_road():
    # Every ambulance but #3 is at its depot; #3 just dropped someone at AIIMS, next to the caller.
    rows = [_dropped(po.AMBULANCE_POOL[2], "AIIMS", T0 - timedelta(minutes=1)), _queued("Near AIIMS", "THYAGARAJ")]
    ctx = {"teams": RESCUE_TEAMS, "dispatch_policy": "greedy"}
    po.advance_all(rows, ctx, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS))
    row = rows[1]
    assert row["ops_status"] == "assigned"
    assert row["ambulance_name"] == po.AMBULANCE_POOL[2]
    assert tuple(row["unit_base"]) == GRAPH_NODES["AIIMS"]
    assert row["dispatch_choice"]["policy"] == "greedy"


def test_nearest_depot_policy_is_the_original_rule():
    rows = [_queued("X", "THYAGARAJ")]
    po.advance_all(rows, {"teams": RESCUE_TEAMS}, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS))
    assert rows[0]["ambulance_name"] == po.AMBULANCE_POOL[0]
    assert rows[0]["dispatch_choice"]["policy"] == "nearest_depot"


def _weighted_total(rows, ctx):
    total = 0.0
    for r in rows:
        mins = po._road_minutes([tuple(r["unit_base"])], [(r["lat"], r["lon"])], ctx.get("roads"))[0][0]
        total += mins * po.VULN_WEIGHT.get(r["vulnerability"], 1.0)
    return total


def test_optimal_is_never_worse_than_greedy_on_a_batch():
    # Only two ambulances free (the rest busy); two callers waiting at once.
    busy = [{"citizen_name": f"b{i}", "ops_status": "en_route", "ambulance_name": a, "unit_name": a}
            for i, a in enumerate(po.AMBULANCE_POOL[2:])]
    drops = [_dropped(po.AMBULANCE_POOL[0], "CWG", T0 - timedelta(minutes=5)),
             _dropped(po.AMBULANCE_POOL[1], "AZADPUR", T0 - timedelta(minutes=5))]

    def scenario(policy):
        a = _queued("A", "MAYUR", index=1)
        b = _queued("B", "DU", index=2)
        for r in (a, b):
            r["ops_stage_at"] = po._iso(T0)
            r["ops_stage_seconds"] = 0.0
        rows = [dict(x) for x in busy + drops] + [a, b]
        ctx = {"teams": RESCUE_TEAMS, "dispatch_policy": policy}
        po.advance_all(rows, ctx, now=T0 + timedelta(seconds=0.5))
        got = [r for r in rows if r["citizen_name"] in ("A", "B")]
        assert all(r["ops_status"] == "assigned" for r in got)
        return _weighted_total(got, ctx), got

    greedy, _ = scenario("greedy")
    optimal, got = scenario("optimal")
    assert optimal <= greedy + 1e-6
    assert got[0]["dispatch_choice"]["policy"] == "optimal" and got[0]["dispatch_choice"]["batch_size"] == 2


def test_staging_moves_idle_ambulances_toward_demand_and_dispatch_starts_mid_move():
    rows = [_queued(f"P{i}", n, index=i) for i, n in enumerate(["GEETA", "YBANK", "MAYUR"], start=1)]
    for r in rows:
        r["ops_stage_at"] = po._iso(T0 + timedelta(hours=1))  # not yet due: all ambulances idle
    ctx = {"teams": RESCUE_TEAMS, "staging": {}}
    moves = po.plan_staging(rows, ctx, 0.8, now=T0)
    assert moves, "idle ambulances get staging moves"
    for mv in moves.values():
        assert mv["points"] and mv["seconds"] > 0 and mv["to"]
    ctx["staging"] = moves
    a = next(iter(moves))
    half = T0 + timedelta(seconds=moves[a]["seconds"] / 2)
    pos = po.ambulance_positions(rows, ctx, half)[a]
    assert pos["kind"] == "repositioning" and 0.3 < pos["progress"] < 0.7 and pos["route"]
    # a second plan right away keeps the same ambulances where they are going
    assert not set(po.plan_staging(rows, ctx, 0.8, now=half)) & set(moves)


def test_unknown_policy_rejected_by_schema():
    from pydantic import ValidationError

    from backend.schemas.common import SimulationStartRequest

    with pytest.raises(ValidationError):
        SimulationStartRequest(scenario="heavy_rainfall", dispatch_policy="random")
    assert SimulationStartRequest(scenario="heavy_rainfall").dispatch_policy == "nearest_depot"
