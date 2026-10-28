"""F33 — sensitivity analysis: zero range = zero effect, seeded, ranges + reasons listed."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("sens", ROOT / "scripts" / "sensitivity_ops.py")
sens = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sens)


def test_every_range_has_a_reason_and_skipped_ones_say_why():
    for k, (d, lo, hi, why) in sens.PARAMS.items():
        assert lo <= d <= hi and why
    assert all(v for v in sens.NOT_VARIED.values())


def test_zero_range_has_zero_effect_and_is_deterministic(monkeypatch):
    from backend.geo import cities

    monkeypatch.setitem(sens.PARAMS, "mobilise_s", (2.0, 2.0, 2.0, "zero range (test)"))
    out = sens.run(cities.LEGACY, runs=1, seed_=3, n_sos=4, surge=2, names=["mobilise_s", "ambulances"])
    row = next(r for r in out["tornado"] if r["parameter"] == "mobilise_s")
    assert row["effect_low_min"] == 0 and row["effect_high_min"] == 0
    again = sens.run(cities.LEGACY, runs=1, seed_=3, n_sos=4, surge=2, names=["mobilise_s", "ambulances"])
    strip = lambda o: json.dumps({k: v for k, v in o.items() if k != "code"}, sort_keys=True)  # noqa: E731
    assert strip(out) == strip(again)
    assert set(out["ranges"]) == set(sens.PARAMS)


def test_assumptions_are_restored_after_each_play():
    from backend.services import person_ops as po
    from backend.services import route_engine, seed

    caps = [s["capacity"] for s in seed.SHELTERS]
    with sens.applied({"speed_kmh": 10, "mobilise_s": 9, "shelter_capacity_factor": 0.1, "ambulances": 3}):
        assert route_engine.RESCUE_SPEED_KMH == 10 and len(po.ambulance_pool()) == 3
    assert route_engine.RESCUE_SPEED_KMH == 25.0 and po.MOBILISE_SECONDS == 2.0
    assert [s["capacity"] for s in seed.SHELTERS] == caps and po.ambulance_pool() == po.AMBULANCE_POOL
