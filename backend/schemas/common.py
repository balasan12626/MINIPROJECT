from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HealthResponse(BaseModel):
    status: str
    backend: str
    mongodb: str
    models: str
    timestamp: datetime


class SourceStatus(BaseModel):
    available: bool
    source: str
    message: Optional[str] = None
    timestamp: Optional[datetime] = None


class WeatherCurrent(BaseModel):
    available: bool = True
    source: str
    temperature_c: Optional[float] = None
    rainfall_mm: Optional[float] = None
    rainfall_1h_mm: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_mps: Optional[float] = None
    pressure_hpa: Optional[float] = None
    description: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    timestamp: Optional[datetime] = None
    message: Optional[str] = None


class WeatherForecastItem(BaseModel):
    timestamp: datetime
    temperature_c: Optional[float] = None
    rainfall_mm: Optional[float] = None
    humidity_pct: Optional[float] = None
    description: Optional[str] = None


class ForecastResponse(BaseModel):
    available: bool = True
    source: str
    items: list[WeatherForecastItem] = Field(default_factory=list)
    message: Optional[str] = None


class HydroObservation(BaseModel):
    available: bool = True
    source: str
    kind: str
    value_m: Optional[float] = None
    danger_level_m: Optional[float] = None
    percent_of_danger: Optional[float] = None
    station: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    timestamp: Optional[datetime] = None
    message: Optional[str] = None


class PredictionRequest(BaseModel):
    rainfall_1h_mm: Optional[float] = None
    rainfall_24h_mm: Optional[float] = None
    forecast_daily_mm: list[float] = Field(default_factory=list)
    humidity_pct: Optional[float] = None
    temperature_c: Optional[float] = None
    water_level_m: Optional[float] = None
    dam_level_m: Optional[float] = None
    river_level_m: Optional[float] = None
    month: Optional[int] = None
    mode: str = "live"


class PredictionResponse(BaseModel):
    available: bool = True
    flood_probability: Optional[float] = None
    risk_category: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    prediction_timestamp: Optional[datetime] = None
    inference_latency_ms: Optional[float] = None
    data_freshness_sec: Optional[float] = None
    features_used: dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None


class AgentStatus(BaseModel):
    name: str
    status: str
    last_event: Optional[str] = None
    timestamp: Optional[datetime] = None
    current_action: Optional[str] = None


class PolicyResponse(BaseModel):
    monitor_threshold: float
    auto_threshold: float
    automation_enabled: bool
    human_override_enabled: bool
    action: str
    reason: str
    flood_probability: Optional[float] = None
    gates: dict[str, Any] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    incident_id: str
    decision: str
    reason: str = ""
    user: str = "operator"


class SosRequest(BaseModel):
    lat: float
    lon: float
    people: int = 1
    emergency_type: str = "flood"
    medical_need: bool = False
    notes: str = ""


class RescueStatusUpdate(BaseModel):
    status: str


class OptimizationRequest(BaseModel):
    incident_id: Optional[str] = None
    method: Optional[str] = None
    population_by_zone: Optional[dict[str, int]] = None


