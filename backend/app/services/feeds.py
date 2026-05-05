from urllib.parse import urlparse

from app.core.config import get_settings
from app.schemas import FeedConfig, FeedValidationRequest, FeedValidationResponse


def get_default_feed_config() -> FeedConfig:
    settings = get_settings()
    return FeedConfig(
        city=settings.city_name,
        agency=settings.agency_name,
        static_gtfs_url=settings.hsl_static_gtfs_url,
        vehicle_positions_url=settings.hsl_vehicle_positions_url,
        trip_updates_url=settings.hsl_trip_updates_url,
        service_alerts_url=settings.hsl_service_alerts_url,
        poll_interval_seconds=settings.gtfs_rt_poll_interval_seconds,
    )


def validate_feed_urls(payload: FeedValidationRequest) -> FeedValidationResponse:
    issues: list[str] = []

    for field_name, url in payload.model_dump().items():
        parsed = urlparse(str(url))
        if parsed.scheme not in {"http", "https"}:
            issues.append(f"{field_name} must use http or https.")
        if not parsed.netloc:
            issues.append(f"{field_name} is missing a valid host.")

    return FeedValidationResponse(valid=not issues, issues=issues)

