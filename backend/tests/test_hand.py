"""F26 — Tests for Height-based road flood risk (HAND)."""

import numpy as np
import pytest

from scripts.build_hand import compute_d8_hand, build_hand_for_city, HAND_CITATION


def test_hand_on_synthetic_valley():
    # 5x5 grid with a central river valley at column 2
    # Elevations: column 2 is 10m, column 1 & 3 are 20m, column 0 & 4 are 30m
    elev = np.array([
        [30, 20, 10, 20, 30],
        [30, 20, 10, 20, 30],
        [30, 20, 10, 20, 30],
        [30, 20, 10, 20, 30],
        [30, 20, 10, 20, 30],
    ], dtype=np.float64)

    drainage = np.zeros_like(elev, dtype=bool)
    drainage[:, 2] = True  # column 2 is the river

    hand = compute_d8_hand(elev, drainage)

    # HAND >= 0 everywhere
    assert np.all(hand >= 0.0)

    # River cells have HAND == 0
    assert np.all(hand[:, 2] == 0.0)

    # Ridge cells have HAND > 0 (height above valley floor)
    assert np.all(hand[:, 0] > 0.0)
    assert np.all(hand[:, 4] > 0.0)
    # Higher ridge has higher HAND than valley flank
    assert np.mean(hand[:, 0]) > np.mean(hand[:, 1])


def test_build_hand_city_preserves_v1_and_adds_v2():
    res = build_hand_for_city("delhi")
    assert res["city"] == "delhi"
    assert res["hand_stats"]["min_m"] >= 0.0
    assert "roads_closing_earlier_in_v2" in res
    assert "roads_closing_later_in_v2" in res
    assert res["citation"]["method"].startswith("Height Above Nearest Drainage")

    # Check city file has both v1 and v2
    import json
    from pathlib import Path
    city_file = Path("backend/data/cities/delhi.json")
    data = json.loads(city_file.read_text(encoding="utf-8"))
    roads = data["roads"]
    assert len(roads) > 0
    sample = roads[0]
    assert "flood_exposure" in sample  # v1 preserved
    assert "flood_exposure_v2" in sample  # v2 added
    assert "hand_m" in sample
    assert sample["hand_m"] >= 0.0


def test_hand_model_changes_closure_order_not_rule():
    from backend.geo.cities import activate, load_city, LEGACY
    try:
        activate("delhi")
        city = load_city("delhi")
        roads = city["roads"]
        assert any("flood_exposure_v2" in r for r in roads)

        # Comparing closures between v1 and v2 on same blockage
        from backend.services.ops_sim import roads_at
        r_v1 = roads_at(0.2, set(), exposure_model="distance")
        r_v2 = roads_at(0.2, set(), exposure_model="hand")
        closed_v1 = {r["road_id"] for r in r_v1 if r["blocked"]}
        closed_v2 = {r["road_id"] for r in r_v2 if r["blocked"]}
        # Topography reorders closures: roads with low HAND close earlier
        assert closed_v1 != closed_v2
    finally:
        activate(LEGACY)

