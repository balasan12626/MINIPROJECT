from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "flood_response"

    weather_api_key: str = ""
    openweather_api_key: str = ""
    tomorrow_io_api_key: str = ""
    tomtom_api_key: str = ""
    maps_api_key: str = ""
    traffic_api_key: str = ""
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_live_model: str = "gemini-3.1-flash-live-preview"

    city_name: str = "Delhi"
    city_lat: float = 28.6139
    city_lon: float = 77.2090
    city_bbox: str = "28.4,76.8,28.9,77.4"

    flood_monitor_threshold: float = 0.50
    flood_auto_threshold: float = 0.60
    automation_enabled: bool = True
    human_override_enabled: bool = True

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    operator_username: str = "operator"
    operator_password: str = "changeme"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    model_dir: str = "models"
    model_lazy_load: bool = True

    wris_basin: str = "Yamuna"
    dam_danger_level_m: float = 205.80
    wris_danger_level_m: float = 205.80

    @property
    def openweather_key(self) -> str:
        return self.openweather_api_key or self.weather_api_key

    @property
    def tomtom_key(self) -> str:
        return self.tomtom_api_key or self.maps_api_key or self.traffic_api_key

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        parts = [float(x) for x in self.city_bbox.split(",")]
        if len(parts) != 4:
            return (28.4, 76.8, 28.9, 77.4)
        return tuple(parts)  # south, west, north, east

    @property
    def models_path(self) -> Path:
        path = Path(self.model_dir)
        if not path.is_absolute():
            path = ROOT / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
