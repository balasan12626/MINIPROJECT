import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_list_dams():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dams")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert len(body["dams"]) == 5
        for dam in body["dams"]:
            assert 0 <= dam["fill_percentage"] <= 200
            assert dam["status"] in {"LOW", "MODERATE", "HIGH", "VERY_HIGH", "CRITICAL"}
            assert dam["figures_are_approximate"] is True


@pytest.mark.asyncio
async def test_dam_detail_and_percentage_math():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dams/mettur")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "mettur"
        # Live-storage fill: levels are absolute elevations (m MSL), so the
        # usable fraction is measured from the dead-storage level, not from 0.
        dead = body["dead_storage_level_m"]
        full = body["full_reservoir_level_m"]
        expected_pct = round((body["current_level_m"] - dead) / (full - dead) * 100.0, 2)
        assert body["fill_percentage"] == expected_pct
        assert body["status_box"]["calculation"] == (
            "fill_percentage = (current_level_m - dead_storage_level_m) / "
            "(full_reservoir_level_m - dead_storage_level_m) * 100"
        )


@pytest.mark.asyncio
async def test_unknown_dam_id_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dams/not-a-real-dam")
        assert resp.status_code == 404
        resp2 = await client.get("/api/dams/not-a-real-dam/history")
        assert resp2.status_code == 404
        resp3 = await client.post("/api/simulation/run", json={"dam_id": "not-a-real-dam"})
        assert resp3.status_code == 404
        resp4 = await client.post("/api/prediction/dam-risk", json={"dam_id": "not-a-real-dam"})
        assert resp4.status_code == 404


@pytest.mark.asyncio
async def test_dam_history():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dams/bhakra/history?days=7")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data_source"] == "simulated_history"
        assert len(body["points"]) == 8


@pytest.mark.asyncio
async def test_run_simulation_normal_scenario():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/simulation/run",
            json={"dam_id": "hirakud", "scenario": "normal", "forecast_hours": 24},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["scenario"]["id"] == "normal"
        assert len(body["projection"]["series"]) == 25
        assert body["status_box"]["data_source"] == "calculated"
        assert body["risk_engine"]["risk"] in {"LOW", "MODERATE", "HIGH", "VERY_HIGH", "CRITICAL"}
        assert "main_drivers" in body["risk_engine"]


@pytest.mark.asyncio
async def test_run_simulation_worst_case_raises_risk():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        normal = await client.post(
            "/api/simulation/run", json={"dam_id": "srisailam", "scenario": "normal", "forecast_hours": 48}
        )
        worst = await client.post(
            "/api/simulation/run", json={"dam_id": "srisailam", "scenario": "worst_case", "forecast_hours": 48}
        )
        assert normal.status_code == 200 and worst.status_code == 200
        n_score = normal.json()["risk_engine"]["composite_score"]
        w_score = worst.json()["risk_engine"]["composite_score"]
        assert w_score >= n_score


@pytest.mark.asyncio
async def test_invalid_inputs_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        neg_level = await client.post(
            "/api/simulation/run", json={"dam_id": "mettur", "current_level_m": -5}
        )
        assert neg_level.status_code == 422
        zero_capacity = await client.post(
            "/api/simulation/run", json={"dam_id": "mettur", "capacity_override_m": 0}
        )
        assert zero_capacity.status_code == 422
        bad_scenario = await client.post(
            "/api/simulation/run", json={"dam_id": "mettur", "scenario": "made_up"}
        )
        assert bad_scenario.status_code == 400


@pytest.mark.asyncio
async def test_dam_risk_prediction_box_is_independent_of_status():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/prediction/dam-risk",
            json={"dam_id": "nagarjuna_sagar", "rainfall_24h_mm": 80, "month": 7},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data_source"] == "ml_model"
        if body.get("available"):
            assert "probability_severe" in body
            assert "model_evaluation" in body
