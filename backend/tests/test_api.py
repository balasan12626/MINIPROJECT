import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["backend"] == "connected"


@pytest.mark.asyncio
async def test_policy_and_scenarios():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        pol = await client.get("/api/policy")
        assert pol.status_code == 200
        sc = await client.get("/api/simulation/scenarios")
        assert sc.status_code == 200
        assert len(sc.json()["scenarios"]) >= 5


@pytest.mark.asyncio
async def test_predict_with_rainfall():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/ml/predict", json={"rainfall_24h_mm": 80, "forecast_daily_mm": [40, 30, 20], "month": 7})
        assert resp.status_code == 200
        body = resp.json()
        assert "available" in body
        if body.get("available"):
            assert 0 <= body["flood_probability"] <= 1
            assert body["risk_category"] in {"LOW", "MODERATE", "HIGH", "CRITICAL"}


@pytest.mark.asyncio
async def test_sources_and_clusters():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        src = await client.get("/api/sources")
        assert src.status_code == 200
        ids = {s["id"] for s in src.json()["live_apis"]}
        assert {"openweather", "open-meteo", "open-meteo-flood", "openstreetmap", "mongodb", "groq"} <= ids
        cl = await client.get("/api/emergency/clusters")
        assert cl.status_code == 200
        body = cl.json()
        assert body["algorithm"] == "kmeans"
        assert "clusters" in body
        talk = await client.get("/api/agents/conversation?mode=simulation")
        assert talk.status_code == 200
        assert "turns" in talk.json() or "history" in talk.json()
        explain = await client.get("/api/ml/explain?rainfall_24h_mm=80")
        assert explain.status_code == 200
        pdf = await client.get("/api/simulation/report.pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"].startswith("application/pdf")
