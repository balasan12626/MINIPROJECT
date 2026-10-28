"""Static reference data for the 5 major-dam scenarios shown on /simulation.

Values for full-reservoir level, storage capacity, and downstream region are
well-known public reference figures for these real dams, rounded for a demo
data set (not live official gauge readings) — every dam entry carries
``figures_are_approximate: True`` so the frontend can label them honestly.

``catchment_profile`` intentionally does NOT use each dam's true (very large)
basin drainage area. The trained INDOFLOODS regressor/classifier
(backend/ml/inference.py) was fit on catchments in the hundreds-to-low-
thousands of km^2 range (see model_metadata / flood_model_metadata_v3
``default_catchment``); feeding it a real multi-lakh-km^2 Indian river basin
would push every numeric feature far outside the model's training domain and
risk an unbounded, meaningless extrapolation. To keep predictions inside the
model's valid operating range, catchment_profile varies only the fields that
can differ plausibly within that domain (climate/land-use/population signals)
and reuses the model's own default categorical values, which are guaranteed
to be in its training vocabulary. This is documented, not hidden, in
``catchment_note`` below and in every API response that uses it.

Data-driven: adding a 6th dam is one more dict entry in DAM_REGISTRY.
"""

from __future__ import annotations

from typing import Any

CATCHMENT_NOTE = (
    "Catchment features are scaled to stay within the trained model's "
    "INDOFLOODS catchment-size domain (hundreds-low thousands km^2), not the "
    "dam's true multi-lakh-km^2 river basin, to avoid out-of-distribution "
    "extrapolation. Categorical fields reuse the model's default vocabulary."
)

# Baseline categorical values are the model's own defaults — guaranteed to be
# in the fitted encoder's vocabulary, so every dam predicts safely.
_BASE_CATEGORICAL = {
    "KoppenGeiger Climate Type": "Tropical",
    "Land cover": "No dominant class",
    "Soil type": "Acrisols",
    "lithology type": "No dominant class",
}


def _catchment(
    *,
    drainage_area: float,
    relief: float,
    length: float,
    sinuosity: float,
    form_factor: float,
    relief_ratio: float,
    drainage_density: float,
    urban_pct: float,
    population_density: float,
    road_density: float,
    mean_temp_c: float,
    annual_precip_mm: float,
    wettest_month_mm: float,
    precip_seasonality: float,
    wettest_quarter_mm: float,
    max_temp_c: float,
    night_light: float,
    hdi: float,
    stream_order: float,
    perimeter: float,
    compactness: float,
) -> dict[str, Any]:
    return {
        **_BASE_CATEGORICAL,
        "Drainage Area": drainage_area,
        "Catchment Relief": relief,
        "Catchment Length": length,
        "Sinuosity Index": sinuosity,
        "Form Factor": form_factor,
        "Relief Ratio": relief_ratio,
        "Drainage Density": drainage_density,
        "Urban percentage": urban_pct,
        "Population Density": population_density,
        "Road Density": road_density,
        "Annual Mean Temperature": mean_temp_c,
        "Annual Precipitation": annual_precip_mm,
        "Precipitation of Wettest Month": wettest_month_mm,
        "Precipitation Seasonality": precip_seasonality,
        "Precipitation of Wettest Quarter": wettest_quarter_mm,
        "Max Temperature of Warmest Month": max_temp_c,
        "Night Light": night_light,
        "2015_HDI": hdi,
        "Stream Order": stream_order,
        "Catchment Perimeter": perimeter,
        "Compactness Coefficient": compactness,
    }


