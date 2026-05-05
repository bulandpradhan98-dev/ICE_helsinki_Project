from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
from google.transit import gtfs_realtime_pb2

from app.core.config import get_settings
from app.core.database import connection


async def fetch_protobuf(url: str) -> gtfs_realtime_pb2.FeedMessage:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url)
        response.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    return feed


def normalize_vehicle_positions(feed: gtfs_realtime_pb2.FeedMessage) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        trip = entity.vehicle.trip
        position = entity.vehicle.position
        vehicle = entity.vehicle.vehicle
        normalized.append(
            {
                "entity_id": entity.id,
                "recorded_at": datetime.now(UTC),
                "route_id": trip.route_id or None,
                "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
                "start_date": trip.start_date or None,
                "start_time": trip.start_time or None,
                "trip_id": trip.trip_id or None,
                "schedule_relationship": gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(
                    trip.schedule_relationship
                )
                if trip.HasField("schedule_relationship")
                else None,
                "stop_id": entity.vehicle.stop_id or None,
                "current_status": gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(
                    entity.vehicle.current_status
                )
                if entity.vehicle.HasField("current_status")
                else None,
                "latitude": position.latitude,
                "longitude": position.longitude,
                "bearing": position.bearing if position.HasField("bearing") else None,
                "speed": position.speed if position.HasField("speed") else None,
                "vehicle_id": vehicle.id or None,
                "vehicle_label": vehicle.label or None,
            }
        )
    return normalized


def normalize_trip_updates(feed: gtfs_realtime_pb2.FeedMessage) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip = entity.trip_update.trip
        updates = []
        for stop_time_update in entity.trip_update.stop_time_update:
            arrival = stop_time_update.arrival if stop_time_update.HasField("arrival") else None
            departure = stop_time_update.departure if stop_time_update.HasField("departure") else None
            updates.append(
                {
                    "stop_id": stop_time_update.stop_id,
                    "stop_sequence": stop_time_update.stop_sequence,
                    "arrival_delay_seconds": arrival.delay
                    if arrival is not None and arrival.HasField("delay")
                    else None,
                    "departure_delay_seconds": departure.delay
                    if departure is not None and departure.HasField("delay")
                    else None,
                    "arrival_time": arrival.time
                    if arrival is not None and arrival.HasField("time")
                    else None,
                    "departure_time": departure.time
                    if departure is not None and departure.HasField("time")
                    else None,
                }
            )
        normalized.append(
            {
                "entity_id": entity.id,
                "recorded_at": datetime.now(UTC),
                "route_id": trip.route_id or None,
                "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
                "start_date": trip.start_date or None,
                "start_time": trip.start_time or None,
                "trip_id": trip.trip_id or None,
                "vehicle_id": entity.trip_update.vehicle.id if entity.trip_update.HasField("vehicle") else None,
                "stop_time_updates": updates,
            }
        )
    return normalized


async def poll_and_store_realtime() -> dict[str, int]:
    settings = get_settings()
    vehicle_feed, trip_feed = await _fetch_realtime_feeds(
        str(settings.hsl_vehicle_positions_url),
        str(settings.hsl_trip_updates_url),
    )

    vehicle_positions = normalize_vehicle_positions(vehicle_feed)
    trip_updates = normalize_trip_updates(trip_feed)

    async with connection() as conn:
        async with conn.transaction():
            if vehicle_positions:
                await conn.executemany(
                    """
                    INSERT INTO rt_vehicle_positions_raw (
                      recorded_at,
                      entity_id,
                      route_id,
                      direction_id,
                      start_date,
                      start_time,
                      trip_id,
                      stop_id,
                      current_status,
                      schedule_relationship,
                      vehicle_id,
                      vehicle_label,
                      latitude,
                      longitude,
                      bearing,
                      speed
                    )
                    VALUES (
                      $1, $2, $3, $4, $5, $6, $7, $8,
                      $9, $10, $11, $12, $13, $14, $15, $16
                    )
                    """,
                    [
                        (
                            row["recorded_at"],
                            row["entity_id"],
                            row["route_id"],
                            row["direction_id"],
                            row["start_date"],
                            row["start_time"],
                            row["trip_id"],
                            row["stop_id"],
                            row["current_status"],
                            row["schedule_relationship"],
                            row["vehicle_id"],
                            row["vehicle_label"],
                            row["latitude"],
                            row["longitude"],
                            row["bearing"],
                            row["speed"],
                        )
                        for row in vehicle_positions
                    ],
                )

            if trip_updates:
                await conn.executemany(
                    """
                    INSERT INTO rt_trip_updates_raw (
                      recorded_at,
                      entity_id,
                      route_id,
                      direction_id,
                      start_date,
                      start_time,
                      trip_id,
                      vehicle_id,
                      payload
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                    """,
                    [
                        (
                            row["recorded_at"],
                            row["entity_id"],
                            row["route_id"],
                            row["direction_id"],
                            row["start_date"],
                            row["start_time"],
                            row["trip_id"],
                            row["vehicle_id"],
                            json.dumps({"stop_time_updates": row["stop_time_updates"]}),
                        )
                        for row in trip_updates
                    ],
                )

    return {
        "vehicle_positions": len(vehicle_positions),
        "trip_updates": len(trip_updates),
    }


async def _fetch_realtime_feeds(
    vehicle_positions_url: str,
    trip_updates_url: str,
) -> tuple[gtfs_realtime_pb2.FeedMessage, gtfs_realtime_pb2.FeedMessage]:
    async with httpx.AsyncClient(timeout=30) as client:
        vehicle_response, trip_response = await client.get(vehicle_positions_url), await client.get(
            trip_updates_url
        )
        vehicle_response.raise_for_status()
        trip_response.raise_for_status()

    vehicle_feed = gtfs_realtime_pb2.FeedMessage()
    vehicle_feed.ParseFromString(vehicle_response.content)
    trip_feed = gtfs_realtime_pb2.FeedMessage()
    trip_feed.ParseFromString(trip_response.content)
    return vehicle_feed, trip_feed
