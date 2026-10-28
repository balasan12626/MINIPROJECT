"""F12 — headless Monte-Carlo ops evaluation: deterministic, paired, honest labels."""
import importlib.util
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.geo import cities
from backend.services import person_ops as po

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("mc", ROOT / "scripts" / "monte_carlo_ops.py")
mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mc)


@pytest.fixture(scope="module")
def tiny():
    out = mc.run(cities.LEGACY, runs=2, seed_=3, n_sos=5, surge=2, policies=["first_free", "greedy", "optimal"])
    yield out
    cities.activate(cities.LEGACY)


def test_same_seed_same_result(tiny):
    again = mc.run(cities.LEGACY, runs=2, seed_=3, n_sos=5, surge=2, policies=["first_free", "greedy", "optimal"])
    strip = lambda r: {k: v for k, v in r.items() if k != "code"}  # noqa: E731
    assert json.dumps(strip(tiny[0]), sort_keys=True) == json.dumps(strip(again[0]), sort_keys=True)
    assert po.ROUTE_CHOOSER == "qaoa", "the live chooser is restored after a batch run"


def test_every_policy_replays_the_same_people_and_reports_honestly(tiny):
    res, timing = tiny
    people = {name: s["people"] for name, s in res["summary"].items()}
    assert len(set(people.values())) == 1 and people["first_free"] == 2 * 7
    for s in res["summary"].values():
        assert s["served"] + s["censored"] == s["people"]
        assert set(s["time_to_safety_min"]) == {"n", "mean", "p50", "p90"}
    assert set(res["paired_vs_first_free"]) == {"greedy", "optimal"}
    assert res["synthetic"] is True and res["settings"]["route_chooser"].startswith("dijkstra")
    assert set(timing["seconds_per_policy"]) == {"first_free", "greedy", "optimal"}


@pytest.mark.asyncio
async def test_ops_endpoint(tmp_path, monkeypatch, tiny):
    from backend.api import benchmark as api
    from backend.main import app

    monkeypatch.setattr(api, "MODELS", tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/benchmark/ops")).status_code == 404
        (tmp_path / "ops_montecarlo_v1_testcity.json").write_text(json.dumps(tiny[0]), encoding="utf-8")
        body = (await c.get("/api/benchmark/ops")).json()
        assert body["available_cities"] == ["testcity"] and "summary" in body
        assert (await c.get("/api/benchmark/ops", params={"city": "nowhere"})).status_code == 404
