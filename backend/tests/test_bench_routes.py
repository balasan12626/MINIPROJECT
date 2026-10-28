"""F6 — route-choice benchmark: deterministic, honest ordering, no blocked roads used."""
import importlib.util
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("bench_routes", ROOT / "scripts" / "bench_routes.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

LEVELS = [0.0, 0.3]


@pytest.fixture(scope="module")
def tiny():
    return bench.run(trips=5, seed=11, levels=LEVELS)


def test_same_seed_gives_identical_json(tiny):
    again, _ = bench.run(trips=5, seed=11, levels=LEVELS)
    assert json.dumps(tiny[0], sort_keys=True) == json.dumps(again, sort_keys=True)
    other, _ = bench.run(trips=5, seed=12, levels=LEVELS)
    assert other["trips"] != tiny[0]["trips"]


def test_exhaustive_is_never_worse_than_qaoa_or_dijkstra(tiny):
    for lv in tiny[0]["levels"]:
        for r in lv["per_trip"]:
            if r.get("unreachable"):
                continue
            ex = r["exhaustive"]["cost"]
            assert ex <= r["qaoa"]["cost"] + 1e-9
            assert ex <= r["dijkstra"]["cost"] + 1e-9
            assert r["qaoa_matches_exhaustive"] == (r["qaoa"]["index"] == r["exhaustive"]["index"])


def test_blocked_roads_never_appear_in_a_chosen_path(tiny):
    for lv in tiny[0]["levels"]:
        closed = set(lv["roads_closed"])
        for r in lv["per_trip"]:
            for m in ("dijkstra", "qaoa", "exhaustive"):
                if m in r:
                    assert not closed & set(r[m]["road_ids"]), (lv["blockage"], m, r["trip"])


def test_json_has_the_documented_keys(tiny):
    result, timing = tiny
    assert result["synthetic_trips"] is True
    for k in ("trips", "seed", "blockage_levels", "candidates_k", "qaoa_layers", "qaoa_shots", "qaoa_penalty"):
        assert k in result["settings"]
    assert "commit" in result["code"]
    lv = result["levels"][0]
    for k in ("blockage", "routed", "no_open_road", "same_junction", "qaoa_equals_exhaustive_pct", "qaoa_equals_dijkstra_pct", "methods"):
        assert k in lv
    assert set(lv["methods"]) == {"dijkstra", "qaoa", "exhaustive", "direct"}
    for k in ("mean", "median", "p95"):
        assert k in lv["methods"]["qaoa"]["travel_min"]
    assert "hazard" in lv["methods"]["qaoa"] and "hazard" not in lv["methods"]["direct"]
    assert [t["blockage"] for t in timing["levels"]] == LEVELS
    # more blockage never routes MORE trips
    assert result["levels"][1]["routed"] <= result["levels"][0]["routed"]


@pytest.mark.asyncio
async def test_endpoint_serves_file_or_404(tmp_path, monkeypatch):
    from backend.api import benchmark as api
    from backend.main import app

    monkeypatch.setattr(api, "RESULT", tmp_path / "missing.json")
    monkeypatch.setattr(api, "TIMING", tmp_path / "missing.timing.json")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/benchmark/routes")
        assert r.status_code == 404 and "bench_routes.py" in r.json()["detail"]
        result, _ = bench.run(trips=3, seed=1, levels=[0.0])
        path = tmp_path / "rb.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        monkeypatch.setattr(api, "RESULT", path)
        body = (await c.get("/api/benchmark/routes")).json()
        assert body["levels"][0]["blockage"] == 0.0 and "per_trip" not in body["levels"][0]
        assert (await c.get("/api/benchmark/routes", params={"details": True})).json()["levels"][0]["per_trip"]