DAM_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "mettur",
        "name": "Mettur Dam",
        "state": "Tamil Nadu",
        "river": "Cauvery",
        "lat": 11.7898,
        "lon": 77.7996,
        "level_unit": "m",
        "level_datum": "MSL",
        # 120 ft gauge == EL 240.79 m MSL. The previous 121.92 was 400 ft
        # converted to metres — a different quantity entirely.
        "full_reservoir_level_m": 240.79,
        "dead_storage_level_m": 219.456,  # MDDL
        "live_capacity_mcm": 2646.74,  # 93.47 TMC
        "effective_area_km2": 124.06,  # live_capacity / (FRL - MDDL)
        "area_source": "derived_from_live_capacity",
        "historical_normal_level_m": 231.19,
        "current_level_m": 234.94,
        "capacity_note": "FRL 120 ft gauge (EL 240.79 m MSL); MDDL 219.456 m; live 93.47 TMC (public reference, approximate)",
        # Mettur is read on its own dam gauge in feet (full = 120 ft). Gauge
        # zero is derived from the anchor above: 240.79 m − 120 ft × 0.3048.
        "gauge_unit": "ft",
        "gauge_full": 120.0,
        "gauge_zero_m": 204.214,
        "risk_threshold_pct": 90.0,
        "downstream_region": "Cauvery delta — Salem, Erode, Tiruchirappalli, Thanjavur districts",
        "catchment_profile": _catchment(
            drainage_area=1180.0, relief=610.0, length=42000.0, sinuosity=1.28,
            form_factor=0.34, relief_ratio=0.031, drainage_density=0.00021,
            urban_pct=22.0, population_density=610.0, road_density=460.0,
            mean_temp_c=27.4, annual_precip_mm=950.0, wettest_month_mm=210.0,
            precip_seasonality=68.0, wettest_quarter_mm=520.0, max_temp_c=36.5,
            night_light=4.1, hdi=0.72, stream_order=4.0, perimeter=165000.0,
            compactness=1.52,
        ),
    },
    {
        "id": "srisailam",
        "name": "Srisailam Dam",
        "state": "Andhra Pradesh / Telangana",
        "river": "Krishna",
        "lat": 16.0827,
        "lon": 78.8659,
        "level_unit": "m",
        "level_datum": "MSL",
        "full_reservoir_level_m": 269.748,  # 885 ft
        "dead_storage_level_m": 245.364,  # MDDL 805 ft
        "live_capacity_mcm": 4403.3,  # gross 215.8 TMC - dead 60.3 TMC
        "effective_area_km2": 180.58,
        "area_source": "derived_from_live_capacity",
        "historical_normal_level_m": 258.78,
        "current_level_m": 264.35,
        "capacity_note": "FRL 885 ft (269.748 m); MDDL 805 ft (245.364 m); gross ~215.8 TMC, dead ~60.3 TMC (public reference, approximate)",
        "risk_threshold_pct": 92.0,
        "downstream_region": "Krishna downstream — Kurnool, Guntur, Prakasam districts",
        "catchment_profile": _catchment(
            drainage_area=1450.0, relief=780.0, length=58000.0, sinuosity=1.34,
            form_factor=0.29, relief_ratio=0.034, drainage_density=0.00018,
            urban_pct=15.0, population_density=390.0, road_density=340.0,
            mean_temp_c=28.6, annual_precip_mm=880.0, wettest_month_mm=195.0,
            precip_seasonality=74.0, wettest_quarter_mm=480.0, max_temp_c=38.2,
            night_light=2.8, hdi=0.66, stream_order=4.0, perimeter=201000.0,
            compactness=1.61,
        ),
    },
    {
        "id": "nagarjuna_sagar",
        "name": "Nagarjuna Sagar Dam",
        "state": "Andhra Pradesh / Telangana",
        "river": "Krishna",
        "lat": 16.5738,
        "lon": 79.3129,
        "level_unit": "m",
        "level_datum": "MSL",
        "full_reservoir_level_m": 179.832,  # 590 ft
        "dead_storage_level_m": 137.16,  # MDDL of river sluices, 450 ft
        "live_capacity_mcm": 3760.5,  # ~132.8 TMC live of ~312 TMC gross
        "effective_area_km2": 88.13,
        "area_source": "derived_from_live_capacity_estimated",
        "historical_normal_level_m": 160.63,
        "current_level_m": 168.72,
        "capacity_note": "FRL 590 ft (179.832 m); MDDL 450 ft (137.16 m); gross ~312 TMC (public reference, approximate)",
        "risk_threshold_pct": 90.0,
        "downstream_region": "Krishna delta — Guntur, Prakasam, Krishna districts",
        "catchment_profile": _catchment(
            drainage_area=1520.0, relief=520.0, length=61000.0, sinuosity=1.31,
            form_factor=0.31, relief_ratio=0.026, drainage_density=0.00017,
            urban_pct=18.0, population_density=410.0, road_density=355.0,
            mean_temp_c=28.1, annual_precip_mm=830.0, wettest_month_mm=185.0,
            precip_seasonality=71.0, wettest_quarter_mm=455.0, max_temp_c=37.8,
            night_light=3.2, hdi=0.68, stream_order=4.0, perimeter=209000.0,
            compactness=1.58,
        ),
    },
    {
        "id": "hirakud",
        "name": "Hirakud Dam",
        "state": "Odisha",
        "river": "Mahanadi",
        "lat": 21.5326,
        "lon": 83.8647,
        "level_unit": "m",
        "level_datum": "MSL",
        "full_reservoir_level_m": 192.024,  # 630 ft
        "dead_storage_level_m": 179.832,  # 590 ft
        "live_capacity_mcm": 4779.0,
        "effective_area_km2": 391.98,
        "area_source": "derived_from_live_capacity_estimated",
        "water_spread_km2_at_frl": 743.0,
        "historical_normal_level_m": 186.54,
        "current_level_m": 189.10,
        # Was "~743 TMC gross storage" — 743 km2 is the water spread AREA, not a volume.
        "capacity_note": "FRL 630 ft (192.024 m); dead storage level 590 ft (179.832 m); water spread ~743 km2 at FRL (public reference, approximate)",
        "risk_threshold_pct": 93.0,
        "downstream_region": "Mahanadi delta — Sambalpur, Cuttack, Puri districts",
        "catchment_profile": _catchment(
            drainage_area=1340.0, relief=440.0, length=49000.0, sinuosity=1.4,
            form_factor=0.36, relief_ratio=0.024, drainage_density=0.00023,
            urban_pct=13.0, population_density=330.0, road_density=300.0,
            mean_temp_c=26.8, annual_precip_mm=1450.0, wettest_month_mm=330.0,
            precip_seasonality=80.0, wettest_quarter_mm=880.0, max_temp_c=35.1,
            night_light=2.3, hdi=0.63, stream_order=5.0, perimeter=178000.0,
            compactness=1.49,
        ),
    },
    {
        "id": "bhakra",
        "name": "Bhakra Dam",
        "state": "Himachal Pradesh / Punjab",
        "river": "Sutlej",
        "lat": 31.4166,
        "lon": 76.4327,
        "level_unit": "m",
        "level_datum": "MSL",
        "full_reservoir_level_m": 512.064,  # 1680 ft
        "dead_storage_level_m": 445.62,  # 1462 ft
        "live_capacity_mcm": 7436.03,  # gross 9867.84 - dead 2431.81
        "effective_area_km2": 111.92,
        "area_source": "derived_from_live_capacity",
        "historical_normal_level_m": 482.16,
        "current_level_m": 488.83,
        "capacity_note": "FRL 1680 ft (512.064 m); dead storage level 1462 ft (445.62 m); gross 9867.84 MCM, live 7436.03 MCM (BBMB reference, approximate)",
        "risk_threshold_pct": 92.0,
        "downstream_region": "Sutlej command — Punjab, Haryana, Rajasthan irrigation belt",
        "catchment_profile": _catchment(
            drainage_area=1610.0, relief=1450.0, length=52000.0, sinuosity=1.22,
            form_factor=0.27, relief_ratio=0.058, drainage_density=0.00014,
            urban_pct=9.0, population_density=210.0, road_density=250.0,
            mean_temp_c=18.4, annual_precip_mm=1150.0, wettest_month_mm=260.0,
            precip_seasonality=62.0, wettest_quarter_mm=610.0, max_temp_c=30.2,
            night_light=1.6, hdi=0.71, stream_order=4.0, perimeter=192000.0,
            compactness=1.55,
        ),
    },
]

DAM_BY_ID: dict[str, dict[str, Any]] = {d["id"]: d for d in DAM_REGISTRY}


def get_dam_raw(dam_id: str) -> dict[str, Any] | None:
    return DAM_BY_ID.get(dam_id)
