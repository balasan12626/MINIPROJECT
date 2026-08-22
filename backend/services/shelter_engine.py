from __future__ import annotations

from typing import Any

from backend.database import mongo
from backend.services.seed import SHELTERS
from backend.utils.geo import haversine_km


def _available_seats(shelter: dict[str, Any]) -> int:
    return int(shelter.get("capacity") or 0) - int(shelter.get("occupancy") or 0)


def filter_shelters(shelters: list[dict[str, Any]], zone_risk: float) -> list[dict[str, Any]]:
    kept = []
    for s in shelters:
        status = str(s.get("status") or "open").lower()
        if status in {"unsafe", "closed", "full"}:
            continue
        if not s.get("accessible", True):
            continue
        if _available_seats(s) <= 0:
            continue
        if float(s.get("flood_risk") or 0) >= 0.65:
            continue
        if zone_risk >= 0.7 and float(s.get("flood_risk") or 0) >= 0.45:
            continue
        kept.append(s)
    return kept


def score_shelter(
    shelter: dict[str, Any],
    origin_lat: float,
    origin_lon: float,
    population: int,
    traffic: float,
    zone_risk: float,
) -> dict[str, Any]:
    dist = haversine_km(origin_lat, origin_lon, float(shelter["lat"]), float(shelter["lon"]))
    travel_min = dist / max(0.18, 0.42 - 0.25 * traffic) * 60 / 1.0  # ~15-40 km/h mixed urban
    flood_risk = float(shelter.get("flood_risk") or 0)
    seats = max(_available_seats(shelter), 1)
    overload = max(0.0, (population - seats) / max(seats, 1))
    road_safety = 1.0 - min(1.0, flood_risk * 0.7 + zone_risk * 0.3)
    score = (
        0.22 * dist
        + 0.22 * (travel_min / 10.0)
        + 0.20 * flood_risk * 10
        + 0.12 * traffic * 5
        + 0.16 * overload * 4
        + 0.08 * (1.0 - road_safety) * 8
    )
    return {
        **shelter,
        "distance_km": round(dist, 3),
        "travel_time_min": round(travel_min, 2),
        "available_seats": _available_seats(shelter),
        "overload": round(overload, 3),
        "road_safety": round(road_safety, 3),
        "score": round(score, 4),
    }


async def recommend_shelters(
    origin_lat: float,
    origin_lon: float,
    population: int,
    traffic: float,
    zone_risk: float,
    limit: int = 3,
) -> list[dict[str, Any]]:
    stored = await mongo.find_many("shelters", {}, limit=50, sort_field="shelter_id", direction=1)
    shelters = stored or SHELTERS
    candidates = filter_shelters(shelters, zone_risk)
    scored = [score_shelter(s, origin_lat, origin_lon, population, traffic, zone_risk) for s in candidates]
    scored.sort(key=lambda x: x["score"])
    return scored[:limit]
