from app.core.config import get_settings
from app.core.database import connection


def adherence_case_expression(delay_column: str = "delay_minutes") -> str:
    settings = get_settings()
    return f"""
CASE
  WHEN {delay_column} < {settings.schedule_early_threshold_minutes} THEN 'early'
  WHEN {delay_column} > {settings.schedule_late_threshold_minutes} THEN 'late'
  ELSE 'on_time'
END
"""


MATCHED_EVENTS_SQL = """
WITH latest_batch AS (
  SELECT id
  FROM gtfs_import_batches
  ORDER BY import_started_at DESC
  LIMIT 1
)
INSERT INTO matched_vehicle_events (
  observed_at,
  entity_id,
  vehicle_id,
  route_id,
  matched_trip_id,
  direction_id,
  start_date,
  start_time,
  stop_id,
  stop_name,
  scheduled_arrival_time,
  observed_delay_minutes,
  match_score,
  geom
)
SELECT
  vp.recorded_at,
  vp.entity_id,
  vp.vehicle_id,
  vp.route_id,
  trip_match.trip_id,
  vp.direction_id,
  vp.start_date,
  vp.start_time,
  vp.stop_id,
  stops.stop_name,
  stop_time_match.arrival_time,
  NULL,
  CASE WHEN trip_match.trip_id IS NULL THEN 0 ELSE 75 END,
  vp.geom
FROM rt_vehicle_positions_raw vp
CROSS JOIN latest_batch lb
LEFT JOIN LATERAL (
  SELECT trip_id
  FROM gtfs_trips gt
  JOIN gtfs_routes gr
    ON gr.batch_id = gt.batch_id
   AND gr.route_id = gt.route_id
  WHERE gt.batch_id = lb.id
    AND (gr.route_id = vp.route_id OR gr.route_short_name = vp.route_id)
    AND (gt.direction_id IS NOT DISTINCT FROM vp.direction_id)
    AND gt.start_time = vp.start_time
  LIMIT 1
) trip_match ON TRUE
LEFT JOIN gtfs_stops stops
  ON stops.batch_id = lb.id
 AND stops.stop_id = vp.stop_id
LEFT JOIN gtfs_stop_times stop_time_match
  ON stop_time_match.batch_id = lb.id
 AND stop_time_match.trip_id = trip_match.trip_id
 AND stop_time_match.stop_id = vp.stop_id
WHERE vp.recorded_at >= NOW() - interval '30 minutes';
"""


