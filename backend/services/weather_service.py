from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from backend.config import get_settings
from backend.database import mongo
from backend.utils.geo import jsonable

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
OPENWEATHER = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"
TOMORROW = "https://api.tomorrow.io/v4/weather/realtime"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def fetch_current() -> dict[str, Any]:
    settings = get_settings()
    lat, lon = settings.city_lat, settings.city_lon
    errors: list[str] = []

    ow_key = settings.openweather_key
    if ow_key:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    OPENWEATHER,
                    params={"lat": lat, "lon": lon, "appid": ow_key, "units": "metric"},
                )
                resp.raise_for_status()
                data = resp.json()
            rain = 0.0
            if isinstance(data.get("rain"), dict):
                rain = float(data["rain"].get("1h") or data["rain"].get("3h") or 0.0)
            doc = {
                "available": True,
                "source": "openweather",
                "temperature_c": data.get("main", {}).get("temp"),
                "rainfall_mm": rain,
                "rainfall_1h_mm": rain,
                "humidity_pct": data.get("main", {}).get("humidity"),
                "wind_mps": data.get("wind", {}).get("speed"),
                "pressure_hpa": data.get("main", {}).get("pressure"),
                "description": (data.get("weather") or [{}])[0].get("description"),
                "lat": lat,
                "lon": lon,
                "timestamp": _now(),
                "raw_id": data.get("id"),
            }
            await mongo.insert("weather_observations", doc)
            await mongo.insert(
                "rainfall_observations",
                {"value_mm": rain, "source": "openweather", "lat": lat, "lon": lon, "timestamp": _now()},
            )
            return jsonable(doc)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"openweather: {exc}")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                OPEN_METEO,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,precipitation,pressure_msl,wind_speed_10m",
                    "hourly": "precipitation",
                    "timezone": "UTC",
                    "forecast_days": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        current = data.get("current") or {}
        rain = float(current.get("precipitation") or 0.0)
        hourly = data.get("hourly") or {}
        rains = hourly.get("precipitation") or []
        rain_24 = float(sum(rains[-24:])) if rains else rain
        doc = {
            "available": True,
            "source": "open-meteo",
            "temperature_c": current.get("temperature_2m"),
            "rainfall_mm": rain_24,
            "rainfall_1h_mm": rain,
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_mps": current.get("wind_speed_10m"),
            "pressure_hpa": current.get("pressure_msl"),
            "description": "open-meteo current",
            "lat": lat,
            "lon": lon,
            "timestamp": _now(),
        }
        await mongo.insert("weather_observations", doc)
        await mongo.insert(
            "rainfall_observations",
            {"value_mm": rain_24, "source": "open-meteo", "lat": lat, "lon": lon, "timestamp": _now()},
        )
        return jsonable(doc)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"open-meteo: {exc}")

    latest = await mongo.find_latest("weather_observations")
    if latest:
        latest["available"] = True
        latest["message"] = "serving last stored observation; live APIs failed"
        latest["source"] = f"{latest.get('source', 'cache')}-cache"
        return jsonable(latest)

    return jsonable({
        "available": False,
        "source": "none",
        "message": "DATA SOURCE UNAVAILABLE: " + "; ".join(errors),
        "timestamp": _now(),
    })


async def fetch_forecast() -> dict[str, Any]:
    settings = get_settings()
    lat, lon = settings.city_lat, settings.city_lon
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                OPEN_METEO,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "precipitation_sum,temperature_2m_max,relative_humidity_2m_mean",
                    "timezone": "UTC",
                    "forecast_days": 10,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        items = []
        for i, day in enumerate(times):
            items.append(
                {
                    "timestamp": datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
                    "temperature_c": (daily.get("temperature_2m_max") or [None])[i] if i < len(daily.get("temperature_2m_max") or []) else None,
                    "rainfall_mm": (daily.get("precipitation_sum") or [None])[i] if i < len(daily.get("precipitation_sum") or []) else None,
                    "humidity_pct": (daily.get("relative_humidity_2m_mean") or [None])[i] if i < len(daily.get("relative_humidity_2m_mean") or []) else None,
                    "description": "daily forecast",
                }
            )
        return jsonable({"available": True, "source": "open-meteo", "items": items, "message": None})
    except Exception as exc:  # noqa: BLE001
        ow_key = settings.openweather_key
        if ow_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        OPENWEATHER_FORECAST,
                        params={"lat": lat, "lon": lon, "appid": ow_key, "units": "metric"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                items = []
                for row in data.get("list", [])[:16]:
                    rain = 0.0
                    if isinstance(row.get("rain"), dict):
                        rain = float(row["rain"].get("3h") or 0)
                    items.append(
                        {
                            "timestamp": datetime.fromtimestamp(row["dt"], tz=timezone.utc),
                            "temperature_c": row.get("main", {}).get("temp"),
                            "rainfall_mm": rain,
                            "humidity_pct": row.get("main", {}).get("humidity"),
                            "description": (row.get("weather") or [{}])[0].get("description"),
                        }
                    )
                return {"available": True, "source": "openweather", "items": items, "message": None}
            except Exception as exc2:  # noqa: BLE001
                return {
                    "available": False,
                    "source": "none",
                    "items": [],
                    "message": f"DATA SOURCE UNAVAILABLE: {exc}; {exc2}",
                }
        return {"available": False, "source": "none", "items": [], "message": f"DATA SOURCE UNAVAILABLE: {exc}"}


async def rainfall_24h_and_forecast() -> tuple[float | None, list[float], dict[str, Any]]:
    current = await fetch_current()
    forecast = await fetch_forecast()
    rain_24 = None
    if current.get("available"):
        rain_24 = float(current.get("rainfall_mm") or current.get("rainfall_1h_mm") or 0.0)
        if current.get("source") == "openweather":
            try:
                settings = get_settings()
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        OPEN_METEO,
                        params={
                            "latitude": settings.city_lat,
                            "longitude": settings.city_lon,
                            "hourly": "precipitation",
                            "past_days": 1,
                            "forecast_days": 1,
                            "timezone": "UTC",
                        },
                    )
                    if resp.status_code == 200:
                        rains = (resp.json().get("hourly") or {}).get("precipitation") or []
                        if rains:
                            rain_24 = float(sum(rains[:24])) if len(rains) >= 24 else float(sum(rains))
                            current["rainfall_mm"] = rain_24
                            current["source"] = "openweather+open-meteo-precip"
            except Exception:  # noqa: BLE001
                pass
    daily = []
    if forecast.get("available"):
        daily = [float(x.get("rainfall_mm") or 0.0) for x in forecast.get("items") or []]
    return rain_24, daily, {"current": current, "forecast": forecast}
