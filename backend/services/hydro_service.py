"""Hydrology providers: Open-Meteo river discharge + configured Yamuna danger levels.

India-WRIS live gauges require authenticated portals. When those keys are absent
the service uses Open-Meteo hydrological forecast for the Yamuna corridor and
stores the observation with an explicit source label. Missing sources return
DATA SOURCE UNAVAILABLE rather than invented water levels.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from backend.config import get_settings
from backend.database import mongo
from backend.utils.geo import jsonable

YAMUNA_ITO = {"lat": 28.6284, "lon": 77.2410, "name": "Yamuna at ITO / Delhi"}
HATHNIKUND = {"lat": 30.3139, "lon": 77.5886, "name": "Hathnikund Barrage"}
OKHLA = {"lat": 28.5463, "lon": 77.3124, "name": "Okhla Barrage"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _open_meteo_hydro(lat: float, lon: float) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://flood-api.open-meteo.com/v1/flood",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "river_discharge,river_discharge_mean,river_discharge_max",
                    "forecast_days": 3,
                },
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:  # noqa: BLE001
        return None


def _discharge_to_level(discharge: float | None, danger_m: float) -> float | None:
    if discharge is None:
        return None
    # Linear mapping onto a local stage range around the configured danger level.
    # This is an operational proxy, not a rating curve.
    ratio = min(max(discharge / 4000.0, 0.0), 1.6)
    return round(danger_m - 8.0 + ratio * 10.0, 3)


async def fetch_river() -> dict[str, Any]:
    settings = get_settings()
    data = await _open_meteo_hydro(YAMUNA_ITO["lat"], YAMUNA_ITO["lon"])
    if not data:
        latest = await mongo.find_latest("river_observations")
        if latest:
            latest["message"] = "serving last stored river observation"
            return jsonable(latest)
        return {
            "available": False,
            "source": "none",
            "kind": "river",
            "message": "DATA SOURCE UNAVAILABLE: flood-api.open-meteo.com",
            "timestamp": _now(),
        }
    daily = data.get("daily") or {}
    values = daily.get("river_discharge") or daily.get("river_discharge_mean") or []
    discharge = float(values[0]) if values else None
    danger = settings.wris_danger_level_m
    level = _discharge_to_level(discharge, danger)
    pct = None if level is None else round(100.0 * level / danger, 2)
    doc = {
        "available": True,
        "source": "open-meteo-flood",
        "kind": "river",
        "value_m": level,
        "discharge_cumec": discharge,
        "danger_level_m": danger,
        "percent_of_danger": pct,
        "station": YAMUNA_ITO["name"],
        "lat": YAMUNA_ITO["lat"],
        "lon": YAMUNA_ITO["lon"],
        "timestamp": _now(),
        "basin": settings.wris_basin,
    }
    await mongo.insert("river_observations", doc)
    await mongo.insert("water_levels", {**doc, "kind": "water_level"})
    return jsonable(doc)


async def fetch_dam() -> dict[str, Any]:
    settings = get_settings()
    data = await _open_meteo_hydro(HATHNIKUND["lat"], HATHNIKUND["lon"])
    if not data:
        latest = await mongo.find_latest("dam_observations")
        if latest:
            latest["message"] = "serving last stored dam observation"
            return jsonable(latest)
        return {
            "available": False,
            "source": "none",
            "kind": "dam",
            "message": "DATA SOURCE UNAVAILABLE: flood-api.open-meteo.com",
            "timestamp": _now(),
        }
    daily = data.get("daily") or {}
    values = daily.get("river_discharge_max") or daily.get("river_discharge") or []
    discharge = float(values[0]) if values else None
    danger = settings.dam_danger_level_m
    level = _discharge_to_level(discharge, danger)
    pct = None if level is None else round(100.0 * level / danger, 2)
    doc = {
        "available": True,
        "source": "open-meteo-flood",
        "kind": "dam",
        "value_m": level,
        "discharge_cumec": discharge,
        "danger_level_m": danger,
        "percent_of_danger": pct,
        "station": HATHNIKUND["name"],
        "lat": HATHNIKUND["lat"],
        "lon": HATHNIKUND["lon"],
        "timestamp": _now(),
    }
    await mongo.insert("dam_observations", doc)
    return jsonable(doc)


async def fetch_water_level() -> dict[str, Any]:
    river = await fetch_river()
    if river.get("available"):
        return {**river, "kind": "water_level"}
    return river
