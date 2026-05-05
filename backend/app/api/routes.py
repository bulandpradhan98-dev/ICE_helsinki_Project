import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import ORJSONResponse

from app.core.config import get_settings
from app.core.database import fetch, fetchrow
from app.jobs.gtfs_rt_poller import poll_and_store_realtime
from app.jobs.metrics import refresh_matches_and_metrics
from app.jobs.modeling import (
    ensure_model_tables,
    model_status,
    recompute_anomalies,
    recompute_clusters,
    recompute_model_features,
)
from app.jobs.static_gtfs import import_static_gtfs
from app.schemas import (
    FeedValidationRequest,
    FeedValidationResponse,
    IngestionStatus,
    OperationResult,
    RouteMetric,
    StopMetric,
    SummaryResponse,
    SystemStatus,
)
from app.services.analytics import fetch_route_metrics, fetch_stop_metrics, fetch_summary
from app.services.feeds import get_default_feed_config, validate_feed_urls

router = APIRouter(prefix="/api/v1")
BUS_ROUTE_TYPES = [701, 702, 704]


def _mode_route_types(mode: str) -> list[int] | None:
    if mode == "bus":
        return BUS_ROUTE_TYPES
    return None


def _json_payload(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _delay_minutes(stop_update: dict) -> float | None:
    delay_seconds = (
        stop_update.get("arrival_delay_seconds")
        if stop_update.get("arrival_delay_seconds") is not None
        else stop_update.get("departure_delay_seconds")
    )
    return delay_seconds / 60.0 if delay_seconds is not None else None


def _next_stop_from_context(
    *,
    current_status: str | None,
    vehicle_stop_id: str | None,
    vehicle_stop_name: str | None,
    static_next_stop_id: str | None,
    static_next_stop_name: str | None,
    static_next_stop_sequence: int | None,
    upcoming_stops: list[dict[str, object]],
) -> dict[str, object]:
    if current_status in {"IN_TRANSIT_TO", "INCOMING_AT"} and vehicle_stop_id:
        matching_update = next(
            (stop for stop in upcoming_stops if stop.get("stop_id") == vehicle_stop_id),
            {},
        )
        return {
            "stop_id": vehicle_stop_id,
            "stop_name": vehicle_stop_name,
            "stop_sequence": matching_update.get("stop_sequence"),
            "delay_minutes": matching_update.get("delay_minutes"),
            "source": "vehicle_position_target_stop",
        }

    if current_status == "STOPPED_AT" and static_next_stop_id:
        matching_update = next(
            (stop for stop in upcoming_stops if stop.get("stop_id") == static_next_stop_id),
            {},
        )
        return {
            "stop_id": static_next_stop_id,
            "stop_name": static_next_stop_name,
            "stop_sequence": static_next_stop_sequence,
            "delay_minutes": matching_update.get("delay_minutes"),
            "source": "static_gtfs_next_stop",
        }

    for stop in upcoming_stops:
        stop_id = stop.get("stop_id")
        if current_status == "STOPPED_AT" and vehicle_stop_id and stop_id == vehicle_stop_id:
            continue
        return {
            "stop_id": stop_id,
            "stop_name": stop.get("stop_name"),
            "stop_sequence": stop.get("stop_sequence"),
            "delay_minutes": stop.get("delay_minutes"),
            "source": "trip_update_prediction",
        }

    return {
        "stop_id": None,
        "stop_name": None,
        "stop_sequence": None,
        "delay_minutes": None,
        "source": "unavailable",
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/feeds/default")
async def default_feeds():
    return get_default_feed_config()


@router.post("/feeds/validate", response_model=FeedValidationResponse)
async def validate_feeds(payload: FeedValidationRequest) -> FeedValidationResponse:
    return validate_feed_urls(payload)


@router.get("/summary", response_model=SummaryResponse)
async def summary(window_hours: int = 24) -> SummaryResponse:
    return await fetch_summary(window_hours=window_hours)


@router.get("/routes", response_model=list[RouteMetric])
async def routes(window_hours: int = 24) -> list[RouteMetric]:
    return await fetch_route_metrics(window_hours=window_hours)


@router.get("/routes/{route_id}/stops", response_model=list[StopMetric])
async def route_stops(route_id: str, window_hours: int = 24) -> list[StopMetric]:
    return await fetch_stop_metrics(route_id=route_id, window_hours=window_hours)


@router.get("/routes/{route_id}/geometry", response_class=ORJSONResponse)
async def route_geometry(route_id: str):
    rows = await fetch(
        """
        WITH latest_batch AS (
          SELECT id
          FROM gtfs_import_batches
          ORDER BY import_started_at DESC
          LIMIT 1
        ),
        route_match AS (
          SELECT
            gr.batch_id,
            gr.route_id,
            gr.route_short_name,
            gr.route_type,
            gr.route_color,
            gr.route_text_color
          FROM gtfs_routes gr
          CROSS JOIN latest_batch lb
          WHERE gr.batch_id = lb.id
            AND (gr.route_id = $1 OR gr.route_short_name = $1)
            AND gr.route_type = ANY($2::int[])
          LIMIT 1
        ),
        preferred_shape AS (
          SELECT gt.shape_id
          FROM gtfs_trips gt
          JOIN route_match rm
            ON rm.batch_id = gt.batch_id
           AND rm.route_id = gt.route_id
          WHERE gt.shape_id IS NOT NULL
          GROUP BY gt.shape_id
          ORDER BY COUNT(*) DESC
          LIMIT 1
        )
        SELECT
          rm.route_id,
          COALESCE(rm.route_short_name, rm.route_id) AS route_short_name,
          rm.route_type,
          rm.route_color,
          rm.route_text_color,
          ST_AsGeoJSON(ST_MakeLine(gs.geom::geometry ORDER BY gs.shape_pt_sequence)) AS geometry
        FROM route_match rm
        JOIN preferred_shape ps ON TRUE
        JOIN gtfs_shapes gs
          ON gs.batch_id = rm.batch_id
         AND gs.shape_id = ps.shape_id
        GROUP BY rm.route_id, rm.route_short_name, rm.route_type, rm.route_color, rm.route_text_color
        """,
        route_id,
        BUS_ROUTE_TYPES,
    )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No route geometry found for {route_id}.")

    row = rows[0]
    return {
        "type": "Feature",
        "properties": {
          "route_id": row["route_id"],
          "route_short_name": row["route_short_name"],
          "route_type": row["route_type"],
          "route_color": row["route_color"],
          "route_text_color": row["route_text_color"],
        },
        "geometry": json.loads(row["geometry"]),
    }


@router.get("/network/geometry", response_class=ORJSONResponse)
async def network_geometry(limit: int = 48, mode: str = "bus"):
    route_types = _mode_route_types(mode)
    rows = await fetch(
        """
        WITH latest_batch AS (
          SELECT id
          FROM gtfs_import_batches
          ORDER BY import_started_at DESC
          LIMIT 1
        ),
        candidate_routes AS (
          SELECT
            gr.route_id,
            COALESCE(gr.route_short_name, gr.route_id) AS route_short_name,
            gr.route_type,
            gr.route_color,
            gr.route_text_color
          FROM gtfs_routes gr
          JOIN latest_batch lb
            ON lb.id = gr.batch_id
          WHERE ($2::int[] IS NULL OR gr.route_type = ANY($2::int[]))
          ORDER BY gr.route_type, gr.route_id
          LIMIT $1
        ),
        route_shapes AS (
          SELECT
            gt.route_id,
            gt.shape_id,
            COUNT(*) AS trip_count
          FROM gtfs_trips gt
          JOIN latest_batch lb
            ON lb.id = gt.batch_id
          JOIN candidate_routes cr
            ON cr.route_id = gt.route_id
          WHERE gt.shape_id IS NOT NULL
          GROUP BY gt.route_id, gt.shape_id
        ),
        preferred_shapes AS (
          SELECT DISTINCT ON (route_id)
            route_id,
            shape_id
          FROM route_shapes
          ORDER BY route_id, trip_count DESC, shape_id
        )
        SELECT
          cr.route_id,
          cr.route_short_name,
          cr.route_type,
          cr.route_color,
          cr.route_text_color,
          ST_AsGeoJSON(ST_MakeLine(gs.geom::geometry ORDER BY gs.shape_pt_sequence)) AS geometry
        FROM preferred_shapes ps
        JOIN latest_batch lb ON TRUE
        JOIN candidate_routes cr
          ON cr.route_id = ps.route_id
        JOIN gtfs_shapes gs
          ON gs.batch_id = lb.id
         AND gs.shape_id = ps.shape_id
        GROUP BY
          cr.route_id,
          cr.route_short_name,
          cr.route_type,
          cr.route_color,
          cr.route_text_color
        ORDER BY cr.route_type, cr.route_id
        """,
        limit,
        route_types,
    )

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "route_id": row["route_id"],
                    "route_short_name": row["route_short_name"],
                    "route_type": row["route_type"],
                    "route_color": row["route_color"],
                    "route_text_color": row["route_text_color"],
                    "total_events": 0,
                },
                "geometry": json.loads(row["geometry"]),
            }
            for row in rows
        ],
    }