class SimulationStartRequest(BaseModel):
    scenario: str
    rainfall_intensity: float = 40.0
    dam_level: float = 198.0
    river_level: float = 204.0
    road_blockage: float = 0.1
    population: int = 12000
    shelter_capacity_factor: float = 1.0
    traffic: float = 0.4
    sos_count: int = 3
    ticks: int = 36
    tick_seconds: float = 2.0
    citizens: list[dict[str, Any]] = Field(default_factory=list)
    features: dict[str, bool] = Field(default_factory=dict)
    # F7: the city the run plans on (backend/data/cities/<id>.json or "delhi_seed").
    city: Optional[str] = Field(default=None, max_length=40)
    # F8: which free ambulance serves an SOS. "nearest_depot" = the original rule.
    dispatch_policy: Literal["nearest_depot", "first_free", "greedy", "optimal", "fair"] = "nearest_depot"
    # F32: fairness knob of the "fair" policy (0 = exactly "optimal").
    fair_lambda: float = Field(default=1.0, ge=0.0, le=20.0)
    # F9: move idle ambulances to predicted hotspots between jobs.
    preposition: bool = False
    # F18: "forecast" = the next hours of Open-Meteo rain for the city drive the run's rainfall.
    rain_source: Literal["scenario", "forecast"] = "scenario"
    # F23: ASSUMED share of a warned zone's people who leave early (0 = off). Used by
    # the what-if planner's synthetic arrivals; swept in the stress test — never a finding.
    warning_compliance: float = Field(default=0.0, ge=0.0, le=1.0)
    # F25: assumed crew rules {on, shift_max_min, rest_min, range_km, refuel_min}; off by default.
    crew_rules: Optional[dict[str, Any]] = None
    # F28: assumed supply-truck fleet {on, trucks, load_person_days, initial_stock_days}; off by default.
    supply: Optional[dict[str, Any]] = None
    # F22: assumed boat fleet count (default 0 = off).
    boats: int = Field(default=0, ge=0, le=20)
    # F26: road flood exposure model ("distance" = proxy v1, "hand" = height above nearest drainage v2).
    exposure_model: Literal["distance", "hand"] = "distance"


class SimulationOverrideRequest(BaseModel):
    rainfall_mm: Optional[float] = None
    river_m: Optional[float] = None
    dam_m: Optional[float] = None
    flood_probability: Optional[float] = None
    # Card names to hand back to the scenario's physics (drop the override).
    clear: Optional[list[str]] = None


class RoadOverrideRequest(BaseModel):
    """Operator road control (F1). `blocked` sets the road; `clear` hands it
    back to the flood rule."""

    road_id: str = Field(min_length=2, max_length=8)
    blocked: Optional[bool] = None
    clear: bool = False


class ShelterOverrideRequest(BaseModel):
    """Operator shelter control (F2). `closed` / `capacity` edit the shelter
    for this run; `clear` restores the seeded capacity and reopens it."""

    name: str = Field(min_length=2, max_length=80)
    closed: Optional[bool] = None
    capacity: Optional[int] = Field(default=None, ge=0, le=100000)
    clear: bool = False


class WhatIfOption(BaseModel):
    """F16: one change to try on a copy of the live run."""

    kind: Literal["add_ambulances", "close_shelter", "set_capacity", "block_road", "open_road",
                  "dispatch_policy", "preposition"]
    n: Optional[int] = Field(default=None, ge=1, le=10)
    name: Optional[str] = Field(default=None, max_length=80)
    capacity: Optional[int] = Field(default=None, ge=0, le=100000)
    road_id: Optional[str] = Field(default=None, max_length=8)
    policy: Optional[Literal["nearest_depot", "first_free", "greedy", "optimal", "fair"]] = None
    on: Optional[bool] = None


class WhatIfRequest(BaseModel):
    options: list[WhatIfOption] = Field(default_factory=list, max_length=4)
    horizon_min: float = Field(default=60, ge=15, le=120)
    runs: int = Field(default=10, ge=5, le=30)
    arrivals: bool = True


class CitizenSosRequest(BaseModel):
    citizen_name: str = "Aarav Sharma"
    age: Optional[int] = Field(default=None, ge=0, le=120)
    lat: float = 28.651
    lon: float = 77.262
    people: int = Field(default=2, ge=1, le=50)
    water_level_note: str = "knee-deep rainwater"
    mode: str = "simulation"
    # F21: injured / critical go to the nearest OSM hospital (triage first).
    medical: Literal["none", "injured", "critical"] = "none"


class RescueOutcomeRequest(BaseModel):
    rescued: bool
    mode: str = "simulation"


class ForecastV4Request(BaseModel):
    """Historical replay of the v4 CAMELS-IND forecaster for one gauge-day."""
    gauge_id: int
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
