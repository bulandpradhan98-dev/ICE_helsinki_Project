from datetime import date, datetime
from typing import Literal
from typing import Any

from pydantic import BaseModel, HttpUrl


class FeedConfig(BaseModel):
    city: str
    agency: str
    static_gtfs_url: HttpUrl
    vehicle_positions_url: HttpUrl
    trip_updates_url: HttpUrl
    service_alerts_url: HttpUrl
    poll_interval_seconds: int


class FeedValidationRequest(BaseModel):
    static_gtfs_url: HttpUrl
    vehicle_positions_url: HttpUrl
    trip_updates_url: HttpUrl
    service_alerts_url: HttpUrl


class FeedValidationResponse(BaseModel):
    valid: bool
    issues: list[str]


class OperationResult(BaseModel):
    ok: bool
    message: str
    details: dict[str, Any]


class IngestionStatus(BaseModel):
    latest_batch_id: int | None
    latest_batch_started_at: datetime | None
    latest_vehicle_position_at: datetime | None
    latest_trip_update_at: datetime | None
    service_start_date: date | None
    service_end_date: date | None
    routes_count: int
    stops_count: int
    trips_count: int
    stop_times_count: int
    vehicle_positions_count: int
    trip_updates_count: int
    matched_events_count: int
    adherence_events_count: int


class SummaryResponse(BaseModel):
    city: str
    window_hours: int
    bootstrap_mode: bool
    on_time_percentage: float
    total_events: int
    late_events: int
    early_events: int
    updated_at: datetime


class RouteMetric(BaseModel):
    route_id: str
    route_short_name: str
    route_type: int | None = None
    window_hours: int
    on_time_percentage: float
    avg_delay_minutes: float
    total_events: int
    status: Literal["good", "watch", "poor"]


class StopMetric(BaseModel):
    stop_id: str
    stop_name: str
    route_id: str
    on_time_percentage: float
    avg_delay_minutes: float
    total_events: int


class SystemStatus(BaseModel):
    city: str
    agency: str
    active_metric: str
    early_threshold_minutes: int
    late_threshold_minutes: int
    has_database_connection: bool
    notes: list[str]
