from pathlib import Path

from backend.ml.inference import predict_live
from backend.ml.risk_engine import operational_risk
from backend.services.sos_cluster import cluster_emergencies
from backend.utils.geo import jsonable


def test_operational_risk_increases_with_rain():
    dry = operational_risk(0.6, 8, 50, 50)
    mid = operational_risk(0.6, 40, 80, 80)
    wet = operational_risk(0.6, 90, 100, 100)
    assert dry["flood_probability"] < mid["flood_probability"] < wet["flood_probability"]
    assert dry["flood_probability"] < 0.50
    assert wet["flood_probability"] >= 0.60



def test_inference_if_model_present():
    if not (Path("models") / "random_forest_flood.pkl").exists() and not (Path("models") / "xgboost_flood.pkl").exists():
        return
    dry = predict_live(5.0, [2, 1, 0], month=1)
    wet = predict_live(180.0, [90, 70, 40], month=7)
    assert dry.get("available") is True
    assert wet.get("available") is True
    assert 0 <= dry["flood_probability"] <= 1
    assert 0 <= wet["flood_probability"] <= 1
    assert dry["model_id"]
    assert wet["inference_latency_ms"] is not None


def test_jsonable_objectid_and_datetime():
    class ObjectId:
        def __str__(self):
            return "abc123"

    from datetime import datetime, timezone

    out = jsonable({"_id": ObjectId(), "when": datetime(2026, 8, 19, tzinfo=timezone.utc), "nested": [ObjectId()]})
    assert out["_id"] == "abc123"
    assert isinstance(out["when"], str)
    assert out["nested"] == ["abc123"]


def test_kmeans_clusters_many_sos():
    teams = [
        {"team_id": "T1", "name": "North", "lat": 28.70, "lon": 77.20, "status": "AVAILABLE"},
        {"team_id": "T2", "name": "East", "lat": 28.62, "lon": 77.28, "status": "AVAILABLE"},
    ]
    sos = [
        {"_id": "a", "lat": 28.701, "lon": 77.201, "people": 2, "status": "open"},
        {"_id": "b", "lat": 28.702, "lon": 77.199, "people": 3, "status": "open"},
        {"_id": "c", "lat": 28.621, "lon": 77.279, "people": 4, "status": "open"},
        {"_id": "d", "lat": 28.619, "lon": 77.281, "people": 1, "status": "open"},
        {"_id": "e", "lat": 28.620, "lon": 77.282, "people": 2, "status": "open"},
    ]
    result = cluster_emergencies(sos, teams)
    assert result["algorithm"] == "kmeans"
    assert result["n_sos"] == 5
    assert result["n_clusters"] == 2
    assert {c["assigned_team"] for c in result["clusters"]} <= {"T1", "T2"}
    assert sum(c["sos_count"] for c in result["clusters"]) == 5
    assert "priority_global" in result


def test_vulnerable_first_kabir_then_children():
    from backend.services.citizens import roster
    from backend.services.priority import rank_citizens

    ordered = rank_citizens(roster(10))
    assert ordered[0]["citizen_name"] == "Kabir Singh"
    assert ordered[0]["vulnerability"] == "child"
    names = [c["citizen_name"] for c in ordered]
    assert names.index("Isha Patel") < names.index("Priya Sharma")


from backend.agents.dialogue import risk_band, speakers_for, _scripted, _parse_turns
from backend.ml.change_monitor import CardChangeMonitor


def test_risk_bands():
    assert risk_band(0.21) == "calm"
    assert risk_band(0.45) == "watch"
    assert risk_band(0.55) == "admin"
    assert risk_band(0.61) == "auto"
    assert speakers_for("auto") == ["Rescue Agent", "Ambulance Agent", "Disaster Team Agent"]
    assert speakers_for("admin") == ["Administrator Agent", "Flood Risk Agent"]


def test_scripted_auto_mentions_dispatch():
    turns = _scripted("auto", "72.0%", "Yamuna Pushta", "ITO / Rajghat floodplain")
    assert len(turns) >= 4
    blob = " ".join(t["text"] for t in turns).lower()
    assert "60" in blob or "rescue" in blob
    assert turns[0]["from"] == "Rescue Agent"
    assert turns[1]["from"] == "Ambulance Agent"


def test_parse_llm_json():
    raw = '{"turns":[{"from":"Rescue Agent","to":"Ambulance Agent","text":"Go now."},{"from":"Ambulance Agent","to":"Rescue Agent","text":"Rolling."}]}'
    turns = _parse_turns(raw, {"Rescue Agent", "Ambulance Agent"})
    assert turns and turns[0]["text"] == "Go now."


def test_parse_allows_citizen_name():
    raw = '{"turns":[{"from":"Rescue Agent","to":"Priya Sharma","text":"Priya, how deep is the water?"},{"from":"Priya Sharma","to":"Rescue Agent","text":"Knee deep."}]}'
    turns = _parse_turns(raw, {"Rescue Agent", "Ambulance Agent", "Priya Sharma"})
    assert turns[0]["to"] == "Priya Sharma"
    assert turns[1]["from"] == "Priya Sharma"


def test_ten_citizen_roster_unique_names():
    from backend.services.citizens import roster

    rows = roster(10)
    assert len(rows) == 10
    assert len({r["citizen_name"] for r in rows}) == 10
    assert all(r.get("lat") and r.get("water_level_note") for r in rows)


def test_explain_random_forest_if_present():
    from backend.ml.explain import explain_prediction

    if not (Path("models") / "random_forest_flood.pkl").exists():
        return
    out = explain_prediction(90.0, [40, 30, 20])
    assert out.get("available") is True
    assert out.get("bars")
    assert out["bars"][0]["feature"]


def test_after_action_pdf_header():
    from backend.services.report import build_report_pdf

    pdf = build_report_pdf(
        {
            "run_id": "demo",
            "scenario": "multiple_sos",
            "history": [{"flood_probability": 0.72}],
            "citizens": [
                {"citizen_name": "Priya Sharma", "age": 29, "lat": 28.65, "lon": 77.26, "water_level_note": "knee-deep", "people": 3}
            ],
            "conversation": {"rescue_check": {"answered": "yes"}, "turns": [{"from": "Rescue Agent", "text": "Priya, stay put."}]},
            "pipeline": {"clusters": [{"cluster_id": "C1", "sos_count": 1, "assigned_team": "T1"}]},
            "events": [],
        }
    )
    assert pdf.startswith(b"%PDF")


def test_card_monitor_reports_seconds_on_sudden_drop():
    mon = CardChangeMonitor()
    first = mon.observe(90, 214, 208, 0.90)
    assert first["sudden"] is False
    second = mon.observe(20, 214, 208, 0.20)
    assert second["sudden"] is True
    assert second["seconds_since_last"] is not None
    metrics = {a["metric"] for a in second["alerts"]}
    assert "flood_probability" in metrics or "rainfall_mm" in metrics