@router.get("/network/vehicles", response_class=ORJSONResponse)
async def network_vehicles(minutes: int = 15, mode: str = "bus"):
    route_types = _mode_route_types(mode)
    rows = await fetch(
        """
        WITH latest_batch AS (
          SELECT id
          FROM gtfs_import_batches
          ORDER BY import_started_at DESC
          LIMIT 1
        ),
        latest_positions AS (
          SELECT DISTINCT ON (COALESCE(vp.vehicle_id, vp.entity_id))
            vp.recorded_at,
            vp.entity_id,
            vp.vehicle_id,
            vp.vehicle_label,
            vp.route_id AS realtime_route_id,
            vp.trip_id,
            vp.direction_id,
            vp.start_date,
            vp.start_time,
            vp.stop_id,
            vp.current_status,
            vp.bearing,
            vp.speed,
            ST_AsGeoJSON(vp.geom::geometry) AS geometry
          FROM rt_vehicle_positions_raw vp
          WHERE vp.recorded_at >= NOW() - ($1 * interval '1 minute')
          ORDER BY COALESCE(vp.vehicle_id, vp.entity_id), vp.recorded_at DESC
        )
        SELECT
          lp.recorded_at,
          lp.entity_id,
          lp.vehicle_id,
          lp.vehicle_label,
          lp.realtime_route_id,
          lp.trip_id,
          lp.direction_id,
          lp.start_date,
          lp.start_time,
          lp.stop_id,
          st.stop_name AS stop_name,
          lp.current_status,
          lp.bearing,
          lp.speed,
          lp.geometry,
          COALESCE(gr.route_short_name, gr.route_id) AS route_short_name,
          gr.route_type,
          gr.route_color,
          tu.recorded_at AS trip_update_recorded_at,
          tu.payload,
          static_next.stop_id AS static_next_stop_id,
          static_next.stop_name AS static_next_stop_name,
          static_next.stop_sequence AS static_next_stop_sequence
        FROM latest_positions lp
        CROSS JOIN latest_batch lb
        LEFT JOIN gtfs_stops st
          ON st.batch_id = lb.id
         AND st.stop_id = lp.stop_id
        LEFT JOIN gtfs_routes gr
          ON gr.batch_id = lb.id
         AND (gr.route_id = lp.realtime_route_id OR gr.route_short_name = lp.realtime_route_id)
        LEFT JOIN LATERAL (
          SELECT
            tu.recorded_at,
            tu.payload
          FROM rt_trip_updates_raw tu
          WHERE tu.recorded_at >= NOW() - ($1 * interval '1 minute')
            AND tu.route_id = lp.realtime_route_id
            AND (
              (lp.vehicle_id IS NOT NULL AND tu.vehicle_id = lp.vehicle_id)
              OR (lp.vehicle_id IS NULL AND tu.entity_id = lp.entity_id)
              OR (
                tu.direction_id IS NOT NULL
                AND lp.direction_id IS NOT NULL
                AND tu.direction_id = lp.direction_id
                AND tu.start_date = lp.start_date
                AND tu.start_time = lp.start_time
              )
            )
          ORDER BY tu.recorded_at DESC
            LIMIT 1
        ) tu ON TRUE
        LEFT JOIN LATERAL (
          SELECT
            next_st.stop_id,
            next_stop.stop_name,
            next_st.stop_sequence
          FROM gtfs_trips gt
          JOIN gtfs_stop_times current_st
            ON current_st.batch_id = gt.batch_id
           AND current_st.trip_id = gt.trip_id
           AND current_st.stop_id = lp.stop_id
          JOIN gtfs_stop_times next_st
            ON next_st.batch_id = gt.batch_id
           AND next_st.trip_id = gt.trip_id
           AND next_st.stop_sequence > current_st.stop_sequence
          JOIN gtfs_stops next_stop
            ON next_stop.batch_id = gt.batch_id
           AND next_stop.stop_id = next_st.stop_id
          WHERE gt.batch_id = lb.id
            AND gt.route_id = gr.route_id
            AND gt.direction_id = lp.direction_id
            AND gt.start_time = lp.start_time
          ORDER BY next_st.stop_sequence
          LIMIT 1
        ) static_next ON TRUE
        WHERE ($2::int[] IS NULL OR gr.route_type = ANY($2::int[]))
          AND gr.route_id IS NOT NULL
          AND st.stop_name IS NOT NULL
          AND lp.realtime_route_id IS NOT NULL
          AND lp.current_status IS NOT NULL
          AND tu.recorded_at IS NOT NULL
          AND jsonb_array_length(COALESCE(tu.payload->'stop_time_updates', '[]'::jsonb)) > 0
        ORDER BY lp.recorded_at DESC
        """,
        minutes,
        route_types,
    )

    stop_ids: set[str] = set()
    upcoming_by_entity: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        payload = _json_payload(row["payload"])
        updates = payload.get("stop_time_updates", [])
        if not isinstance(updates, list):
            updates = []
        simplified_updates: list[dict[str, object]] = []
        for stop_update in updates[:4]:
            if not isinstance(stop_update, dict):
                continue
            stop_id = stop_update.get("stop_id")
            if isinstance(stop_id, str) and stop_id:
                stop_ids.add(stop_id)
            simplified_updates.append(
                {
                    "stop_id": stop_id,
                    "stop_sequence": stop_update.get("stop_sequence"),
                    "delay_minutes": _delay_minutes(stop_update),
                }
            )
        upcoming_by_entity[row["entity_id"]] = simplified_updates

    stop_name_lookup: dict[str, str] = {}
    if stop_ids:
        batch_id = await fetchrow(
            """
            SELECT id
            FROM gtfs_import_batches
            ORDER BY import_started_at DESC
            LIMIT 1
            """
        )
        if batch_id:
            stop_rows = await fetch(
                """
                SELECT stop_id, stop_name
                FROM gtfs_stops
                WHERE batch_id = $1
                  AND stop_id = ANY($2::text[])
                """,
                batch_id["id"],
                list(stop_ids),
            )
            stop_name_lookup = {row["stop_id"]: row["stop_name"] for row in stop_rows}

    return {
        "type": "FeatureCollection",
        "meta": {
            "vehicle_count": len(rows),
            "latest_recorded_at": rows[0]["recorded_at"].isoformat() if rows else None,
            "mode": mode,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "entity_id": row["entity_id"],
                    "vehicle_id": row["vehicle_id"],
                    "vehicle_label": row["vehicle_label"] or row["vehicle_id"] or row["entity_id"],
                    "realtime_route_id": row["realtime_route_id"],
                    "route_short_name": row["route_short_name"],
                    "route_type": row["route_type"],
                    "route_color": row["route_color"],
                    "trip_id": row["trip_id"],
                    "direction_id": row["direction_id"],
                    "start_date": row["start_date"],
                    "start_time": row["start_time"],
                    "stop_id": row["stop_id"],
                    "stop_name": row["stop_name"],
                    "current_status": row["current_status"],
                    "bearing": row["bearing"],
                    "speed": row["speed"],
                    "recorded_at": row["recorded_at"].isoformat(),
                    "trip_update_recorded_at": (
                        row["trip_update_recorded_at"].isoformat() if row["trip_update_recorded_at"] else None
                    ),
                    **(
                        lambda upcoming_stops, next_stop: {
                            "next_stop_id": next_stop["stop_id"],
                            "next_stop_name": next_stop["stop_name"],
                            "next_stop_sequence": next_stop["stop_sequence"],
                            "next_stop_delay_minutes": (
                                round(float(next_stop["delay_minutes"]), 2)
                                if next_stop["delay_minutes"] is not None
                                else None
                            ),
                            "next_stop_source": next_stop["source"],
                            "upcoming_stops": upcoming_stops,
                        }
                    )(
                        [
                            {
                                "stop_id": stop_update["stop_id"],
                                "stop_name": stop_name_lookup.get(stop_update["stop_id"], stop_update["stop_id"]),
                                "stop_sequence": stop_update["stop_sequence"],
                                "delay_minutes": (
                                    round(float(stop_update["delay_minutes"]), 2)
                                    if stop_update["delay_minutes"] is not None
                                    else None
                                ),
                            }
                            for stop_update in upcoming_by_entity.get(row["entity_id"], [])
                        ],
                        _next_stop_from_context(
                            current_status=row["current_status"],
                            vehicle_stop_id=row["stop_id"],
                            vehicle_stop_name=row["stop_name"],
                            static_next_stop_id=row["static_next_stop_id"],
                            static_next_stop_name=row["static_next_stop_name"],
                            static_next_stop_sequence=row["static_next_stop_sequence"],
                            upcoming_stops=[
                                {
                                    "stop_id": stop_update["stop_id"],
                                    "stop_name": stop_name_lookup.get(stop_update["stop_id"], stop_update["stop_id"]),
                                    "stop_sequence": stop_update["stop_sequence"],
                                    "delay_minutes": stop_update["delay_minutes"],
                                }
                                for stop_update in upcoming_by_entity.get(row["entity_id"], [])
                            ],
                        ),
                    ),
                },
                "geometry": json.loads(row["geometry"]),
            }
            for row in rows
        ],
    }


