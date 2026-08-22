from datetime import datetime, timezone
from typing import Any, Optional

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


class SimulationOverrideRequest(BaseModel):
    rainfall_mm: Optional[float] = None
    river_m: Optional[float] = None
    dam_m: Optional[float] = None
    flood_probability: Optional[float] = None


class CitizenSosRequest(BaseModel):
    citizen_name: str = "Aarav Sharma"
    lat: float = 28.651
    lon: float = 77.262
    people: int = 2
    water_level_note: str = "knee-deep rainwater"
    mode: str = "simulation"


class RescueOutcomeRequest(BaseModel):
    rescued: bool
    mode: str = "simulation"
