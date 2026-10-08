from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DamSimulationRequest(BaseModel):
    dam_id: str
    scenario: Optional[str] = None  # normal | heavy_rainfall | extreme_rainfall | emergency_release | worst_case
    current_level_m: Optional[float] = Field(default=None, ge=0)
    rainfall_mm: float = Field(default=20.0, ge=0, le=600)
    rainfall_intensity_mm_hr: float = Field(default=5.0, ge=0, le=150)
    inflow_cumec: float = Field(default=800.0, ge=0)
    outflow_cumec: float = Field(default=600.0, ge=0)
    capacity_override_m: Optional[float] = Field(default=None, gt=0)
    forecast_hours: int = Field(default=72, ge=1, le=240)
    temperature_c: Optional[float] = Field(default=None, ge=-10, le=55)


class DamRiskRequest(BaseModel):
    dam_id: str
    rainfall_24h_mm: float = Field(default=20.0, ge=0, le=600)
    forecast_daily_mm: list[float] = Field(default_factory=list)
    month: Optional[int] = Field(default=None, ge=1, le=12)