@router.get("/routes/{route_id}/comparison", response_class=ORJSONResponse)
async def route_comparison(route_id: str):
    settings = get_settings()
    route_match = await fetchrow(
        """
        WITH latest_batch AS (
          SELECT id
          FROM gtfs_import_batches
          ORDER BY import_started_at DESC
          LIMIT 1
        )
        SELECT gr.batch_id, gr.route_id, COALESCE(gr.route_short_name, gr.route_id) AS route_short_name
        FROM gtfs_routes gr
        CROSS JOIN latest_batch lb
        WHERE gr.batch_id = lb.id
          AND (gr.route_id = $1 OR gr.route_short_name = $1)
          AND gr.route_type = ANY($2::int[])
        LIMIT 1
        """,
        route_id,
        BUS_ROUTE_TYPES,
    )

    if route_match is None:
        raise HTTPException(status_code=404, detail=f"No route found for {route_id}.")

    rows = await fetch(
        """
        WITH static_trip AS (
          SELECT gt.trip_id
          FROM gtfs_trips gt
          JOIN gtfs_stop_times gst
            ON gst.batch_id = gt.batch_id
           AND gst.trip_id = gt.trip_id
          WHERE gt.batch_id = $3
            AND gt.route_id = $1
          GROUP BY gt.trip_id
          ORDER BY COUNT(*) DESC, gt.trip_id
          LIMIT 1
        ),
        static_stops AS (
          SELECT
            gst.stop_sequence,
            gst.stop_id,
            gst.arrival_time,
            gst.departure_time,
            gs.stop_name,
            ST_AsGeoJSON(gs.geom::geometry) AS geometry
          FROM gtfs_stop_times gst
          JOIN static_trip st
            ON st.trip_id = gst.trip_id
          JOIN gtfs_stops gs
            ON gs.batch_id = gst.batch_id
           AND gs.stop_id = gst.stop_id
          WHERE gst.batch_id = $3
          ORDER BY gst.stop_sequence
        ),
        latest_route_update AS (
          SELECT MAX(recorded_at) AS latest_recorded_at
          FROM rt_trip_updates_raw
          WHERE route_id IN ($1, $2)
        ),
        expanded_updates AS (
          SELECT
            tu.recorded_at,
            tu.entity_id,
            tu.vehicle_id,
            tu.trip_id,
            tu.route_id AS realtime_route_id,
            tu.direction_id,
            tu.start_date,
            tu.start_time,
            NULLIF(stop_update->>'stop_id', '') AS stop_id,
            NULLIF(stop_update->>'stop_sequence', '')::INTEGER AS stop_sequence,
            COALESCE(
              NULLIF(stop_update->>'arrival_delay_seconds', '')::DOUBLE PRECISION,
              NULLIF(stop_update->>'departure_delay_seconds', '')::DOUBLE PRECISION
            ) / 60.0 AS raw_delay_minutes,
            NULLIF(stop_update->>'arrival_time', '')::DOUBLE PRECISION AS arrival_time_epoch,
            NULLIF(stop_update->>'departure_time', '')::DOUBLE PRECISION AS departure_time_epoch,
            CASE
              WHEN NULLIF(stop_update->>'arrival_time', '') IS NOT NULL
               AND stop_time_match.arrival_time IS NOT NULL
               AND tu.start_date IS NOT NULL
              THEN EXTRACT(
                EPOCH FROM (
                  (to_timestamp(NULLIF(stop_update->>'arrival_time', '')::DOUBLE PRECISION) AT TIME ZONE 'Europe/Helsinki')
                  - (
                    to_date(tu.start_date, 'YYYYMMDD')
                    + split_part(stop_time_match.arrival_time, ':', 1)::integer * interval '1 hour'
                    + split_part(stop_time_match.arrival_time, ':', 2)::integer * interval '1 minute'
                    + split_part(stop_time_match.arrival_time, ':', 3)::double precision * interval '1 second'
                  )
                )
              ) / 60.0
              WHEN NULLIF(stop_update->>'departure_time', '') IS NOT NULL
               AND stop_time_match.departure_time IS NOT NULL
               AND tu.start_date IS NOT NULL
              THEN EXTRACT(
                EPOCH FROM (
                  (to_timestamp(NULLIF(stop_update->>'departure_time', '')::DOUBLE PRECISION) AT TIME ZONE 'Europe/Helsinki')
                  - (
                    to_date(tu.start_date, 'YYYYMMDD')
                    + split_part(stop_time_match.departure_time, ':', 1)::integer * interval '1 hour'
                    + split_part(stop_time_match.departure_time, ':', 2)::integer * interval '1 minute'
                    + split_part(stop_time_match.departure_time, ':', 3)::double precision * interval '1 second'
                  )
                )
              ) / 60.0
              ELSE NULLIF(
                COALESCE(
                  NULLIF(stop_update->>'arrival_delay_seconds', '')::DOUBLE PRECISION,
                  NULLIF(stop_update->>'departure_delay_seconds', '')::DOUBLE PRECISION
                ) / 60.0,
                0
              )
            END AS delay_minutes
          FROM rt_trip_updates_raw tu
          CROSS JOIN latest_route_update lru
          CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(tu.payload->'stop_time_updates', '[]'::jsonb)
          ) AS stop_update
          LEFT JOIN LATERAL (
            SELECT gt.trip_id
            FROM gtfs_trips gt
            JOIN gtfs_routes gr
              ON gr.batch_id = gt.batch_id
             AND gr.route_id = gt.route_id
            WHERE gt.batch_id = $3
              AND (gr.route_id = tu.route_id OR gr.route_short_name = tu.route_id)
              AND (gt.direction_id IS NOT DISTINCT FROM tu.direction_id)
              AND gt.start_time = tu.start_time
            LIMIT 1
          ) AS trip_match ON TRUE
          LEFT JOIN gtfs_stop_times stop_time_match
            ON stop_time_match.batch_id = $3
           AND stop_time_match.trip_id = trip_match.trip_id
           AND (
             (NULLIF(stop_update->>'stop_id', '') IS NOT NULL AND stop_time_match.stop_id = NULLIF(stop_update->>'stop_id', ''))
             OR (
               NULLIF(stop_update->>'stop_id', '') IS NULL
               AND stop_time_match.stop_sequence = NULLIF(stop_update->>'stop_sequence', '')::INTEGER
             )
           )
          WHERE tu.route_id IN ($1, $2)
            AND tu.recorded_at >= COALESCE(lru.latest_recorded_at - interval '5 minutes', tu.recorded_at)
        )
        SELECT
          ss.stop_sequence,
          ss.stop_id,
          ss.stop_name,
          ss.geometry,
          live.recorded_at,
          live.vehicle_id,
          live.trip_id,
          live.entity_id,
          live.realtime_route_id,
          live.delay_minutes,
          COALESCE(live.update_count, 0) AS update_count
        FROM static_stops ss
        LEFT JOIN LATERAL (
          SELECT
            eu.recorded_at,
            eu.vehicle_id,
            eu.trip_id,
            eu.entity_id,
            eu.realtime_route_id,
            eu.delay_minutes,
            (
              SELECT COUNT(*)
              FROM expanded_updates ec
              CROSS JOIN latest_route_update lru
              WHERE ec.recorded_at >= COALESCE(lru.latest_recorded_at - interval '5 minutes', ec.recorded_at)
                AND (
                  (ec.stop_id IS NOT NULL AND ec.stop_id = ss.stop_id)
                  OR (ec.stop_id IS NULL AND ec.stop_sequence = ss.stop_sequence)
                )
            ) AS update_count
          FROM expanded_updates eu
          CROSS JOIN latest_route_update lru
          WHERE eu.recorded_at >= COALESCE(lru.latest_recorded_at - interval '5 minutes', eu.recorded_at)
            AND (
              (eu.stop_id IS NOT NULL AND eu.stop_id = ss.stop_id)
              OR (eu.stop_id IS NULL AND eu.stop_sequence = ss.stop_sequence)
            )
          ORDER BY eu.recorded_at DESC
          LIMIT 1
        ) AS live ON TRUE
        ORDER BY ss.stop_sequence
        """,
        route_match["route_id"],
        route_match["route_short_name"],
        route_match["batch_id"],
    )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No static stop sequence found for {route_id}.")

    status_counts = {
        "scheduled_only": 0,
        "early": 0,
        "on_time": 0,
        "late": 0,
    }
    latest_recorded_at = None
    features = []

    for row in rows:
        delay_minutes = row["delay_minutes"]
        live_status = "scheduled_only"
        if delay_minutes is not None:
            if delay_minutes < settings.schedule_early_threshold_minutes:
                live_status = "early"
            elif delay_minutes > settings.schedule_late_threshold_minutes:
                live_status = "late"
            else:
                live_status = "on_time"

        status_counts[live_status] += 1
        recorded_at = row["recorded_at"]
        if recorded_at and (latest_recorded_at is None or recorded_at > latest_recorded_at):
            latest_recorded_at = recorded_at

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "stop_id": row["stop_id"],
                    "stop_name": row["stop_name"],
                    "stop_sequence": row["stop_sequence"],
                    "live_status": live_status,
                    "delay_minutes": round(float(delay_minutes), 2) if delay_minutes is not None else None,
                    "recorded_at": recorded_at.isoformat() if recorded_at else None,
                    "vehicle_id": row["vehicle_id"],
                    "trip_id": row["trip_id"],
                    "entity_id": row["entity_id"],
                    "realtime_route_id": row["realtime_route_id"],
                    "update_count": int(row["update_count"]),
                },
                "geometry": json.loads(row["geometry"]),
            }
        )

    return {
        "type": "FeatureCollection",
        "meta": {
            "route_id": route_match["route_id"],
            "route_short_name": route_match["route_short_name"],
            "stop_count": len(features),
            "latest_recorded_at": latest_recorded_at.isoformat() if latest_recorded_at else None,
            "status_counts": status_counts,
        },
        "features": features,
    }


