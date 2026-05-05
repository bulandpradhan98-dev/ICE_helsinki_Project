from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_env: Literal["development", "staging", "production"] = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql://transit:transit@db:5432/transit_performance"

    city_name: str = "Helsinki"
    agency_name: str = "HSL"

    hsl_static_gtfs_url: AnyHttpUrl = Field(
        default="https://infopalvelut.storage.hsldev.com/gtfs/hsl.zip"
    )
    hsl_vehicle_positions_url: AnyHttpUrl = Field(
        default="https://realtime.hsl.fi/realtime/vehicle-positions/v2/hsl"
    )
    hsl_trip_updates_url: AnyHttpUrl = Field(
        default="https://realtime.hsl.fi/realtime/trip-updates/v2/hsl"
    )
    hsl_service_alerts_url: AnyHttpUrl = Field(
        default="https://realtime.hsl.fi/realtime/service-alerts/v2/hsl"
    )
    gtfs_rt_poll_interval_seconds: int = 30

    schedule_early_threshold_minutes: int = -1
    schedule_late_threshold_minutes: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()