SCHEDULE_ADHERENCE_SQL = f"""
WITH latest_batch AS (
  SELECT id
  FROM gtfs_import_batches
  ORDER BY import_started_at DESC
  LIMIT 1
),
latest_trip_update AS (
  SELECT MAX(recorded_at) AS latest_recorded_at
  FROM rt_trip_updates_raw
),
expanded AS (
  SELECT
    r.recorded_at AS observed_at,
    r.route_id,
    r.direction_id,
    r.start_date,
    r.start_time,
    stop_update ->> 'stop_id' AS stop_id,
    NULLIF(stop_update ->> 'stop_sequence', '')::INTEGER AS stop_sequence,
    COALESCE(
      NULLIF(stop_update ->> 'arrival_delay_seconds', '')::double precision,
      NULLIF(stop_update ->> 'departure_delay_seconds', '')::double precision
    ) / 60.0 AS raw_delay_minutes,
    NULLIF(stop_update ->> 'arrival_time', '')::double precision AS arrival_time_epoch,
    NULLIF(stop_update ->> 'departure_time', '')::double precision AS departure_time_epoch
  FROM rt_trip_updates_raw r
  CROSS JOIN latest_trip_update ltu
  CROSS JOIN LATERAL jsonb_array_elements(r.payload -> 'stop_time_updates') stop_update
  WHERE r.route_id IS NOT NULL
    AND r.recorded_at >= COALESCE(ltu.latest_recorded_at - interval '5 minutes', r.recorded_at)
),
enriched AS (
  SELECT
    expanded.observed_at,
    expanded.route_id,
    route_match.route_short_name,
    route_match.route_type,
    expanded.stop_id,
    stops.stop_name,
    trip_match.trip_id,
    CASE
      WHEN expanded.arrival_time_epoch IS NOT NULL
       AND stop_time_match.arrival_time IS NOT NULL
       AND expanded.start_date IS NOT NULL
      THEN EXTRACT(
        EPOCH FROM (
          (to_timestamp(expanded.arrival_time_epoch) AT TIME ZONE 'Europe/Helsinki')
          - (
            to_date(expanded.start_date, 'YYYYMMDD')
            + split_part(stop_time_match.arrival_time, ':', 1)::integer * interval '1 hour'
            + split_part(stop_time_match.arrival_time, ':', 2)::integer * interval '1 minute'
            + split_part(stop_time_match.arrival_time, ':', 3)::double precision * interval '1 second'
          )
        )
      ) / 60.0
      WHEN expanded.departure_time_epoch IS NOT NULL
       AND stop_time_match.departure_time IS NOT NULL
       AND expanded.start_date IS NOT NULL
      THEN EXTRACT(
        EPOCH FROM (
          (to_timestamp(expanded.departure_time_epoch) AT TIME ZONE 'Europe/Helsinki')
          - (
            to_date(expanded.start_date, 'YYYYMMDD')
            + split_part(stop_time_match.departure_time, ':', 1)::integer * interval '1 hour'
            + split_part(stop_time_match.departure_time, ':', 2)::integer * interval '1 minute'
            + split_part(stop_time_match.departure_time, ':', 3)::double precision * interval '1 second'
          )
        )
      ) / 60.0
      ELSE NULLIF(expanded.raw_delay_minutes, 0)
    END AS delay_minutes
  FROM expanded
  CROSS JOIN latest_batch lb
  LEFT JOIN LATERAL (
    SELECT route_id, route_short_name, route_type
    FROM gtfs_routes gr
    WHERE gr.batch_id = lb.id
      AND (gr.route_id = expanded.route_id OR gr.route_short_name = expanded.route_id)
    LIMIT 1
  ) route_match ON TRUE
  LEFT JOIN gtfs_stops stops
    ON stops.batch_id = lb.id
   AND stops.stop_id = expanded.stop_id
  LEFT JOIN LATERAL (
    SELECT trip_id
    FROM gtfs_trips gt
    JOIN gtfs_routes gr
      ON gr.batch_id = gt.batch_id
     AND gr.route_id = gt.route_id
    WHERE gt.batch_id = lb.id
      AND (gr.route_id = expanded.route_id OR gr.route_short_name = expanded.route_id)
      AND (gt.direction_id IS NOT DISTINCT FROM expanded.direction_id)
      AND gt.start_time = expanded.start_time
    LIMIT 1
  ) trip_match ON TRUE
  LEFT JOIN gtfs_stop_times stop_time_match
    ON stop_time_match.batch_id = lb.id
   AND stop_time_match.trip_id = trip_match.trip_id
   AND (
     (expanded.stop_id IS NOT NULL AND stop_time_match.stop_id = expanded.stop_id)
     OR (expanded.stop_id IS NULL AND stop_time_match.stop_sequence = expanded.stop_sequence)
   )
  WHERE (
    expanded.arrival_time_epoch IS NOT NULL
    OR expanded.departure_time_epoch IS NOT NULL
    OR NULLIF(expanded.raw_delay_minutes, 0) IS NOT NULL
  )
)
INSERT INTO schedule_adherence_events (
  observed_at,
  route_id,
  route_short_name,
  route_type,
  stop_id,
  stop_name,
  trip_id,
  delay_minutes,
  adherence_status
)
SELECT
  observed_at,
  route_id,
  route_short_name,
  route_type,
  stop_id,
  stop_name,
  trip_id,
  delay_minutes,
  {adherence_case_expression()}
FROM enriched
WHERE delay_minutes IS NOT NULL;
"""


