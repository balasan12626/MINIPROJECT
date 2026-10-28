"""F29 — silent zones: phone towers lost to the flood (modelled).

Tower locations come from OpenCelliD (CC BY-SA 4.0, attribution required) via
scripts/build_towers.py → backend/data/cities/<id>.towers.json. No towers file
(no OPENCELLID_TOKEN yet) → the feature is off and nothing here changes a run.

A tower is "flooded" when its flood exposure (the SAME distance-to-water proxy
the roads use, computed at build time) meets the engine's road closure rule
exposure ≥ 0.85 − blockage. Coverage radius per radio type is ASSUMED (labelled).
A grid cell is SILENT when at least one tower covered it before the flood and
no tower that still works covers it now. Everything is labelled "modelled".
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.utils.geo import haversine_km

CITY_DIR = Path(__file__).resolve().parents[1] / "data" / "cities"
COVERAGE_KM = {"GSM": 2.0, "UMTS": 1.5, "LTE": 1.0, "NR": 0.5, "CDMA": 2.0}  # assumed by radio type
COVERAGE_SOURCE = "assumed coverage radius by radio type (GSM 2 km, UMTS 1.5 km, LTE 1 km, NR 0.5 km)"
GRID_KM = 0.5
CLOSE_RULE = 0.85  # same as the road rule: flooded when exposure >= 0.85 - blockage


@lru_cache(maxsize=16)
def load_towers(city_id: str) -> dict[str, Any] | None:
    path = CITY_DIR / f"{city_id}.towers.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def coverage_km(t: dict[str, Any]) -> float:
    return float(COVERAGE_KM.get(str(t.get("radio") or "").upper(), 1.0))


def flooded(t: dict[str, Any], blockage: float) -> bool:
    return float(t.get("flood_exposure") or 0.0) >= CLOSE_RULE - float(blockage)


def grid(bbox: list[float], step_km: float = GRID_KM) -> list[tuple[float, float]]:
    s, w, n, e = bbox
    dlat = step_km / 110.574
    dlon = step_km / (111.320 * math.cos(math.radians((s + n) / 2)))
    out = []
    lat = s + dlat / 2
    while lat < n:
        lon = w + dlon / 2
        while lon < e:
            out.append((round(lat, 5), round(lon, 5)))
            lon += dlon
        lat += dlat
    return out


def _covered_mask(cells, towers: list[dict[str, Any]]):
    """Boolean per cell: inside any tower's coverage circle (equirectangular km)."""
    import numpy as np

    c = np.asarray(cells, dtype=float)
    if not towers or not len(c):
        return np.zeros(len(c), dtype=bool)
    t = np.asarray([[float(x["lat"]), float(x["lon"])] for x in towers])
    r = np.asarray([coverage_km(x) for x in towers])
    kx = 111.320 * np.cos(np.radians(c[:, 0:1]))
    d = np.hypot((c[:, 0:1] - t[None, :, 0]) * 110.574, (c[:, 1:2] - t[None, :, 1]) * kx)
    return (d <= r[None, :]).any(axis=1)


def silent_cells(towers: list[dict[str, Any]], blockage: float, cells: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Cells covered by some tower before the flood and by no working tower now."""
    up = [t for t in towers if not flooded(t, blockage)]
    down = [t for t in towers if flooded(t, blockage)]
    if not down or not cells:
        return []
    mask = _covered_mask(cells, down) & ~_covered_mask(cells, up)
    return [p for p, m in zip(cells, mask) if m]


def silent_zones(city: dict[str, Any], blockage: float) -> dict[str, Any] | None:
    """Silent cells grouped by the nearest OSM zone. None when no towers file."""
    data = load_towers(city["id"])
    if not data:
        return None
    towers = data.get("towers") or []
    cells = silent_cells(towers, blockage, grid(city["bbox"]))
    zones = city.get("zones") or []
    groups: dict[str, dict[str, Any]] = {}
    for c in cells:
        z = min(zones, key=lambda z: haversine_km(c[0], c[1], float(z["lat"]), float(z["lon"]))) if zones else None
        key = str(z["zone_id"]) if z else "area"
        g = groups.setdefault(key, {"zone_id": key, "name": z["name"] if z else "area", "lat": z["lat"] if z else c[0],
                                    "lon": z["lon"] if z else c[1], "cells": 0, "centre": [0.0, 0.0]})
        g["cells"] += 1
        g["centre"][0] += c[0]
        g["centre"][1] += c[1]
    for g in groups.values():
        g["centre"] = [round(g["centre"][0] / g["cells"], 5), round(g["centre"][1] / g["cells"], 5)]
        g["area_km2"] = round(g["cells"] * GRID_KM * GRID_KM, 2)
    return {
        "towers": len(towers),
        "towers_flooded": sum(1 for t in towers if flooded(t, blockage)),
        "cells": [list(c) for c in cells],
        "cell_km": GRID_KM,
        "zones": sorted(groups.values(), key=lambda g: -g["cells"]),
        "label": "modelled — tower flooding from the road flood proxy; coverage radius assumed",
        "coverage_source": COVERAGE_SOURCE,
        "attribution": data.get("attribution"),
    }


def is_silent(lat: float, lon: float, view: dict[str, Any] | None) -> bool:
    if not view or not view.get("cells"):
        return False
    half = view["cell_km"] / 2 + 0.01
    return any(haversine_km(lat, lon, c[0], c[1]) <= half * 1.42 for c in view["cells"])