@router.get("/routes/{route_id}/vehicles", response_class=ORJSONResponse)
async def route_vehicles(route_id: str):
    route_match = await fetchrow(
        """
        WITH latest_batch AS (
          SELECT id
          FROM gtfs_import_batches
          ORDER BY import_started_at DESC
          LIMIT 1
        )
        SELECT gr.batch_id, gr.route_id, COALESCE(gr.route_short_name, gr.route_id) AS route_short_name
        FROM gtfs_routes gr
        CROSS JOIN latest_batch lb
        WHERE gr.batch_id = lb.id
          AND (gr.route_id = $1 OR gr.route_short_name = $1)
          AND gr.route_type = ANY($2::int[])
        LIMIT 1
        """,
        route_id,
        BUS_ROUTE_TYPES,
    )

    if route_match is None:
        raise HTTPException(status_code=404, detail=f"No route found for {route_id}.")

    rows = await fetch(
        """
        WITH latest_positions AS (
          SELECT DISTINCT ON (COALESCE(vp.vehicle_id, vp.entity_id))
            vp.recorded_at,
            vp.entity_id,
            vp.vehicle_id,
            vp.vehicle_label,
            vp.route_id AS realtime_route_id,
            vp.trip_id,
            vp.direction_id,
            vp.start_date,
            vp.start_time,
            vp.stop_id,
            vp.current_status,
            vp.bearing,
            vp.speed,
            ST_AsGeoJSON(vp.geom::geometry) AS geometry
          FROM rt_vehicle_positions_raw vp
          WHERE (vp.route_id = $1 OR vp.route_id = $2)
            AND vp.recorded_at >= NOW() - interval '15 minutes'
          ORDER BY COALESCE(vp.vehicle_id, vp.entity_id), vp.recorded_at DESC
        )
        SELECT
          lp.recorded_at,
          lp.entity_id,
          lp.vehicle_id,
          lp.vehicle_label,
          lp.realtime_route_id,
          lp.trip_id,
          lp.direction_id,
          lp.start_date,
          lp.start_time,
          lp.stop_id,
          st.stop_name AS stop_name,
          lp.current_status,
          lp.bearing,
          lp.speed,
          lp.geometry,
          tu.trip_id AS update_trip_id,
          tu.recorded_at AS trip_update_recorded_at,
          tu.payload,
          static_next.stop_id AS static_next_stop_id,
          static_next.stop_name AS static_next_stop_name,
          static_next.stop_sequence AS static_next_stop_sequence
        FROM latest_positions lp
        LEFT JOIN gtfs_stops st
          ON st.batch_id = $3
         AND st.stop_id = lp.stop_id
        LEFT JOIN LATERAL (
          SELECT
            tu.recorded_at,
            tu.trip_id,
            tu.payload
          FROM rt_trip_updates_raw tu
          WHERE tu.recorded_at >= NOW() - interval '15 minutes'
            AND (tu.route_id = $1 OR tu.route_id = $2)
            AND (
              (lp.vehicle_id IS NOT NULL AND tu.vehicle_id = lp.vehicle_id)
              OR (lp.vehicle_id IS NULL AND tu.entity_id = lp.entity_id)
              OR (
                tu.direction_id IS NOT NULL
                AND lp.direction_id IS NOT NULL
                AND tu.direction_id = lp.direction_id
                AND tu.start_date = lp.start_date
                AND tu.start_time = lp.start_time
              )
            )
          ORDER BY tu.recorded_at DESC
          LIMIT 1
        ) tu ON TRUE
        LEFT JOIN LATERAL (
          SELECT
            next_st.stop_id,
            next_stop.stop_name,
            next_st.stop_sequence
          FROM gtfs_trips gt
          JOIN gtfs_stop_times current_st
            ON current_st.batch_id = gt.batch_id
           AND current_st.trip_id = gt.trip_id
           AND current_st.stop_id = lp.stop_id
          JOIN gtfs_stop_times next_st
            ON next_st.batch_id = gt.batch_id
           AND next_st.trip_id = gt.trip_id
           AND next_st.stop_sequence > current_st.stop_sequence
          JOIN gtfs_stops next_stop
            ON next_stop.batch_id = gt.batch_id
           AND next_stop.stop_id = next_st.stop_id
          WHERE gt.batch_id = $3
            AND gt.route_id = $1
            AND gt.direction_id = lp.direction_id
            AND gt.start_time = lp.start_time
          ORDER BY next_st.stop_sequence
          LIMIT 1
        ) static_next ON TRUE
        WHERE st.stop_name IS NOT NULL
          AND lp.realtime_route_id IS NOT NULL
          AND lp.current_status IS NOT NULL
          AND tu.recorded_at IS NOT NULL
          AND jsonb_array_length(COALESCE(tu.payload->'stop_time_updates', '[]'::jsonb)) > 0
        ORDER BY lp.recorded_at DESC
        """,
        route_match["route_id"],
        route_match["route_short_name"],
        route_match["batch_id"],
    )

    stop_ids: set[str] = set()
    upcoming_by_entity: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        payload = _json_payload(row["payload"])
        updates = payload.get("stop_time_updates", [])
        if not isinstance(updates, list):
            updates = []
        simplified_updates: list[dict[str, object]] = []
        for stop_update in updates[:5]:
            if not isinstance(stop_update, dict):
                continue
            stop_id = stop_update.get("stop_id")
            if isinstance(stop_id, str) and stop_id:
                stop_ids.add(stop_id)
            simplified_updates.append(
                {
                    "stop_id": stop_id,
                    "stop_sequence": stop_update.get("stop_sequence"),
                    "delay_minutes": _delay_minutes(stop_update),
                }
            )
        upcoming_by_entity[row["entity_id"]] = simplified_updates

    stop_name_lookup: dict[str, str] = {}
    if stop_ids:
        stop_rows = await fetch(
            """
            SELECT stop_id, stop_name
            FROM gtfs_stops
            WHERE batch_id = $1
              AND stop_id = ANY($2::text[])
            """,
            route_match["batch_id"],
            list(stop_ids),
        )
        stop_name_lookup = {row["stop_id"]: row["stop_name"] for row in stop_rows}

    return {
        "type": "FeatureCollection",
        "meta": {
            "route_id": route_match["route_id"],
            "route_short_name": route_match["route_short_name"],
            "vehicle_count": len(rows),
            "latest_recorded_at": rows[0]["recorded_at"].isoformat() if rows else None,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "entity_id": row["entity_id"],
                    "vehicle_id": row["vehicle_id"],
                    "vehicle_label": row["vehicle_label"] or row["vehicle_id"] or row["entity_id"],
                    "realtime_route_id": row["realtime_route_id"],
                    "trip_id": row["update_trip_id"] or row["trip_id"],
                    "direction_id": row["direction_id"],
                    "start_date": row["start_date"],
                    "start_time": row["start_time"],
                    "stop_id": row["stop_id"],
                    "stop_name": row["stop_name"],
                    "current_status": row["current_status"],
                    "bearing": row["bearing"],
                    "speed": row["speed"],
                    "recorded_at": row["recorded_at"].isoformat(),
                    "trip_update_recorded_at": (
                        row["trip_update_recorded_at"].isoformat() if row["trip_update_recorded_at"] else None
                    ),
                    **(
                        lambda upcoming_stops, next_stop: {
                            "next_stop_id": next_stop["stop_id"],
                            "next_stop_name": next_stop["stop_name"],
                            "next_stop_sequence": next_stop["stop_sequence"],
                            "next_stop_delay_minutes": (
                                round(float(next_stop["delay_minutes"]), 2)
                                if next_stop["delay_minutes"] is not None
                                else None
                            ),
                            "next_stop_source": next_stop["source"],
                            "upcoming_stops": upcoming_stops,
                        }
                    )(
                        [
                            {
                                "stop_id": stop_update["stop_id"],
                                "stop_name": stop_name_lookup.get(stop_update["stop_id"], stop_update["stop_id"]),
                                "stop_sequence": stop_update["stop_sequence"],
                                "delay_minutes": (
                                    round(float(stop_update["delay_minutes"]), 2)
                                    if stop_update["delay_minutes"] is not None
                                    else None
                                ),
                            }
                            for stop_update in upcoming_by_entity.get(row["entity_id"], [])
                        ],
                        _next_stop_from_context(
                            current_status=row["current_status"],
                            vehicle_stop_id=row["stop_id"],
                            vehicle_stop_name=row["stop_name"],
                            static_next_stop_id=row["static_next_stop_id"],
                            static_next_stop_name=row["static_next_stop_name"],
                            static_next_stop_sequence=row["static_next_stop_sequence"],
                            upcoming_stops=[
                                {
                                    "stop_id": stop_update["stop_id"],
                                    "stop_name": stop_name_lookup.get(stop_update["stop_id"], stop_update["stop_id"]),
                                    "stop_sequence": stop_update["stop_sequence"],
                                    "delay_minutes": stop_update["delay_minutes"],
                                }
                                for stop_update in upcoming_by_entity.get(row["entity_id"], [])
                            ],
                        ),
                    ),
                },
                "geometry": json.loads(row["geometry"]),
            }
            for row in rows
        ],
    }


