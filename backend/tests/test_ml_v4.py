"""V4 CAMELS-IND forecaster: live benchmark, gauge list and replay endpoints."""

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.ml.inference import models_dir

V4_READY = all((models_dir() / n).exists() for n in
               ("flood_forecast_v4.pkl", "flood_test_unseen_v4.npz", "flood_evaluation_v4.json"))
pytestmark = pytest.mark.skipif(not V4_READY, reason="v4 artifacts not trained")


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_benchmark_v4_is_recomputed_from_the_test_set():
    async with await _client() as client:
        body = (await client.get("/api/ml/benchmark-v4")).json()
    assert body["available"] is True
    t = body["live_test"]
    # confusion matrix must add up to the stored unseen-gauge test set
    n = len(np.load(models_dir() / "flood_test_unseen_v4.npz")["y"])
    assert t["tp"] + t["fp"] + t["tn"] + t["fn"] == t["n"] == n
    assert t["accuracy"] == pytest.approx((t["tp"] + t["tn"]) / n)
    assert body["fit_check"]["verdict"] in {"BALANCED", "OVERFIT", "UNDERFIT"}


@pytest.mark.asyncio
async def test_replay_returns_prediction_outcome_and_shap():
    async with await _client() as client:
        gauges = (await client.get("/api/ml/v4/gauges")).json()
        assert gauges["available"] and gauges["gauges"]
        gid = gauges["gauges"][0]["gauge_id"]
        out = (await client.post("/api/ml/predict-v4", json={"gauge_id": gid})).json()
    assert out["available"] is True and out["mode"] == "HISTORICAL_REPLAY"
    assert 0.0 <= out["flood_probability"] <= 1.0
    assert out["predicted_flood_within_3d"] == (out["flood_probability"] >= out["decision_threshold"])
    assert out["gauge_seen_in_training"] is False
    if out["explanation"]:
        assert len(out["explanation"]["top"]) > 0


@pytest.mark.asyncio
async def test_replay_rejects_bad_input():
    async with await _client() as client:
        bad_date = await client.post("/api/ml/predict-v4", json={"gauge_id": 3017, "date": "17-10-2017"})
        unknown = (await client.post("/api/ml/predict-v4", json={"gauge_id": 999999})).json()
    assert bad_date.status_code == 422
    assert unknown["available"] is False
