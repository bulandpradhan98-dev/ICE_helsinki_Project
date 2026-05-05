from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import date

import httpx

from app.core.config import get_settings
from app.core.database import connection


@dataclass(slots=True)
class GTFSStaticSummary:
    file_counts: dict[str, int]
    start_date: date | None
    end_date: date | None


def _read_csv_tables(content: bytes) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name in archive.namelist():
            if not name.endswith(".txt"):
                continue
            with archive.open(name) as file_handle:
                text = io.TextIOWrapper(file_handle, encoding="utf-8-sig")
                reader = csv.DictReader(text)
                tables[name] = list(reader)
    return tables


def summarize_gtfs_tables(tables: dict[str, list[dict[str, str]]]) -> GTFSStaticSummary:
    counts = {table_name: len(rows) for table_name, rows in tables.items()}

    calendar_dates = tables.get("calendar_dates.txt", [])
    service_dates = [row.get("date") for row in calendar_dates if row.get("date")]
    parsed_dates = sorted(
        date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:8]}")
        for value in service_dates
    )

    return GTFSStaticSummary(
        file_counts=counts,
        start_date=parsed_dates[0] if parsed_dates else None,
        end_date=parsed_dates[-1] if parsed_dates else None,
    )


async def fetch_static_gtfs_tables(url: str) -> tuple[dict[str, list[dict[str, str]]], GTFSStaticSummary]:
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(url)
        response.raise_for_status()
    tables = _read_csv_tables(response.content)
    return tables, summarize_gtfs_tables(tables)


def _first_stop_times(stop_times: list[dict[str, str]]) -> dict[str, str]:
    first_times: dict[str, tuple[int, str]] = {}
    for row in stop_times:
        trip_id = row.get("trip_id")
        if not trip_id:
            continue
        sequence = int(row.get("stop_sequence") or 0)
        departure_time = row.get("departure_time") or row.get("arrival_time") or ""
        current = first_times.get(trip_id)
        if current is None or sequence < current[0]:
            first_times[trip_id] = (sequence, departure_time)
    return {trip_id: value[1] for trip_id, value in first_times.items()}