@router.get("/models/status")
async def models_status():
    return await model_status()


@router.get("/models/runs")
async def model_runs(limit: int = 12):
    await ensure_model_tables()
    rows = await fetch(
        """
        SELECT
          id,
          model_family,
          algorithm,
          started_at,
          completed_at,
          status,
          rows_used,
          selected_params,
          metrics,
          notes
        FROM model_run_metadata
        ORDER BY started_at DESC
        LIMIT $1
        """,
        limit,
    )
    return {
        "runs": [
            {
                "id": row["id"],
                "model_family": row["model_family"],
                "algorithm": row["algorithm"],
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "status": row["status"],
                "rows_used": row["rows_used"],
                "selected_params": row["selected_params"] or {},
                "metrics": row["metrics"] or {},
                "notes": row["notes"],
            }
            for row in rows
        ]
    }


@router.post("/models/features/recompute", response_model=OperationResult)
async def recompute_features() -> OperationResult:
    try:
        details = await recompute_model_features(mode="bus")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Feature recompute failed: {exc}") from exc

    return OperationResult(
        ok=True,
        message="Model feature windows recomputed.",
        details=details,
    )


@router.post("/models/clusters/recompute", response_model=OperationResult)
async def recompute_model_clusters() -> OperationResult:
    try:
        details = await recompute_clusters(mode="bus")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cluster recompute failed: {exc}") from exc

    return OperationResult(
        ok=True,
        message="KMeans and DBSCAN clustering recomputed.",
        details=details,
    )


