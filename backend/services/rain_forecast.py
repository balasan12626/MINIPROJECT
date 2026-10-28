"""F18 — live rainfall forecast per city (Open-Meteo, free, no key).

A FORECAST, not an observation: every value carries `source` and `fetched_at`.
A failed fetch raises `ForecastUnavailable` — the run refuses to start rather
than silently falling back to the scenario's number.

Units: the engine's `rainfall_mm` is a 24-hour rainfall total (the scenario
presets and the ML models use it that way). At a tick whose simulated time is
T, the forecast-driven value is the SUM of the forecast hourly precipitation
over [T, T + 24 h); `rainfall_1h_mm` is the forecast for the hour containing T.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 8.0
CACHE_S = 30 * 60
SOURCE = "forecast (Open-Meteo)"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

_cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}


class ForecastUnavailable(RuntimeError):
    pass


def _key(lat: float, lon: float) -> tuple[float, float]:
    return round(float(lat), 3), round(float(lon), 3)


def fetch(lat: float, lon: float, client: httpx.Client | None = None, now: float | None = None) -> dict[str, Any]:
    """Hourly precipitation for the next 3 days at (lat, lon); cached 30 min."""
    k = _key(lat, lon)
    now = time.time() if now is None else now
    hit = _cache.get(k)
    if hit and now - hit[0] < CACHE_S:
        return {**hit[1], "cache": "hit"}
    params = {"latitude": k[0], "longitude": k[1], "hourly": "precipitation", "forecast_days": 3, "timezone": "UTC"}
    try:
        c = client or httpx.Client(timeout=TIMEOUT_S)
        try:
            r = c.get(URL, params=params)
        finally:
            if client is None:
                c.close()
        r.raise_for_status()
        body = r.json()
        times = body["hourly"]["time"]
        mm = body["hourly"]["precipitation"]
    except Exception as e:  # noqa: BLE001 — any failure = no forecast, said out loud
        raise ForecastUnavailable(f"Open-Meteo forecast unavailable for {k[0]}, {k[1]}: {str(e)[:160]}") from None
    hourly = [
        {"time": datetime.fromisoformat(t).replace(tzinfo=timezone.utc).isoformat(), "mm": float(v or 0.0)}
        for t, v in zip(times, mm)
    ]
    out = {
        "source": SOURCE,
        "attribution": ATTRIBUTION,
        "lat": k[0],
        "lon": k[1],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "url": f"{URL}?latitude={k[0]}&longitude={k[1]}&hourly=precipitation&forecast_days=3",
        "hourly": hourly,
    }
    _cache[k] = (now, out)
    return {**out, "cache": "miss"}


def _hour_index(fc: dict[str, Any], at: datetime) -> int:
    hours = [datetime.fromisoformat(h["time"]) for h in fc["hourly"]]
    i = 0
    for j, h in enumerate(hours):
        if h <= at:
            i = j
    return i


def at_time(fc: dict[str, Any], at: datetime) -> dict[str, float]:
    """24-h total from `at`, the hour's own value, and the next 3 daily totals."""
    i = _hour_index(fc, at)
    mm = [h["mm"] for h in fc["hourly"]]
    day = lambda a: round(sum(mm[a:a + 24]), 2)  # noqa: E731
    return {
        "rainfall_mm": day(i),
        "rainfall_1h_mm": round(mm[i] if i < len(mm) else 0.0, 2),
        "daily": [day(i), day(i + 24), day(i + 48)],
        "hours_available": max(0, len(mm) - i),
    }


def series_for_run(fc: dict[str, Any], start: datetime, ticks: int, sim_min_per_tick: float) -> list[dict[str, Any]]:
    """The exact value each tick of the run uses (served in state for the chart)."""
    out = []
    for t in range(ticks):
        at = start + timedelta(minutes=t * sim_min_per_tick)
        v = at_time(fc, at)
        out.append({"tick": t, "sim_time": at.isoformat(), "rainfall_mm": v["rainfall_mm"], "rainfall_1h_mm": v["rainfall_1h_mm"]})
    return out