async def import_static_gtfs(url: str) -> dict[str, int | str | None]:
    tables, summary = await fetch_static_gtfs_tables(url)
    settings = get_settings()

    routes = tables.get("routes.txt", [])
    stops = tables.get("stops.txt", [])
    trips = tables.get("trips.txt", [])
    stop_times = tables.get("stop_times.txt", [])
    shapes = tables.get("shapes.txt", [])
    first_stop_times = _first_stop_times(stop_times)

    route_records = [
        (
            row.get("route_id"),
            row.get("agency_id"),
            row.get("route_short_name"),
            row.get("route_long_name"),
            row.get("route_desc"),
            int(row["route_type"]) if row.get("route_type") else None,
            row.get("route_color"),
            row.get("route_text_color"),
        )
        for row in routes
        if row.get("route_id")
    ]
    valid_route_ids = {record[0] for record in route_records}

    stop_records = [
        (
            row.get("stop_id"),
            row.get("stop_code"),
            row.get("stop_name"),
            row.get("parent_station"),
            row.get("platform_code"),
            float(row["stop_lat"]),
            float(row["stop_lon"]),
        )
        for row in stops
        if row.get("stop_id") and row.get("stop_name") and row.get("stop_lat") and row.get("stop_lon")
    ]
    valid_stop_ids = {record[0] for record in stop_records}

    trip_records = [
        (
            row.get("trip_id"),
            row.get("route_id"),
            row.get("service_id"),
            row.get("trip_headsign"),
            int(row["direction_id"]) if row.get("direction_id") else None,
            row.get("block_id"),
            row.get("shape_id"),
            first_stop_times.get(row.get("trip_id", "")),
        )
        for row in trips
        if row.get("trip_id") and row.get("route_id") in valid_route_ids
    ]
    valid_trip_ids = {record[0] for record in trip_records}

    stop_time_records = [
        (
            row.get("trip_id"),
            int(row["stop_sequence"]) if row.get("stop_sequence") else 0,
            row.get("stop_id"),
            row.get("arrival_time"),
            row.get("departure_time"),
        )
        for row in stop_times
        if row.get("trip_id") in valid_trip_ids and row.get("stop_id") in valid_stop_ids
    ]

    shape_records = [
        (
            row.get("shape_id"),
            int(row["shape_pt_sequence"]) if row.get("shape_pt_sequence") else 0,
            float(row["shape_pt_lat"]),
            float(row["shape_pt_lon"]),
        )
        for row in shapes
        if row.get("shape_id") and row.get("shape_pt_lat") and row.get("shape_pt_lon")
    ]

    async with connection() as conn:
        async with conn.transaction():
            source_id = await conn.fetchval(
                """
                SELECT id
                FROM data_sources
                WHERE city_name = $1 AND agency_name = $2
                ORDER BY id
                LIMIT 1
                """,
                settings.city_name,
                settings.agency_name,
            )
            if source_id is None:
                source_id = await conn.fetchval(
                    """
                    INSERT INTO data_sources (
                      city_name,
                      agency_name,
                      static_gtfs_url,
                      vehicle_positions_url,
                      trip_updates_url,
                      service_alerts_url,
                      poll_interval_seconds
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                    """,
                    settings.city_name,
                    settings.agency_name,
                    str(settings.hsl_static_gtfs_url),
                    str(settings.hsl_vehicle_positions_url),
                    str(settings.hsl_trip_updates_url),
                    str(settings.hsl_service_alerts_url),
                    settings.gtfs_rt_poll_interval_seconds,
                )

            batch_id = await conn.fetchval(
                """
                INSERT INTO gtfs_import_batches (
                  source_id,
                  import_completed_at,
                  service_start_date,
                  service_end_date,
                  metadata
                )
                VALUES ($1, NOW(), $2, $3, $4::jsonb)
                RETURNING id
                """,
                source_id,
                summary.start_date,
                summary.end_date,
                json.dumps(summary.file_counts),
            )

            if route_records:
                await conn.copy_records_to_table(
                    "gtfs_routes",
                    records=[(batch_id, *record) for record in route_records],
                    columns=[
                        "batch_id",
                        "route_id",
                        "agency_id",
                        "route_short_name",
                        "route_long_name",
                        "route_desc",
                        "route_type",
                        "route_color",
                        "route_text_color",
                    ],
                )

            if trip_records:
                await conn.copy_records_to_table(
                    "gtfs_trips",
                    records=[(batch_id, *record) for record in trip_records],
                    columns=[
                        "batch_id",
                        "trip_id",
                        "route_id",
                        "service_id",
                        "trip_headsign",
                        "direction_id",
                        "block_id",
                        "shape_id",
                        "start_time",
                    ],
                )

            await conn.executemany(
                """
                INSERT INTO gtfs_stops (
                  batch_id,
                  stop_id,
                  stop_code,
                  stop_name,
                  parent_station,
                  platform_code,
                  geom
                )
                VALUES (
                  $1, $2, $3, $4, $5, $6,
                  ST_SetSRID(ST_MakePoint($8, $7), 4326)::geography
                )
                """,
                [(batch_id, *record) for record in stop_records],
                )

            if shape_records:
                await conn.executemany(
                    """
                    INSERT INTO gtfs_shapes (
                      batch_id,
                      shape_id,
                      shape_pt_sequence,
                      geom
                    )
                    VALUES (
                      $1, $2, $3,
                      ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography
                    )
                    """,
                    [(batch_id, *record) for record in shape_records],
                )

            if stop_time_records:
                await conn.copy_records_to_table(
                    "gtfs_stop_times",
                    records=[(batch_id, *record) for record in stop_time_records],
                    columns=[
                        "batch_id",
                        "trip_id",
                        "stop_sequence",
                        "stop_id",
                        "arrival_time",
                        "departure_time",
                    ],
                )

    return {
        "batch_id": batch_id,
        "routes": len(route_records),
        "stops": len(stop_records),
        "trips": len(trip_records),
        "stop_times": len(stop_time_records),
        "shapes": len(shape_records),
        "service_start_date": summary.start_date.isoformat() if summary.start_date else None,
        "service_end_date": summary.end_date.isoformat() if summary.end_date else None,
    }
