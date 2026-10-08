"""Single source of truth for every decision-relevant threshold.

Before this module the same concept was encoded with different numbers in
different places — e.g. the model-disagreement gate was 0.10 in
ml/inference.py but 0.15 in services/algorithm_arena.py, so the main
"Recommended action" and the Arena's autonomy gate could legitimately
disagree about the same run. Every consumer now reads from here.

Operator-tunable values (monitor/auto) stay in Settings so they remain
env-overridable; the rest are policy constants.
"""

from backend.config import get_settings


def _settings():
    return get_settings()


# --- Probability -> severity label cutoffs (was: utils/geo.py literals) ---
SEVERITY_CRITICAL = 0.70
SEVERITY_HIGH = 0.50
SEVERITY_MODERATE = 0.35

# --- Model agreement ---
# One gap threshold, shared by ml/inference.dual_model_view and the Arena.
# Previously 0.10 (inference) vs 0.15 (Arena rule text R1) — the UI quoted
# "gap >= 15%" while the action was actually gated at 10%.
MODEL_GAP_MAX = 0.15
# Physics-twin vs ML divergence (Arena rule R2).
PHYSICS_DIVERGENCE_MAX = 0.20

# --- Priority rules (Phase 8: one definition, used by Arena + triage) ---
# A person is a CHILD when age < CHILD_MAX_AGE (strictly less), ELDERLY when
# age >= ELDERLY_MIN_AGE. Used by policy rule R3, triage, vulnerable-first
# ranking and the ambulance decision (backend/services/priority.py helpers).
# Mirrored in frontend/src/data/rescueAssets.js (CHILD_MAX_AGE).
CHILD_MAX_AGE = 12
ELDERLY_MIN_AGE = 60

# --- Agent narration bands (was: agents/dialogue.py literals) ---
AGENT_BAND_CALM = 0.40
AGENT_BAND_WATCH = 0.50


def monitor_threshold() -> float:
    """Below this probability: MONITOR only."""
    return float(_settings().flood_monitor_threshold)


def auto_threshold() -> float:
    """At/above this probability: automated response is permitted."""
    return float(_settings().flood_auto_threshold)


def as_dict() -> dict:
    """Serialisable view for GET /api/config/thresholds and the frontend."""
    return {
        "monitor_threshold": monitor_threshold(),
        "auto_threshold": auto_threshold(),
        "severity_critical": SEVERITY_CRITICAL,
        "severity_high": SEVERITY_HIGH,
        "severity_moderate": SEVERITY_MODERATE,
        "model_gap_max": MODEL_GAP_MAX,
        "physics_divergence_max": PHYSICS_DIVERGENCE_MAX,
        "child_max_age": CHILD_MAX_AGE,
        "elderly_min_age": ELDERLY_MIN_AGE,
        "agent_band_calm": AGENT_BAND_CALM,
        "agent_band_watch": AGENT_BAND_WATCH,
    }
