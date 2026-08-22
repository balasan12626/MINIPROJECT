from backend.simulation.engine import SCENARIOS, SimulationEngine


def test_scenarios_exist():
    assert "heavy_rainfall" in SCENARIOS
    assert "dam_overflow" in SCENARIOS


def test_evolve_is_monotonic_rain():
    eng = SimulationEngine()
    eng.params = {
        "scenario": "heavy_rainfall",
        "rainfall_intensity": 40,
        "dam_level": 198,
        "river_level": 204,
        "traffic": 0.4,
        "sos_count": 2,
        "road_blockage": 0.1,
    }
    eng.tick = 1
    a = eng._evolve()
    eng.tick = 12
    b = eng._evolve()
    assert b["weather"]["rainfall_mm"] > a["weather"]["rainfall_mm"]
    assert b["river"]["value_m"] > a["river"]["value_m"]
    assert b["dam"]["value_m"] > a["dam"]["value_m"]
