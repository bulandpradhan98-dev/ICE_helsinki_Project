from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

from app.core.config import get_settings
from app.core.database import fetch
from app.schemas import RouteMetric, StopMetric, SummaryResponse

BUS_ROUTE_TYPES = [701, 702, 704]

SUMMARY_QUERY = """
SELECT
  COALESCE(ROUND(AVG(on_time_percentage)::numeric, 2), 0.0) AS on_time_percentage,
  COALESCE(SUM(total_events), 0) AS total_events,
  COALESCE(SUM(late_events), 0) AS late_events,
  COALESCE(SUM(early_events), 0) AS early_events
FROM route_otp_hourly
WHERE bucket >= NOW() - ($1 * interval '1 hour')
  AND route_type = ANY($2::int[]);
"""

ROUTES_QUERY = """
SELECT
  route_id,
  route_short_name,
  route_type,
  ROUND(AVG(on_time_percentage)::numeric, 2) AS on_time_percentage,
  ROUND(AVG(avg_delay_minutes)::numeric, 2) AS avg_delay_minutes,
  SUM(total_events) AS total_events
FROM route_otp_hourly
WHERE bucket >= NOW() - ($1 * interval '1 hour')
  AND route_type = ANY($2::int[])
GROUP BY route_id, route_short_name, route_type
ORDER BY on_time_percentage DESC, total_events DESC;
"""

STOPS_QUERY = """
SELECT
  stop_id,
  stop_name,
  route_id,
  ROUND(AVG(on_time_percentage)::numeric, 2) AS on_time_percentage,
  ROUND(AVG(avg_delay_minutes)::numeric, 2) AS avg_delay_minutes,
  SUM(total_events) AS total_events
FROM stop_otp_hourly
WHERE route_id = $1
  AND bucket >= NOW() - ($2 * interval '1 hour')
GROUP BY stop_id, stop_name, route_id
ORDER BY total_events DESC, on_time_percentage DESC;
"""


def _fallback_summary(window_hours: int) -> SummaryResponse:
    settings = get_settings()
    return SummaryResponse(
        city=settings.city_name,
        window_hours=window_hours,
        bootstrap_mode=True,
        on_time_percentage=0.0,
        total_events=0,
        late_events=0,
        early_events=0,
        updated_at=datetime.now(UTC),
    )


async def fetch_summary(window_hours: int = 24) -> SummaryResponse:
    settings = get_settings()
    try:
        rows = await fetch(SUMMARY_QUERY, window_hours, BUS_ROUTE_TYPES)
    except (asyncpg.PostgresError, OSError):
        return _fallback_summary(window_hours)

    if not rows:
        return _fallback_summary(window_hours)

    row = rows[0]
    return SummaryResponse(
        city=settings.city_name,
        window_hours=window_hours,
        bootstrap_mode=int(row["total_events"]) == 0,
        on_time_percentage=float(row["on_time_percentage"]),
        total_events=int(row["total_events"]),
        late_events=int(row["late_events"]),
        early_events=int(row["early_events"]),
        updated_at=datetime.now(UTC),
    )


async def fetch_route_metrics(window_hours: int = 24) -> list[RouteMetric]:
    try:
        rows = await fetch(ROUTES_QUERY, window_hours, BUS_ROUTE_TYPES)
    except (asyncpg.PostgresError, OSError):
        return []

    route_metrics: list[RouteMetric] = []
    for row in rows:
        on_time_percentage = float(row["on_time_percentage"])
        status = "good"
        if on_time_percentage < 80:
            status = "poor"
        elif on_time_percentage < 90:
            status = "watch"

        route_metrics.append(
            RouteMetric(
                route_id=row["route_id"],
                route_short_name=row["route_short_name"] or row["route_id"],
                route_type=row["route_type"],
                window_hours=window_hours,
                on_time_percentage=on_time_percentage,
                avg_delay_minutes=float(row["avg_delay_minutes"]),
                total_events=int(row["total_events"]),
                status=status,
            )
        )

    return route_metrics


async def fetch_stop_metrics(route_id: str, window_hours: int = 24) -> list[StopMetric]:
    try:
        rows = await fetch(STOPS_QUERY, route_id, window_hours)
    except (asyncpg.PostgresError, OSError):
        return []

    return [
        StopMetric(
            stop_id=row["stop_id"],
            stop_name=row["stop_name"],
            route_id=row["route_id"],
            on_time_percentage=float(row["on_time_percentage"]),
            avg_delay_minutes=float(row["avg_delay_minutes"]),
            total_events=int(row["total_events"]),
        )
        for row in rows
    ]
