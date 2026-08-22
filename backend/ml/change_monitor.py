"""Isolation Forest + rate-of-change monitor for editable KPI cards."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from backend.utils.geo import utcnow

_KEYS = ("rainfall_mm", "river_m", "dam_m", "flood_probability")
_LABELS = {
    "rainfall_mm": "rainfall",
    "river_m": "river level",
    "dam_m": "dam level",
    "flood_probability": "flood probability",
}


class CardChangeMonitor:
    def __init__(self) -> None:
        self.samples: list[dict[str, Any]] = []
        self.forest: IsolationForest | None = None

    def reset(self) -> None:
        self.samples = []
        self.forest = None

    def observe(self, rainfall_mm: float | None, river_m: float | None, dam_m: float | None, flood_probability: float | None) -> dict[str, Any]:
        now = time.monotonic()
        row = {
            "t": now,
            "timestamp": utcnow().isoformat(),
            "rainfall_mm": float(rainfall_mm or 0),
            "river_m": float(river_m or 0),
            "dam_m": float(dam_m or 0),
            "flood_probability": float(flood_probability or 0),
        }
        prev = self.samples[-1] if self.samples else None
        self.samples.append(row)
        self.samples = self.samples[-80:]
        alerts: list[dict[str, Any]] = []
        seconds = None
        if prev:
            seconds = round(now - float(prev["t"]), 2)
            for key in _KEYS:
                old, new = prev[key], row[key]
                base = abs(old) if abs(old) > 1e-6 else 1.0
                rel = abs(new - old) / base
                abs_hit = abs(new - old) >= (0.12 if key == "flood_probability" else 8.0)
                if seconds <= 45 and (rel >= 0.28 or abs_hit):
                    alerts.append(
                        {
                            "metric": key,
                            "label": _LABELS[key],
                            "from_value": round(old, 4),
                            "to_value": round(new, 4),
                            "seconds": seconds,
                            "direction": "high" if new > old else "low",
                            "relative_change": round(rel, 3),
                        }
                    )
        iso_flag = False
        if len(self.samples) >= 10:
            mat = np.array([[s[k] for k in _KEYS] for s in self.samples], dtype=float)
            self.forest = IsolationForest(n_estimators=40, contamination=0.12, random_state=42)
            self.forest.fit(mat[:-1])
            pred = self.forest.predict(mat[-1:])
            iso_flag = int(pred[0]) == -1
        return {
            "available": True,
            "algorithm": "isolation_forest+delta",
            "sudden": bool(alerts) or iso_flag,
            "isolation_forest_outlier": iso_flag,
            "seconds_since_last": seconds,
            "alerts": alerts,
            "n_samples": len(self.samples),
            "current": {k: row[k] for k in _KEYS},
        }


monitors: dict[str, CardChangeMonitor] = {"live": CardChangeMonitor(), "simulation": CardChangeMonitor()}


def observe_cards(mode: str, rainfall_mm, river_m, dam_m, flood_probability) -> dict[str, Any]:
    return monitors.setdefault(mode, CardChangeMonitor()).observe(rainfall_mm, river_m, dam_m, flood_probability)


def reset_monitor(mode: str = "simulation") -> None:
    monitors.setdefault(mode, CardChangeMonitor()).reset()