@router.post("/models/anomalies/recompute", response_model=OperationResult)
async def recompute_model_anomalies() -> OperationResult:
    try:
        details = await recompute_anomalies(mode="bus")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Anomaly recompute failed: {exc}") from exc

    return OperationResult(
        ok=True,
        message="Isolation Forest and LOF anomaly scores recomputed.",
        details=details,
    )


@router.get("/models/clusters", response_class=ORJSONResponse)
async def model_clusters(limit: int = 1200, hotspots_only: bool = False):
    await ensure_model_tables()
    rows = await fetch(
        """
        WITH latest_model_date AS (
          SELECT MAX(model_date) AS model_date
          FROM cluster_assignments_daily
        )
        SELECT
          cad.model_date,
          cad.route_id,
          cad.route_short_name,
          cad.route_type,
          cad.stop_id,
          cad.stop_name,
          cad.latitude,
          cad.longitude,
          cad.kmeans_cluster,
          cad.dbscan_cluster,
          cad.dbscan_is_hotspot,
          cad.reliability_label,
          cad.mean_delay_minutes,
          cad.p95_abs_delay_minutes,
          cad.prediction_coverage_ratio,
          cad.sample_count,
          cad.updated_at
        FROM cluster_assignments_daily cad
        JOIN latest_model_date lmd
          ON lmd.model_date = cad.model_date
        WHERE ($1::boolean = FALSE OR cad.dbscan_is_hotspot = TRUE)
          AND cad.route_type = ANY($3::int[])
          AND cad.latitude IS NOT NULL
          AND cad.longitude IS NOT NULL
        ORDER BY cad.dbscan_is_hotspot DESC, cad.p95_abs_delay_minutes DESC, cad.mean_delay_minutes DESC
        LIMIT $2
        """,
        hotspots_only,
        limit,
        BUS_ROUTE_TYPES,
    )
    return {
        "type": "FeatureCollection",
        "meta": {
            "count": len(rows),
            "hotspots_only": hotspots_only,
            "model_date": rows[0]["model_date"].isoformat() if rows else None,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "route_id": row["route_id"],
                    "route_short_name": row["route_short_name"],
                    "route_type": row["route_type"],
                    "stop_id": row["stop_id"],
                    "stop_name": row["stop_name"],
                    "kmeans_cluster": row["kmeans_cluster"],
                    "dbscan_cluster": row["dbscan_cluster"],
                    "dbscan_is_hotspot": row["dbscan_is_hotspot"],
                    "reliability_label": row["reliability_label"],
                    "mean_delay_minutes": round(float(row["mean_delay_minutes"]), 2),
                    "p95_abs_delay_minutes": round(float(row["p95_abs_delay_minutes"]), 2),
                    "prediction_coverage_ratio": round(float(row["prediction_coverage_ratio"]), 3),
                    "sample_count": row["sample_count"],
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]],
                },
            }
            for row in rows
        ],
    }


