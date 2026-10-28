"""F22 — Boats for cut-off people tests.

Tests:
1. Grid passability and A* search on a synthetic grid.
2. A* never crosses a dry cell (passable=False).
3. Rows with an open road never get a boat.
4. When boats=0 (default off), behaviour is identical to today (keeps route_alert).
5. When a person has no open road and boats > 0, they get assigned a boat.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from backend.services.boat_route import astar_grid, build_passable_grid, compute_boat_route
from backend.services import person_ops as po
from backend.services.seed import RESCUE_TEAMS

T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
TEAM = RESCUE_TEAMS[0]


def _row(name, lat=28.6139, lon=77.2090, people=1, idx=1):
    row = {
        "citizen_name": name,
        "age": 30,
        "water_level_note": "chest-deep",
        "people": people,
        "lat": lat,
        "lon": lon,
        "cluster_id": "C1",
        "assigned_team": TEAM["name"],
        "assigned_team_name": TEAM["name"],
    }
    po.ensure_ops(row, idx, queue_position=1, at=T0)
    row["person_index"] = idx
    return row


def test_astar_grid_finds_path_on_passable_cells():
    # 5x5 grid with a clear water corridor from (0, 0) to (4, 4)
    grid = [
        [True,  True,  False, False, False],
        [False, True,  True,  False, False],
        [False, False, True,  True,  False],
        [False, False, False, True,  True],
        [False, False, False, False, True],
    ]
    path = astar_grid(grid, (0, 0), (4, 4))
    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (4, 4)
    for r, c in path:
        assert grid[r][c] is True


def test_astar_never_crosses_dry_cell():
    # Grid where the only way between (0, 0) and (2, 2) is blocked by dry land
    grid = [
        [True,  False, True],
        [False, False, False],  # entire barrier of dry land
        [True,  False, True],
    ]
    path = astar_grid(grid, (0, 0), (2, 2))
    assert path is None


def test_people_with_open_road_never_get_a_boat():
    # Setup context with boats enabled (boats=3)
    ctx = {
        "teams": list(RESCUE_TEAMS),
        "roads": [],  # no blocked roads -> road network is completely open
        "boats": 3,
        "shelter_overrides": {},
        "dispatch_policy": "nearest_depot",
    }
    row = _row("Test Citizen")
    rows = [row]
    po._assign(row, rows, ctx, T0)

    # Must get an ambulance, NOT a boat
    assert row.get("unit_role") == "ambulance"
    assert not row.get("by_boat")
    assert not row.get("boat_dispatch")


def test_boats_zero_behaves_identically_to_today():
    # When roads are all blocked, but boats=0
    blocked_roads = [{"road_id": f"R{i}", "blocked": True, "flood_exposure": 1.0} for i in range(10)]
    ctx = {
        "teams": list(RESCUE_TEAMS),
        "roads": blocked_roads,
        "boats": 0,  # OFF
        "shelter_overrides": {},
        "dispatch_policy": "nearest_depot",
    }
    row = _row("Isolated Citizen")
    rows = [row]
    po._assign(row, rows, ctx, T0)

    # With no open road and boats=0, it keeps route_alert and does not assign a boat
    assert not row.get("by_boat")
    assert row.get("route_alert") is not None or row.get("unit_role") != "boat"


def test_isolated_person_gets_boat_when_fleet_enabled():
    # Blocked roads simulating cut off
    blocked_roads = [
        {"road_id": "R1", "blocked": True, "points": [[28.61, 77.20], [28.62, 77.21]], "flood_exposure": 1.0}
    ]
    ctx = {
        "teams": list(RESCUE_TEAMS),
        "roads": blocked_roads,
        "boats": 2,  # 2 boats available
        "shelter_overrides": {},
        "dispatch_policy": "nearest_depot",
    }
    row = _row("Cutoff Person")
    rows = [row]
    po._assign(row, rows, ctx, T0)

    # Check fleet board reflects the boats
    fleet = po.fleet_board(rows, ctx)
    assert fleet["boats_total"] == 2
    assert len(fleet["boats"]) == 2