ROUTE_OTP_REFRESH_SQL = """
INSERT INTO route_otp_hourly (
  bucket,
  route_id,
  route_short_name,
  route_type,
  on_time_percentage,
  avg_delay_minutes,
  total_events,
  early_events,
  late_events
)
SELECT
  date_trunc('hour', observed_at) AS bucket,
  route_id,
  MAX(route_short_name) AS route_short_name,
  MAX(route_type) AS route_type,
  ROUND(
    100.0 * AVG(CASE WHEN adherence_status = 'on_time' THEN 1 ELSE 0 END),
    2
  ) AS on_time_percentage,
  ROUND(AVG(delay_minutes)::numeric, 2) AS avg_delay_minutes,
  COUNT(*) AS total_events,
  SUM(CASE WHEN adherence_status = 'early' THEN 1 ELSE 0 END) AS early_events,
  SUM(CASE WHEN adherence_status = 'late' THEN 1 ELSE 0 END) AS late_events
FROM schedule_adherence_events
GROUP BY 1, 2
ON CONFLICT (bucket, route_id) DO UPDATE
SET
  route_short_name = EXCLUDED.route_short_name,
  route_type = EXCLUDED.route_type,
  on_time_percentage = EXCLUDED.on_time_percentage,
  avg_delay_minutes = EXCLUDED.avg_delay_minutes,
  total_events = EXCLUDED.total_events,
  early_events = EXCLUDED.early_events,
  late_events = EXCLUDED.late_events;
"""


STOP_OTP_REFRESH_SQL = """
INSERT INTO stop_otp_hourly (
  bucket,
  stop_id,
  stop_name,
  route_id,
  on_time_percentage,
  avg_delay_minutes,
  total_events
)
SELECT
  date_trunc('hour', observed_at) AS bucket,
  stop_id,
  COALESCE(MAX(stop_name), stop_id) AS stop_name,
  route_id,
  ROUND(
    100.0 * AVG(CASE WHEN adherence_status = 'on_time' THEN 1 ELSE 0 END),
    2
  ) AS on_time_percentage,
  ROUND(AVG(delay_minutes)::numeric, 2) AS avg_delay_minutes,
  COUNT(*) AS total_events
FROM schedule_adherence_events
WHERE stop_id IS NOT NULL
GROUP BY 1, 2, 4
ON CONFLICT (bucket, stop_id, route_id) DO UPDATE
SET
  stop_name = EXCLUDED.stop_name,
  on_time_percentage = EXCLUDED.on_time_percentage,
  avg_delay_minutes = EXCLUDED.avg_delay_minutes,
  total_events = EXCLUDED.total_events;
"""


async def refresh_matches_and_metrics() -> dict[str, int]:
    async with connection() as conn:
        async with conn.transaction():
            latest_batch_id = await conn.fetchval(
                """
                SELECT id
                FROM gtfs_import_batches
                ORDER BY import_started_at DESC
                LIMIT 1
                """
            )
            if latest_batch_id is None:
                raise RuntimeError("No static GTFS batch found. Import static GTFS first.")

            await conn.execute("TRUNCATE matched_vehicle_events, schedule_adherence_events, route_otp_hourly, stop_otp_hourly;")
            # The vehicle-position fuzzy matcher is intentionally kept separate from
            # live OTP refresh: route reliability comes from TripUpdates predictions.
            # Running the matcher over archived GPS points is too slow for an
            # interactive dashboard recompute.
            await conn.execute(SCHEDULE_ADHERENCE_SQL)
            await conn.execute(ROUTE_OTP_REFRESH_SQL)
            await conn.execute(STOP_OTP_REFRESH_SQL)

            matched_events_count = await conn.fetchval("SELECT COUNT(*) FROM matched_vehicle_events;")
            adherence_events_count = await conn.fetchval("SELECT COUNT(*) FROM schedule_adherence_events;")
            route_rows = await conn.fetchval("SELECT COUNT(*) FROM route_otp_hourly;")
            stop_rows = await conn.fetchval("SELECT COUNT(*) FROM stop_otp_hourly;")

    return {
        "matched_events": int(matched_events_count),
        "adherence_events": int(adherence_events_count),
        "route_buckets": int(route_rows),
        "stop_buckets": int(stop_rows),
    }