@router.get("/models/anomalies/live", response_class=ORJSONResponse)
async def live_anomalies(hours: int = 3, limit: int = 500):
    await ensure_model_tables()
    rows = await fetch(
        """
        SELECT
          bucket,
          route_id,
          route_short_name,
          route_type,
          stop_id,
          stop_name,
          latitude,
          longitude,
          isolation_forest_score,
          isolation_forest_is_anomaly,
          lof_score,
          lof_is_anomaly,
          pseudo_label,
          anomaly_reason,
          mean_delay_minutes,
          prediction_coverage_ratio,
          feed_age_seconds,
          updated_at
        FROM anomaly_scores_live
        WHERE bucket >= NOW() - ($1 * interval '1 hour')
          AND route_type = ANY($3::int[])
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
          AND (isolation_forest_is_anomaly OR lof_is_anomaly OR pseudo_label)
        ORDER BY bucket DESC, GREATEST(COALESCE(isolation_forest_score, 0), COALESCE(lof_score, 0)) DESC
        LIMIT $2
        """,
        hours,
        limit,
        BUS_ROUTE_TYPES,
    )
    return {
        "type": "FeatureCollection",
        "meta": {
            "count": len(rows),
            "window_hours": hours,
            "latest_bucket": rows[0]["bucket"].isoformat() if rows else None,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "bucket": row["bucket"].isoformat(),
                    "route_id": row["route_id"],
                    "route_short_name": row["route_short_name"],
                    "route_type": row["route_type"],
                    "stop_id": row["stop_id"],
                    "stop_name": row["stop_name"],
                    "isolation_forest_score": (
                        round(float(row["isolation_forest_score"]), 4)
                        if row["isolation_forest_score"] is not None
                        else None
                    ),
                    "isolation_forest_is_anomaly": row["isolation_forest_is_anomaly"],
                    "lof_score": round(float(row["lof_score"]), 4) if row["lof_score"] is not None else None,
                    "lof_is_anomaly": row["lof_is_anomaly"],
                    "pseudo_label": row["pseudo_label"],
                    "anomaly_reason": row["anomaly_reason"],
                    "mean_delay_minutes": round(float(row["mean_delay_minutes"]), 2),
                    "prediction_coverage_ratio": round(float(row["prediction_coverage_ratio"]), 3),
                    "feed_age_seconds": round(float(row["feed_age_seconds"]), 1),
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]],
                },
            }
            for row in rows
        ],
    }


@router.get("/routes/{route_id}/model-insights")
async def route_model_insights(route_id: str):
    await ensure_model_tables()
    row = await fetchrow(
        """
        WITH route_cluster_rows AS (
          SELECT *
          FROM cluster_assignments_daily
          WHERE model_date = (SELECT MAX(model_date) FROM cluster_assignments_daily)
            AND (route_id = $1 OR route_short_name = $1)
        ),
        route_feature_rows AS (
          SELECT *
          FROM model_feature_windows
          WHERE bucket >= NOW() - interval '24 hours'
            AND (route_id = $1 OR route_short_name = $1)
        ),
        cluster_summary AS (
          SELECT
            COUNT(*) AS stops_clustered,
            COUNT(*) FILTER (WHERE dbscan_is_hotspot) AS hotspots,
            AVG(mean_delay_minutes) AS avg_cluster_delay,
            AVG(p95_abs_delay_minutes) AS avg_p95_abs_delay,
            AVG(prediction_coverage_ratio) AS avg_prediction_coverage
          FROM route_cluster_rows
        ),
        feature_summary AS (
          SELECT
            COUNT(*) AS feature_windows,
            AVG(mean_delay_minutes) AS avg_feature_delay,
            AVG(p95_abs_delay_minutes) AS avg_feature_p95_abs_delay,
            AVG(prediction_coverage_ratio) AS avg_feature_prediction_coverage
          FROM route_feature_rows
        ),
        reliability_counts AS (
          SELECT COALESCE(jsonb_object_agg(reliability_label, label_count), '{}'::jsonb) AS reliability_counts
          FROM (
            SELECT reliability_label, COUNT(*) AS label_count
            FROM route_cluster_rows
            GROUP BY reliability_label
          ) counts
        ),
        anomaly_summary AS (
          SELECT
            COUNT(*) AS active_anomalies,
            MAX(bucket) AS latest_anomaly_bucket,
            AVG(mean_delay_minutes) AS avg_anomaly_delay,
            jsonb_agg(
              jsonb_build_object(
                'bucket', bucket,
                'stop_id', stop_id,
                'stop_name', stop_name,
                'reason', anomaly_reason,
                'mean_delay_minutes', mean_delay_minutes,
                'isolation_forest_score', isolation_forest_score,
                'lof_score', lof_score
              )
              ORDER BY bucket DESC
            ) FILTER (WHERE bucket IS NOT NULL) AS recent_anomalies
          FROM anomaly_scores_live
          WHERE bucket >= NOW() - interval '3 hours'
            AND (route_id = $1 OR route_short_name = $1)
            AND (isolation_forest_is_anomaly OR lof_is_anomaly OR pseudo_label)
        )
        SELECT
          COALESCE(cs.stops_clustered, 0) AS stops_clustered,
          COALESCE(cs.hotspots, 0) AS hotspots,
          COALESCE(fs.feature_windows, 0) AS feature_windows,
          COALESCE(cs.avg_cluster_delay, fs.avg_feature_delay, 0) AS avg_cluster_delay,
          COALESCE(cs.avg_p95_abs_delay, fs.avg_feature_p95_abs_delay, 0) AS avg_p95_abs_delay,
          COALESCE(cs.avg_prediction_coverage, fs.avg_feature_prediction_coverage, 0) AS avg_prediction_coverage,
          COALESCE(rc.reliability_counts, '{}'::jsonb) AS reliability_counts,
          COALESCE(ans.active_anomalies, 0) AS active_anomalies,
          ans.latest_anomaly_bucket,
          COALESCE(ans.avg_anomaly_delay, 0) AS avg_anomaly_delay,
          COALESCE(ans.recent_anomalies, '[]'::jsonb) AS recent_anomalies
        FROM cluster_summary cs
        CROSS JOIN feature_summary fs
        CROSS JOIN reliability_counts rc
        CROSS JOIN anomaly_summary ans
        """,
        route_id,
    )
    if row is None:
        return {
            "route_id": route_id,
            "feature_windows": 0,
            "stops_clustered": 0,
            "hotspots": 0,
            "active_anomalies": 0,
            "recent_anomalies": [],
        }
    reliability_counts = row["reliability_counts"] or {}
    recent_anomalies = row["recent_anomalies"] or []
    if isinstance(reliability_counts, str):
        reliability_counts = json.loads(reliability_counts)
    if isinstance(recent_anomalies, str):
        recent_anomalies = json.loads(recent_anomalies)
    return {
        "route_id": route_id,
        "feature_windows": int(row["feature_windows"] or 0),
        "stops_clustered": int(row["stops_clustered"] or 0),
        "hotspots": int(row["hotspots"] or 0),
        "avg_cluster_delay": round(float(row["avg_cluster_delay"] or 0), 2),
        "avg_p95_abs_delay": round(float(row["avg_p95_abs_delay"] or 0), 2),
        "avg_prediction_coverage": round(float(row["avg_prediction_coverage"] or 0), 3),
        "reliability_counts": reliability_counts,
        "active_anomalies": int(row["active_anomalies"] or 0),
        "latest_anomaly_bucket": (
            row["latest_anomaly_bucket"].isoformat() if row["latest_anomaly_bucket"] else None
        ),
        "avg_anomaly_delay": round(float(row["avg_anomaly_delay"] or 0), 2),
        "recent_anomalies": recent_anomalies,
    }


