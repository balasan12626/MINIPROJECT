from fastapi import APIRouter

from backend.database import mongo
from backend.services import hydro_service, weather_service
from backend.services.seed import LANDMARKS, ROADS

router = APIRouter()


@router.get("/api/weather/current")
async def weather_current():
    return await weather_service.fetch_current()


@router.get("/api/weather/forecast")
async def weather_forecast():
    return await weather_service.fetch_forecast()


@router.get("/api/rainfall/current")
async def rainfall_current():
    current = await weather_service.fetch_current()
    if not current.get("available"):
        return current
    return {
        "available": True,
        "source": current.get("source"),
        "rainfall_mm": current.get("rainfall_mm"),
        "rainfall_1h_mm": current.get("rainfall_1h_mm"),
        "lat": current.get("lat"),
        "lon": current.get("lon"),
        "timestamp": current.get("timestamp"),
    }


@router.get("/api/water-level")
async def water_level():
    return await hydro_service.fetch_water_level()


@router.get("/api/dam")
async def dam():
    return await hydro_service.fetch_dam()


@router.get("/api/river")
async def river():
    return await hydro_service.fetch_river()


@router.get("/api/traffic")
async def traffic():
    roads = await mongo.find_many("roads", {}, limit=50, sort_field="road_id", direction=1)
    roads = roads or ROADS
    blocked = [r for r in roads if r.get("blocked")]
    return {
        "available": True,
        "source": "seed+runtime",
        "roads": roads,
        "blocked_count": len(blocked),
        "landmarks": LANDMARKS,
    }
