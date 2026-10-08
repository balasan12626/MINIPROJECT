"""One-source-per-value guards (region dam, reservoir peak, optimisation, radio grounding)."""

from backend.agents.dialogue import grounded
from backend.api.dams import evacuation_region, region_dam
from backend.data.dams import get_dam_raw
from backend.services import dam_risk
from backend.simulation.engine import compare_optimization


def test_region_dam_is_nearest_registry_dam_to_the_flood_region():
    region = evacuation_region()
    assert region["river"] == "Yamuna"
    picked = region_dam(dam_risk.list_dams(), region)
    # Computed by haversine from seed ZONES, not hard-coded, and not Mettur (Tamil Nadu).
    assert picked["dam_id"] == "bhakra"
    assert picked["same_river"] is False


def test_projection_peak_is_the_series_max_not_the_final_level():
    dam = get_dam_raw("bhakra")
    proj = dam_risk.water_balance_projection(
        dam, current_level_m=None, capacity_override_m=None, rainfall_mm=60, rainfall_intensity_mm_hr=12, inflow_cumec=1400, outflow_cumec=2400, forecast_hours=48
    )
    levels = [r["predicted_level_m"] for r in proj["series"]]
    assert proj["peak_level_m"] == max(levels)
    assert proj["peak_level_m"] >= proj["final_level_m"]


def test_worse_optimisation_keeps_baseline():
    before = {"solution_cost": 10.0, "constraint_violations": 0}
    worse = {"solution_cost": 12.0, "constraint_violations": 0}
    better = {"solution_cost": 9.0, "constraint_violations": 0}
    rejected = compare_optimization(before, worse)
    assert rejected["status"] == "rejected" and rejected["plan"] is before and "rejected" in rejected["label"]
    accepted = compare_optimization(before, better)
    assert accepted["status"] == "accepted" and accepted["plan"] is better


def test_radio_numbers_must_trace_to_current_state():
    facts = "FACTS: flood probability 73.4%; rain 55 mm; Yamuna river level 204.6 m; time now 18:05 IST"
    assert grounded([{"text": "P is 73% with 55 mm of rain at 18:05."}], facts)
    assert not grounded([{"text": "Three boats, 12 km out, P 91.9%."}], facts)