@router.get("/system/status", response_model=SystemStatus)
async def system_status() -> SystemStatus:
    settings = get_settings()
    has_database_connection = False
    try:
        row = await fetchrow("SELECT 1 AS ok;")
        has_database_connection = row is not None and row["ok"] == 1
    except Exception:
        has_database_connection = False

    return SystemStatus(
        city=settings.city_name,
        agency=settings.agency_name,
        active_metric="Schedule adherence (-1 to +5 minutes)",
        early_threshold_minutes=settings.schedule_early_threshold_minutes,
        late_threshold_minutes=settings.schedule_late_threshold_minutes,
        has_database_connection=has_database_connection,
        notes=[
            "Static GTFS imports are versioned in batches so feed refreshes do not destroy history.",
            "Current OTP recomputation uses GTFS-RT trip updates plus HSL composite trip keys, while vehicle positions are still stored for richer future linking.",
        ],
    )


@router.get("/ingestion/status", response_model=IngestionStatus)
async def ingestion_status() -> IngestionStatus:
    row = await fetchrow(
        """
        WITH latest_batch AS (
          SELECT id, import_started_at, service_start_date, service_end_date, metadata
          FROM gtfs_import_batches
          ORDER BY import_started_at DESC
          LIMIT 1
        )
        SELECT
          latest_batch.id AS latest_batch_id,
          latest_batch.import_started_at AS latest_batch_started_at,
          latest_batch.service_start_date AS service_start_date,
          latest_batch.service_end_date AS service_end_date,
          (SELECT MAX(recorded_at) FROM rt_vehicle_positions_raw) AS latest_vehicle_position_at,
          (SELECT MAX(recorded_at) FROM rt_trip_updates_raw) AS latest_trip_update_at,
          COALESCE((latest_batch.metadata->>'routes.txt')::BIGINT, 0) AS routes_count,
          COALESCE((latest_batch.metadata->>'stops.txt')::BIGINT, 0) AS stops_count,
          COALESCE((latest_batch.metadata->>'trips.txt')::BIGINT, 0) AS trips_count,
          COALESCE((latest_batch.metadata->>'stop_times.txt')::BIGINT, 0) AS stop_times_count,
          (SELECT COUNT(*) FROM rt_vehicle_positions_raw) AS vehicle_positions_count,
          (SELECT COUNT(*) FROM rt_trip_updates_raw) AS trip_updates_count,
          (SELECT COUNT(*) FROM matched_vehicle_events) AS matched_events_count,
          (SELECT COUNT(*) FROM schedule_adherence_events) AS adherence_events_count
        FROM latest_batch
        """
    )

    if row is None:
        return IngestionStatus(
            latest_batch_id=None,
            latest_batch_started_at=None,
            latest_vehicle_position_at=None,
            latest_trip_update_at=None,
            service_start_date=None,
            service_end_date=None,
            routes_count=0,
            stops_count=0,
            trips_count=0,
            stop_times_count=0,
            vehicle_positions_count=0,
            trip_updates_count=0,
            matched_events_count=0,
            adherence_events_count=0,
        )

    return IngestionStatus(
        latest_batch_id=row["latest_batch_id"],
        latest_batch_started_at=row["latest_batch_started_at"],
        latest_vehicle_position_at=row["latest_vehicle_position_at"],
        latest_trip_update_at=row["latest_trip_update_at"],
        service_start_date=row["service_start_date"],
        service_end_date=row["service_end_date"],
        routes_count=int(row["routes_count"]),
        stops_count=int(row["stops_count"]),
        trips_count=int(row["trips_count"]),
        stop_times_count=int(row["stop_times_count"]),
        vehicle_positions_count=int(row["vehicle_positions_count"]),
        trip_updates_count=int(row["trip_updates_count"]),
        matched_events_count=int(row["matched_events_count"]),
        adherence_events_count=int(row["adherence_events_count"]),
    )


@router.post("/ingestion/static/import", response_model=OperationResult)
async def run_static_import() -> OperationResult:
    settings = get_settings()
    try:
        details = await import_static_gtfs(str(settings.hsl_static_gtfs_url))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Static import failed: {exc}") from exc

    return OperationResult(
        ok=True,
        message="Static GTFS imported successfully.",
        details=details,
    )


@router.post("/ingestion/realtime/poll", response_model=OperationResult)
async def run_realtime_poll() -> OperationResult:
    try:
        details = await poll_and_store_realtime()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Realtime poll failed: {exc}") from exc

    return OperationResult(
        ok=True,
        message="GTFS-RT feeds polled and stored successfully.",
        details=details,
    )


@router.post("/analytics/recompute", response_model=OperationResult)
async def recompute_metrics() -> OperationResult:
    try:
        details = await refresh_matches_and_metrics()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Metric recompute failed: {exc}") from exc

    return OperationResult(
        ok=True,
        message="Matched events and OTP metrics refreshed.",
        details=details,
    )
