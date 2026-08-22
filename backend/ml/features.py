"""Map live / simulation observations onto INDOFLOODS training features."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

from backend.config import get_settings

PRECIP_COLS = [f"T{i}d" for i in range(1, 11)]


def _metadata() -> dict[str, Any]:
    path = get_settings().models_path / "model_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def default_catchment() -> dict[str, Any]:
    meta = _metadata()
    return dict(meta.get("default_catchment") or {})


def live_precip_to_t_days(rainfall_24h_mm: float, forecast_daily_mm: list[float] | None = None) -> dict[str, float]:
    forecast = list(forecast_daily_mm or [])
    daily = [max(float(rainfall_24h_mm), 0.0)]
    daily.extend(max(float(x), 0.0) for x in forecast)
    while len(daily) < 10:
        daily.append(daily[-1] * 0.35)
    daily = daily[:10]
    out = {}
    acc = 0.0
    for i, val in enumerate(daily, start=1):
        acc += val
        out[f"T{i}d"] = round(acc, 4)
    return out


def build_feature_row(
    rainfall_24h_mm: float,
    forecast_daily_mm: list[float] | None = None,
    month: int | None = None,
    catchment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    month = int(month or now.month)
    t = live_precip_to_t_days(rainfall_24h_mm, forecast_daily_mm)
    row: dict[str, Any] = {**t}
    row["month"] = month
    row["doy"] = int(now.timetuple().tm_yday) if month == now.month else int(month * 30.4)
    row["is_monsoon"] = int(month in {6, 7, 8, 9})
    t1, t3, t7, t10 = row["T1d"], row["T3d"], row["T7d"], row["T10d"]
    row["precip_intensity_recent"] = t1 / (t3 + 1e-6)
    row["precip_frac_recent"] = t1 / (t10 + 1e-6)
    row["precip_buildup_3_10"] = (t10 - t3) / (t10 + 1e-6)
    row["log_T1d"] = math.log1p(t1)
    row["log_T3d"] = math.log1p(t3)
    row["log_T7d"] = math.log1p(t7)
    row["log_T10d"] = math.log1p(t10)

    catch = {**default_catchment(), **(catchment or {})}
    annual = float(catch.get("Annual Precipitation") or 0) or 1.0
    wettest = float(catch.get("Precipitation of Wettest Month") or 0) or 1.0
    row["t10_vs_annual"] = t10 / ((annual / 36.5) + 1e-6)
    row["t3_vs_wettest"] = t3 / (wettest + 1e-6)
    row["t1_vs_wettest"] = t1 / (wettest + 1e-6)

    meta = _metadata()
    enc = meta.get("encodings") or {}
    row["g_prior"] = float(enc.get("default_prior") or enc.get("global_prior") or 0.36)
    by_col = enc.get("default_precip_by_col") or {}
    glob = enc.get("precip_global") or {}
    for col in PRECIP_COLS:
        stats = by_col.get(col) or glob.get(col) or {}
        mean = float(stats.get("mean") or glob.get(col, {}).get("mean") or 1.0)
        std = float(stats.get("std") or glob.get(col, {}).get("std") or 1.0) or 1.0
        row[f"{col}_z"] = (row[col] - mean) / (std + 1e-6)

    for col in meta.get("features_numeric", []):
        if col not in row and col in catch:
            row[col] = catch[col]
    for col in meta.get("features_categorical", []):
        row[col] = catch.get(col, "Unknown")
    return row


def feature_columns() -> tuple[list[str], list[str]]:
    meta = _metadata()
    return list(meta.get("features_numeric") or []), list(meta.get("features_categorical") or [])
