from fastapi import APIRouter

from backend.config import get_settings
from backend.ml.inference import model_status

router = APIRouter()


@router.get("/api/sources")
async def sources():
    settings = get_settings()
    models = model_status()
    return {
        "city": {"name": settings.city_name, "lat": settings.city_lat, "lon": settings.city_lon},
        "live_apis": [
            {
                "id": "openweather",
                "role": "Current weather (temp, humidity, wind, pressure, rain)",
                "url": "https://api.openweathermap.org/data/2.5/weather",
                "keyed": bool(settings.openweather_key),
            },
            {
                "id": "open-meteo",
                "role": "24h rainfall + 10-day forecast (fallback weather)",
                "url": "https://api.open-meteo.com/v1/forecast",
                "keyed": False,
            },
            {
                "id": "open-meteo-flood",
                "role": "Yamuna / Hathnikund discharge → stage proxy",
                "url": "https://flood-api.open-meteo.com/v1/flood",
                "keyed": False,
            },
            {
                "id": "groq",
                "role": "Agent-to-agent radio conversation (LLM)",
                "url": "https://api.groq.com/openai/v1/chat/completions",
                "keyed": bool(settings.groq_api_key),
            },
            {
                "id": "openstreetmap",
                "role": "Map tiles",
                "url": "https://tile.openstreetmap.org",
                "keyed": False,
            },
            {
                "id": "mongodb",
                "role": "Shelters, roads, SOS, agents, incidents",
                "url": settings.mongodb_uri.split("@")[-1] if settings.mongodb_uri else "",
                "keyed": False,
            },
        ],
        "ml": {
            "best_model": models.get("best_model"),
            "model_id": models.get("model_id"),
            "available": models.get("available"),
            "algorithms": ["random_forest", "xgboost", "kmeans_sos"],
        },
    }
