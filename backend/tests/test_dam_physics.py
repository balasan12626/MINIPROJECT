"""Dam physics guards (audit phases 14-17).

Pins the corrected live-storage fill formula, the volumetric water balance,
and the FRL/spillway/overtopping behaviour.
"""

import pytest

from backend.data.dams import DAM_REGISTRY
from backend.services.dam_risk import fill_percentage, get_dam, threshold_levels, water_balance_projection


def _dam(dam_id: str) -> dict:
    return next(d for d in DAM_REGISTRY if d["id"] == dam_id)


@pytest.mark.parametrize("dam", DAM_REGISTRY, ids=[d["id"] for d in DAM_REGISTRY])
def test_every_dam_declares_units_and_dead_storage(dam):
    assert dam["level_unit"] == "m"
    assert dam["level_datum"] == "MSL"
    assert dam["dead_storage_level_m"] < dam["full_reservoir_level_m"]
    assert dam["effective_area_km2"] > 0


@pytest.mark.parametrize("dam", DAM_REGISTRY, ids=[d["id"] for d in DAM_REGISTRY])
def test_seed_levels_lie_inside_live_range(dam):
    """Every seeded level must be physically meaningful for its reservoir."""
    for field in ("current_level_m", "historical_normal_level_m"):
        assert dam["dead_storage_level_m"] <= dam[field] <= dam["full_reservoir_level_m"], field


def test_fill_uses_live_storage_not_absolute_elevation():
    dam = _dam("hirakud")
    dead = dam["dead_storage_level_m"]  # 179.832
    full = dam["full_reservoir_level_m"]  # 192.024
    # A level at the dead-storage floor is 0% usable, not 93% as level/FRL gave.
    assert fill_percentage(dead, full, dead) == 0.0
    assert fill_percentage(full, full, dead) == 100.0
    midpoint = dead + (full - dead) / 2
    assert fill_percentage(midpoint, full, dead) == pytest.approx(50.0, abs=0.05)


def test_fill_is_clamped_below_dead_storage():
    dam = _dam("hirakud")
    # The old registry value: far below dead storage, previously reported 76%.
    assert fill_percentage(146.0, dam["full_reservoir_level_m"], dam["dead_storage_level_m"]) == 0.0


def test_thresholds_interpolate_across_live_range():
    dam = _dam("bhakra")
    t = threshold_levels(dam["full_reservoir_level_m"], dam["dead_storage_level_m"])
    assert t["dead_storage"] < t["normal"] < t["warning"] < t["high_risk"] < t["critical"] <= t["full_reservoir"]


def test_water_balance_is_physically_plausible():
    """200 cumec net for 72 h must not raise a large reservoir by ~15 m."""
    dam = _dam("bhakra")
    out = water_balance_projection(
        dam,
        current_level_m=dam["current_level_m"],
        rainfall_mm=0.0,
        rainfall_intensity_mm_hr=0.0,
        inflow_cumec=1000.0,
        outflow_cumec=800.0,  # net +200 cumec
        capacity_override_m=None,
        forecast_hours=72,
    )
    rise = out["final_level_m"] - dam["current_level_m"]
    # 200 m3/s * 259200 s / 111.92e6 m2 = ~0.46 m
    assert 0.2 < rise < 1.0, f"implausible 72h rise of {rise:.2f} m"
    assert out["trend"] == "RISING"


def test_level_never_silently_exceeds_frl():
    dam = _dam("mettur")
    full = dam["full_reservoir_level_m"]
    out = water_balance_projection(
        dam,
        current_level_m=full - 0.05,
        rainfall_mm=500.0,
        rainfall_intensity_mm_hr=120.0,
        inflow_cumec=90000.0,
        outflow_cumec=100.0,
        capacity_override_m=None,
        forecast_hours=24,
    )
    assert max(p["predicted_level_m"] for p in out["series"]) <= full + 1e-6
    assert out["overtopping_risk"] is True
    assert out["reservoir_state"] == "OVERTOPPING_RISK"
    assert out["spillway_hours"] > 0


def test_public_dam_payload_exposes_units_and_dead_storage():
    row = get_dam("mettur")
    assert row["level_unit"] == "m"
    assert row["dead_storage_level_m"] == pytest.approx(219.456)
    assert 0.0 <= row["fill_percentage"] <= 100.0
