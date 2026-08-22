from __future__ import annotations

from typing import Any

from backend.config import get_settings
from backend.ml.inference import model_status
from backend.database import mongo


def evaluate_policy(
    flood_probability: float | None,
    data_quality_ok: bool,
    model_ok: bool,
    system_ok: bool,
    human_override: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    monitor = settings.flood_monitor_threshold
    auto = settings.flood_auto_threshold
    gates = {
        "data_quality_ok": data_quality_ok,
        "model_ok": model_ok,
        "system_ok": system_ok,
        "automation_enabled": settings.automation_enabled,
        "human_override_enabled": settings.human_override_enabled,
        "human_override": human_override,
        "monitor_threshold": monitor,
        "auto_threshold": auto,
    }
    if flood_probability is None:
        return {
            "action": "UNAVAILABLE",
            "reason": "MODEL UNAVAILABLE or missing probability",
            "gates": gates,
            "monitor_threshold": monitor,
            "auto_threshold": auto,
            "automation_enabled": settings.automation_enabled,
            "human_override_enabled": settings.human_override_enabled,
            "flood_probability": None,
        }
    if human_override and settings.human_override_enabled:
        return {
            "action": "HUMAN_OVERRIDE",
            "reason": "Operator override is active",
            "gates": gates,
            "monitor_threshold": monitor,
            "auto_threshold": auto,
            "automation_enabled": settings.automation_enabled,
            "human_override_enabled": settings.human_override_enabled,
            "flood_probability": flood_probability,
        }
    if flood_probability < monitor:
        action, reason = "MONITOR", f"P={flood_probability:.3f} < monitor threshold {monitor}"
    elif flood_probability < auto:
        action, reason = "HUMAN_REVIEW", f"monitor ≤ P={flood_probability:.3f} < auto threshold {auto}"
    else:
        action, reason = "AUTOMATED_RESPONSE", f"P={flood_probability:.3f} ≥ auto threshold {auto}"
        if not (settings.automation_enabled and data_quality_ok and model_ok and system_ok):
            action = "HUMAN_REVIEW"
            reason += " — safety gate blocked automation"
    return {
        "action": action,
        "reason": reason,
        "gates": gates,
        "monitor_threshold": monitor,
        "auto_threshold": auto,
        "automation_enabled": settings.automation_enabled,
        "human_override_enabled": settings.human_override_enabled,
        "flood_probability": flood_probability,
    }


def pipeline_health(weather: dict, hydro: dict, prediction: dict) -> tuple[bool, bool, bool]:
    data_ok = bool(weather.get("available")) and bool(hydro.get("available"))
    model_ok = bool(prediction.get("available")) and bool(model_status().get("available"))
    system_ok = bool(mongo.mongo_status().get("connected")) or True
    # Mongo outage must not silently auto-respond; require connected DB for automation.
    system_ok = bool(mongo.mongo_status().get("connected"))
    return data_ok, model_ok, system_ok
