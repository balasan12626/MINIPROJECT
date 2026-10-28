"""F18 — live rainfall forecast: labelled, cached, never a silent fallback (HTTP mocked)."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.services import rain_forecast as rf
from backend.simulation.engine import SCENARIOS, SimulationEngine

T0 = datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc)


def _body(hours=72, mm=lambda i: float(i % 5)):
    times = [(T0.replace(hour=0) + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(hours)]
    return {"hourly": {"time": times, "precipitation": [mm(i) for i in range(hours)]}}


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _clear():
    rf._cache.clear()
    yield
    rf._cache.clear()


def test_fetch_is_labelled_and_cached():
    calls = []

    def ok(req):
        calls.append(req.url)
        return httpx.Response(200, json=_body())

    c = _client(ok)
    a = rf.fetch(28.6, 77.2, client=c, now=1000.0)
    assert a["source"] == "forecast (Open-Meteo)" and a["fetched_at"] and "Open-Meteo" in a["attribution"]
    assert a["cache"] == "miss" and len(a["hourly"]) == 72
    b = rf.fetch(28.6, 77.2, client=c, now=1000.0 + 60)
    assert b["cache"] == "hit" and len(calls) == 1, "a cache hit does not call the API"
    rf.fetch(28.6, 77.2, client=c, now=1000.0 + rf.CACHE_S + 1)
    assert len(calls) == 2, "expired after 30 min"


def test_failed_fetch_raises_never_falls_back():
    c = _client(lambda req: httpx.Response(502, text="bad gateway"))
    with pytest.raises(rf.ForecastUnavailable):
        rf.fetch(28.6, 77.2, client=c)


def test_hourly_to_tick_mapping_is_the_24h_sum_from_the_tick_time():
    fc = {**rf.fetch(28.6, 77.2, client=_client(lambda r: httpx.Response(200, json=_body()))), "cache": None}
    mm = [float(i % 5) for i in range(72)]
    v = rf.at_time(fc, T0)  # hour index 6
    assert v["rainfall_mm"] == pytest.approx(sum(mm[6:30]))
    assert v["rainfall_1h_mm"] == mm[6]
    assert v["daily"] == [pytest.approx(sum(mm[6:30])), pytest.approx(sum(mm[30:54])), pytest.approx(sum(mm[54:72]))]
    s = rf.series_for_run(fc, T0, ticks=40, sim_min_per_tick=4.0)
    assert s[15]["rainfall_mm"] == pytest.approx(sum(mm[7:31])), "tick 15 = 60 sim min later = next hour"


def test_run_with_forecast_uses_the_series_values_exactly():
    fc = rf.fetch(28.6, 77.2, client=_client(lambda r: httpx.Response(200, json=_body(mm=lambda i: 2.0 * i))))
    eng = SimulationEngine()
    eng.params = {**SCENARIOS["heavy_rainfall"]["defaults"], "scenario": "heavy_rainfall", "rain_source": "forecast", "tick_seconds": 2.0}
    eng.rain_forecast = fc
    eng.started_at = T0
    view = eng._rain_view()
    for t in (0, 5, 20):
        obs = eng._evolve(t)
        assert obs["weather"]["rainfall_mm"] == view["per_tick"][t]["rainfall_mm"]
        assert obs["weather"]["rain_source"] == "forecast"
    eng.params["rain_source"] = "scenario"
    assert eng._evolve(5)["weather"]["rain_source"] == "scenario" and eng._rain_view() is None


@pytest.mark.asyncio
async def test_start_endpoint_returns_503_and_keeps_the_old_run(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from backend.api import simulation as api
    from backend.main import app

    def boom(lat, lon):
        raise rf.ForecastUnavailable("Open-Meteo forecast unavailable (test)")

    monkeypatch.setattr(rf, "fetch", boom)
    eng = SimulationEngine()
    eng.run_id = "SIM-OLD"
    monkeypatch.setattr(api, "engine", eng)
    body = {**SCENARIOS["heavy_rainfall"]["defaults"], "scenario": "heavy_rainfall", "rain_source": "forecast"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/simulation/start", json=body)
    assert r.status_code == 503 and "not started" in r.json()["detail"]
    assert eng.run_id == "SIM-OLD"
