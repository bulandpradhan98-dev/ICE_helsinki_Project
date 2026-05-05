from __future__ import annotations

import math
import json
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN, KMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    precision_score,
    recall_score,
    silhouette_score,
)
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

from app.core.database import connection, fetch, fetchrow

BUS_ROUTE_TYPES = [701, 702, 704]
MODEL_FEATURE_COLUMNS = [
    "mean_delay_minutes",
    "median_delay_minutes",
    "p95_abs_delay_minutes",
    "delay_std_minutes",
    "on_time_ratio",
    "late_ratio",
    "early_ratio",
    "prediction_coverage_ratio",
    "vehicle_observation_count",
    "feed_age_seconds",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
]


MODEL_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS model_run_metadata (
  id BIGSERIAL PRIMARY KEY,
  model_family TEXT NOT NULL,
  algorithm TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'running',
  rows_used INTEGER NOT NULL DEFAULT 0,
  selected_params JSONB NOT NULL DEFAULT '{}'::jsonb,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS model_feature_windows (
  bucket TIMESTAMPTZ NOT NULL,
  route_id TEXT NOT NULL,
  route_short_name TEXT,
  route_type INTEGER,
  stop_id TEXT NOT NULL,
  stop_name TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  window_hours INTEGER NOT NULL DEFAULT 1,
  mean_delay_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
  median_delay_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
  p95_abs_delay_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
  delay_std_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
  on_time_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
  late_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
  early_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
  prediction_coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
  vehicle_observation_count INTEGER NOT NULL DEFAULT 0,
  feed_age_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
  hour_of_day INTEGER NOT NULL,
  day_of_week INTEGER NOT NULL,
  is_weekend BOOLEAN NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (bucket, route_id, stop_id)
);

CREATE INDEX IF NOT EXISTS idx_model_feature_windows_route_time
ON model_feature_windows (route_id, bucket DESC);

CREATE INDEX IF NOT EXISTS idx_model_feature_windows_stop
ON model_feature_windows (stop_id);

CREATE TABLE IF NOT EXISTS cluster_assignments_daily (
  model_date DATE NOT NULL,
  route_id TEXT NOT NULL,
  route_short_name TEXT,
  route_type INTEGER,
  stop_id TEXT NOT NULL,
  stop_name TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  kmeans_cluster INTEGER,
  dbscan_cluster INTEGER,
  dbscan_is_hotspot BOOLEAN NOT NULL DEFAULT FALSE,
  reliability_label TEXT NOT NULL DEFAULT 'unclassified',
  mean_delay_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
  p95_abs_delay_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
  prediction_coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
  sample_count INTEGER NOT NULL DEFAULT 0,
  run_id BIGINT REFERENCES model_run_metadata(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (model_date, route_id, stop_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_assignments_daily_hotspot
ON cluster_assignments_daily (model_date DESC, dbscan_is_hotspot);

CREATE TABLE IF NOT EXISTS anomaly_scores_live (
  bucket TIMESTAMPTZ NOT NULL,
  route_id TEXT NOT NULL,
  route_short_name TEXT,
  route_type INTEGER,
  stop_id TEXT NOT NULL,
  stop_name TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  isolation_forest_score DOUBLE PRECISION,
  isolation_forest_is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
  lof_score DOUBLE PRECISION,
  lof_is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
  pseudo_label BOOLEAN NOT NULL DEFAULT FALSE,
  anomaly_reason TEXT,
  mean_delay_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
  prediction_coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
  feed_age_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
  run_id BIGINT REFERENCES model_run_metadata(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (bucket, route_id, stop_id)
);

CREATE INDEX IF NOT EXISTS idx_anomaly_scores_live_bucket
ON anomaly_scores_live (bucket DESC);

CREATE INDEX IF NOT EXISTS idx_anomaly_scores_live_flags
ON anomaly_scores_live (isolation_forest_is_anomaly, lof_is_anomaly);
"""


FEATURE_RECOMPUTE_SQL = """
WITH latest_batch AS (
  SELECT id
  FROM gtfs_import_batches
  ORDER BY import_started_at DESC
  LIMIT 1
),
expanded_updates AS (
  SELECT
    date_trunc('hour', tu.recorded_at) AS bucket,
    tu.recorded_at,
    tu.route_id,
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
    NULLIF(stop_update->>'departure_time', '')::DOUBLE PRECISION AS departure_time_epoch
  FROM rt_trip_updates_raw tu
  CROSS JOIN LATERAL jsonb_array_elements(
    COALESCE(tu.payload->'stop_time_updates', '[]'::jsonb)
  ) AS stop_update
  WHERE tu.route_id IS NOT NULL
    AND (
      NULLIF(stop_update->>'arrival_time', '') IS NOT NULL
      OR NULLIF(stop_update->>'departure_time', '') IS NOT NULL
      OR NULLIF(
        COALESCE(
          NULLIF(stop_update->>'arrival_delay_seconds', '')::DOUBLE PRECISION,
          NULLIF(stop_update->>'departure_delay_seconds', '')::DOUBLE PRECISION
        ),
        0
      ) IS NOT NULL
    )
),
enriched AS (
  SELECT
    eu.bucket,
    COALESCE(gr.route_id, eu.route_id) AS route_id,
    COALESCE(gr.route_short_name, gr.route_id, eu.route_id) AS route_short_name,
    gr.route_type,
    eu.stop_id,
    COALESCE(gs.stop_name, eu.stop_id) AS stop_name,
    ST_Y(gs.geom::geometry) AS latitude,
    ST_X(gs.geom::geometry) AS longitude,
    eu.recorded_at,
    CASE
      WHEN eu.arrival_time_epoch IS NOT NULL
       AND gst.arrival_time IS NOT NULL
       AND eu.start_date IS NOT NULL
      THEN EXTRACT(
        EPOCH FROM (
          (to_timestamp(eu.arrival_time_epoch) AT TIME ZONE 'Europe/Helsinki')
          - (
            to_date(eu.start_date, 'YYYYMMDD')
            + split_part(gst.arrival_time, ':', 1)::integer * interval '1 hour'
            + split_part(gst.arrival_time, ':', 2)::integer * interval '1 minute'
            + split_part(gst.arrival_time, ':', 3)::double precision * interval '1 second'
          )
        )
      ) / 60.0
      WHEN eu.departure_time_epoch IS NOT NULL
       AND gst.departure_time IS NOT NULL
       AND eu.start_date IS NOT NULL
      THEN EXTRACT(
        EPOCH FROM (
          (to_timestamp(eu.departure_time_epoch) AT TIME ZONE 'Europe/Helsinki')
          - (
            to_date(eu.start_date, 'YYYYMMDD')
            + split_part(gst.departure_time, ':', 1)::integer * interval '1 hour'
            + split_part(gst.departure_time, ':', 2)::integer * interval '1 minute'
            + split_part(gst.departure_time, ':', 3)::double precision * interval '1 second'
          )
        )
      ) / 60.0
      ELSE NULLIF(eu.raw_delay_minutes, 0)
    END AS delay_minutes
  FROM expanded_updates eu
  CROSS JOIN latest_batch lb
  LEFT JOIN gtfs_routes gr
    ON gr.batch_id = lb.id
   AND (gr.route_id = eu.route_id OR gr.route_short_name = eu.route_id)
  LEFT JOIN gtfs_stops gs
    ON gs.batch_id = lb.id
   AND gs.stop_id = eu.stop_id
  LEFT JOIN LATERAL (
    SELECT gt.trip_id
    FROM gtfs_trips gt
    JOIN gtfs_routes route_match
      ON route_match.batch_id = gt.batch_id
     AND route_match.route_id = gt.route_id
    WHERE gt.batch_id = lb.id
      AND (route_match.route_id = eu.route_id OR route_match.route_short_name = eu.route_id)
      AND (gt.direction_id IS NOT DISTINCT FROM eu.direction_id)
      AND gt.start_time = eu.start_time
    LIMIT 1
  ) trip_match ON TRUE
  LEFT JOIN gtfs_stop_times gst
    ON gst.batch_id = lb.id
   AND gst.trip_id = trip_match.trip_id
   AND (
     (eu.stop_id IS NOT NULL AND gst.stop_id = eu.stop_id)
     OR (eu.stop_id IS NULL AND gst.stop_sequence = eu.stop_sequence)
   )
  WHERE eu.stop_id IS NOT NULL
    AND ($1::int[] IS NULL OR gr.route_type = ANY($1::int[]))
    AND (
      eu.arrival_time_epoch IS NOT NULL
      OR eu.departure_time_epoch IS NOT NULL
      OR NULLIF(eu.raw_delay_minutes, 0) IS NOT NULL
    )
),
route_hour_totals AS (
  SELECT bucket, route_id, COUNT(*)::DOUBLE PRECISION AS route_update_count
  FROM enriched
  WHERE delay_minutes IS NOT NULL
  GROUP BY bucket, route_id
),
vehicle_counts AS (
  SELECT
    date_trunc('hour', vp.recorded_at) AS bucket,
    COALESCE(gr.route_id, vp.route_id) AS route_id,
    vp.stop_id,
    COUNT(*) AS vehicle_observation_count
  FROM rt_vehicle_positions_raw vp
  CROSS JOIN latest_batch lb
  LEFT JOIN gtfs_routes gr
    ON gr.batch_id = lb.id
   AND (gr.route_id = vp.route_id OR gr.route_short_name = vp.route_id)
  WHERE vp.stop_id IS NOT NULL
    AND ($1::int[] IS NULL OR gr.route_type = ANY($1::int[]))
  GROUP BY 1, 2, 3
),
aggregated AS (
  SELECT
    e.bucket,
    e.route_id,
    MAX(e.route_short_name) AS route_short_name,
    MAX(e.route_type) AS route_type,
    e.stop_id,
    MAX(e.stop_name) AS stop_name,
    MAX(e.latitude) AS latitude,
    MAX(e.longitude) AS longitude,
    ROUND(AVG(e.delay_minutes)::numeric, 4)::DOUBLE PRECISION AS mean_delay_minutes,
    ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY e.delay_minutes)::numeric, 4)::DOUBLE PRECISION AS median_delay_minutes,
    ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY ABS(e.delay_minutes))::numeric, 4)::DOUBLE PRECISION AS p95_abs_delay_minutes,
    ROUND(COALESCE(stddev_samp(e.delay_minutes), 0)::numeric, 4)::DOUBLE PRECISION AS delay_std_minutes,
    AVG(CASE WHEN e.delay_minutes BETWEEN -1 AND 5 THEN 1 ELSE 0 END)::DOUBLE PRECISION AS on_time_ratio,
    AVG(CASE WHEN e.delay_minutes > 5 THEN 1 ELSE 0 END)::DOUBLE PRECISION AS late_ratio,
    AVG(CASE WHEN e.delay_minutes < -1 THEN 1 ELSE 0 END)::DOUBLE PRECISION AS early_ratio,
    COUNT(*)::DOUBLE PRECISION
      / NULLIF(
          COUNT(*)::DOUBLE PRECISION
          + COALESCE(MAX(vc.vehicle_observation_count), 0)::DOUBLE PRECISION,
          0
        ) AS prediction_coverage_ratio,
    COALESCE(MAX(vc.vehicle_observation_count), 0) AS vehicle_observation_count,
    EXTRACT(EPOCH FROM (NOW() - MAX(e.recorded_at)))::DOUBLE PRECISION AS feed_age_seconds
  FROM enriched e
  JOIN route_hour_totals rht
    ON rht.bucket = e.bucket
   AND rht.route_id = e.route_id
  LEFT JOIN vehicle_counts vc
    ON vc.bucket = e.bucket
   AND vc.route_id = e.route_id
   AND vc.stop_id = e.stop_id
  WHERE e.delay_minutes IS NOT NULL
  GROUP BY e.bucket, e.route_id, e.stop_id
)
INSERT INTO model_feature_windows (
  bucket,
  route_id,
  route_short_name,
  route_type,
  stop_id,
  stop_name,
  latitude,
  longitude,
  window_hours,
  mean_delay_minutes,
  median_delay_minutes,
  p95_abs_delay_minutes,
  delay_std_minutes,
  on_time_ratio,
  late_ratio,
  early_ratio,
  prediction_coverage_ratio,
  vehicle_observation_count,
  feed_age_seconds,
  hour_of_day,
  day_of_week,
  is_weekend,
  updated_at
)
SELECT
  bucket,
  route_id,
  route_short_name,
  route_type,
  stop_id,
  stop_name,
  latitude,
  longitude,
  1,
  mean_delay_minutes,
  median_delay_minutes,
  p95_abs_delay_minutes,
  delay_std_minutes,
  on_time_ratio,
  late_ratio,
  early_ratio,
  COALESCE(prediction_coverage_ratio, 0),
  vehicle_observation_count,
  GREATEST(feed_age_seconds, 0),
  EXTRACT(HOUR FROM bucket)::INTEGER,
  EXTRACT(DOW FROM bucket)::INTEGER,
  EXTRACT(ISODOW FROM bucket)::INTEGER IN (6, 7),
  NOW()
FROM aggregated
ON CONFLICT (bucket, route_id, stop_id) DO UPDATE
SET
  route_short_name = EXCLUDED.route_short_name,
  route_type = EXCLUDED.route_type,
  stop_name = EXCLUDED.stop_name,
  latitude = EXCLUDED.latitude,
  longitude = EXCLUDED.longitude,
  mean_delay_minutes = EXCLUDED.mean_delay_minutes,
  median_delay_minutes = EXCLUDED.median_delay_minutes,
  p95_abs_delay_minutes = EXCLUDED.p95_abs_delay_minutes,
  delay_std_minutes = EXCLUDED.delay_std_minutes,
  on_time_ratio = EXCLUDED.on_time_ratio,
  late_ratio = EXCLUDED.late_ratio,
  early_ratio = EXCLUDED.early_ratio,
  prediction_coverage_ratio = EXCLUDED.prediction_coverage_ratio,
  vehicle_observation_count = EXCLUDED.vehicle_observation_count,
  feed_age_seconds = EXCLUDED.feed_age_seconds,
  hour_of_day = EXCLUDED.hour_of_day,
  day_of_week = EXCLUDED.day_of_week,
  is_weekend = EXCLUDED.is_weekend,
  updated_at = NOW();
"""


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    return value


def _feature_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    matrix = []
    for row in rows:
        matrix.append([float(row.get(column) or 0) for column in MODEL_FEATURE_COLUMNS])
    return np.asarray(matrix, dtype=float)


def _percentile(values: list[float], q: float, fallback: float = 0.0) -> float:
    if not values:
        return fallback
    return float(np.percentile(np.asarray(values, dtype=float), q * 100.0))


def _valid_cluster_metrics(matrix: np.ndarray, labels: np.ndarray) -> dict[str, float | None]:
    unique_labels = set(int(label) for label in labels)
    if len(unique_labels) < 2 or len(unique_labels) >= len(labels):
        return {"silhouette": None, "davies_bouldin": None, "calinski_harabasz": None}
    return {
        "silhouette": float(silhouette_score(matrix, labels)),
        "davies_bouldin": float(davies_bouldin_score(matrix, labels)),
        "calinski_harabasz": float(calinski_harabasz_score(matrix, labels)),
    }


async def ensure_model_tables() -> None:
    async with connection() as conn:
        await conn.execute(MODEL_TABLES_SQL)


async def recompute_model_features(mode: str = "bus") -> dict[str, Any]:
    await ensure_model_tables()
    route_types = BUS_ROUTE_TYPES if mode == "bus" else None
    async with connection() as conn:
        await conn.execute(FEATURE_RECOMPUTE_SQL, route_types)
        feature_count = await conn.fetchval("SELECT COUNT(*) FROM model_feature_windows;")
        latest_bucket = await conn.fetchval("SELECT MAX(bucket) FROM model_feature_windows;")
    return {
        "feature_windows": int(feature_count or 0),
        "latest_bucket": latest_bucket.isoformat() if latest_bucket else None,
        "mode": mode,
    }


async def recompute_clusters(mode: str = "bus") -> dict[str, Any]:
    await ensure_model_tables()
    await recompute_model_features(mode=mode)
    rows_raw = await fetch(
        """
        SELECT
          route_id,
          MAX(route_short_name) AS route_short_name,
          MAX(route_type) AS route_type,
          stop_id,
          MAX(stop_name) AS stop_name,
          AVG(latitude) AS latitude,
          AVG(longitude) AS longitude,
          AVG(mean_delay_minutes) AS mean_delay_minutes,
          AVG(median_delay_minutes) AS median_delay_minutes,
          AVG(p95_abs_delay_minutes) AS p95_abs_delay_minutes,
          AVG(delay_std_minutes) AS delay_std_minutes,
          AVG(on_time_ratio) AS on_time_ratio,
          AVG(late_ratio) AS late_ratio,
          AVG(early_ratio) AS early_ratio,
          AVG(prediction_coverage_ratio) AS prediction_coverage_ratio,
          AVG(vehicle_observation_count) AS vehicle_observation_count,
          AVG(feed_age_seconds) AS feed_age_seconds,
          AVG(hour_of_day) AS hour_of_day,
          AVG(day_of_week) AS day_of_week,
          AVG(CASE WHEN is_weekend THEN 1 ELSE 0 END) AS is_weekend,
          COUNT(*) AS sample_count
        FROM model_feature_windows
        WHERE ($1::int[] IS NULL OR route_type = ANY($1::int[]))
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        GROUP BY route_id, stop_id
        HAVING COUNT(*) >= 1
        ORDER BY COUNT(*) DESC, AVG(p95_abs_delay_minutes) DESC, AVG(late_ratio) DESC
        LIMIT 6000
        """,
        BUS_ROUTE_TYPES if mode == "bus" else None,
    )
    rows = [dict(row) for row in rows_raw]
    run_id = await _start_model_run("clustering", "kmeans_dbscan", len(rows))
    if len(rows) < 3:
        await _finish_model_run(
            run_id,
            "skipped",
            {},
            {},
            "Not enough feature rows for clustering.",
        )
        return {"run_id": run_id, "rows_used": len(rows), "status": "skipped"}

    matrix = _feature_matrix(rows)
    scaled = StandardScaler().fit_transform(matrix)
    coverage_values = [float(row["prediction_coverage_ratio"] or 0) for row in rows]
    p95_values = [float(row["p95_abs_delay_minutes"] or 0) for row in rows]
    late_values = [float(row["late_ratio"] or 0) for row in rows]
    feed_age_values = [float(row["feed_age_seconds"] or 0) for row in rows]
    positive_p95_values = [value for value in p95_values if value > 0]
    positive_late_values = [value for value in late_values if value > 0]
    has_delay_signal = bool(positive_p95_values or positive_late_values)
    coverage_low_threshold = _percentile(coverage_values, 0.10, fallback=0.15)
    coverage_watch_threshold = _percentile(coverage_values, 0.25, fallback=coverage_low_threshold)
    delay_hotspot_threshold = _percentile(positive_p95_values, 0.90, fallback=0.0)
    late_hotspot_threshold = _percentile(positive_late_values, 0.90, fallback=0.0)
    feed_stale_threshold = max(120.0, _percentile(feed_age_values, 0.90, fallback=120.0))

    kmeans_trials: list[dict[str, Any]] = []
    best_kmeans: tuple[float, KMeans, np.ndarray, dict[str, Any]] | None = None
    max_k = min(10, len(rows) - 1)
    for k in range(2, max_k + 1):
        model = KMeans(n_clusters=k, init="k-means++", n_init=20, random_state=42)
        labels = model.fit_predict(scaled)
        metrics = _valid_cluster_metrics(scaled, labels)
        score = metrics["silhouette"] if metrics["silhouette"] is not None else -1
        trial = {"k": k, **metrics}
        kmeans_trials.append(trial)
        if best_kmeans is None or score > best_kmeans[0]:
            best_kmeans = (float(score), model, labels, trial)

    dbscan_trials: list[dict[str, Any]] = []
    best_dbscan: tuple[float, DBSCAN, np.ndarray, dict[str, Any]] | None = None
    for eps in [0.4, 0.6, 0.8, 1.0, 1.3, 1.6, 2.0]:
        for min_samples in [5, 10, 15, 20]:
            if min_samples >= len(rows):
                continue
            model = DBSCAN(eps=eps, min_samples=min_samples)
            labels = model.fit_predict(scaled)
            non_noise = labels != -1
            cluster_count = len(set(int(label) for label in labels if label != -1))
            noise_share = float(np.mean(labels == -1))
            metrics = (
                _valid_cluster_metrics(scaled[non_noise], labels[non_noise])
                if cluster_count >= 2 and int(np.sum(non_noise)) > cluster_count
                else {"silhouette": None, "davies_bouldin": None, "calinski_harabasz": None}
            )
            score = metrics["silhouette"] if metrics["silhouette"] is not None else -1
            if cluster_count == 0 or noise_share > 0.85:
                score -= 1
            trial = {
                "eps": eps,
                "min_samples": min_samples,
                "cluster_count": cluster_count,
                "noise_share": noise_share,
                **metrics,
            }
            dbscan_trials.append(trial)
            if best_dbscan is None or score > best_dbscan[0]:
                best_dbscan = (float(score), model, labels, trial)

    assert best_kmeans is not None
    kmeans_labels = best_kmeans[2]
    dbscan_labels = best_dbscan[2] if best_dbscan is not None else np.full(len(rows), -1)

    mean_delay_by_cluster: dict[int, float] = {}
    for label in set(int(label) for label in kmeans_labels):
        delays = [float(row["mean_delay_minutes"] or 0) for row, row_label in zip(rows, kmeans_labels) if int(row_label) == label]
        mean_delay_by_cluster[label] = float(np.mean(delays)) if delays else 0.0

    model_date = datetime.now(timezone.utc).date()
    assignments = []
    for row, k_label, d_label in zip(rows, kmeans_labels, dbscan_labels):
        k_label_int = int(k_label)
        d_label_int = int(d_label)
        coverage_ratio = float(row["prediction_coverage_ratio"] or 0)
        p95_delay = float(row["p95_abs_delay_minutes"] or 0)
        late_ratio = float(row["late_ratio"] or 0)
        feed_age_seconds = float(row["feed_age_seconds"] or 0)
        sample_count = int(row["sample_count"] or 0)
        severe_coverage_gap = sample_count >= 3 and coverage_ratio <= coverage_low_threshold
        watch_coverage_gap = sample_count >= 2 and coverage_ratio <= max(coverage_watch_threshold, coverage_low_threshold)
        delay_hotspot = has_delay_signal and sample_count >= 3 and (
            (delay_hotspot_threshold > 0 and p95_delay >= delay_hotspot_threshold)
            or (late_hotspot_threshold > 0 and late_ratio >= late_hotspot_threshold)
        )
        reliability_label = "reliable"
        if delay_hotspot:
            reliability_label = "delay_hotspot"
        elif severe_coverage_gap:
            reliability_label = "low_realtime_coverage"
        elif (
            watch_coverage_gap
            or feed_age_seconds >= feed_stale_threshold
            or mean_delay_by_cluster.get(k_label_int, 0) > max(2.0, delay_hotspot_threshold / 2 if delay_hotspot_threshold else 2.0)
        ):
            reliability_label = "watch"
        assignments.append(
            (
                model_date,
                row["route_id"],
                row["route_short_name"],
                row["route_type"],
                row["stop_id"],
                row["stop_name"],
                row["latitude"],
                row["longitude"],
                k_label_int,
                d_label_int,
                d_label_int != -1 and (delay_hotspot or severe_coverage_gap),
                reliability_label,
                float(row["mean_delay_minutes"] or 0),
                p95_delay,
                coverage_ratio,
                sample_count,
                run_id,
            )
        )

    async with connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM cluster_assignments_daily WHERE model_date = $1;", model_date)
            await conn.executemany(
                """
                INSERT INTO cluster_assignments_daily (
                  model_date,
                  route_id,
                  route_short_name,
                  route_type,
                  stop_id,
                  stop_name,
                  latitude,
                  longitude,
                  kmeans_cluster,
                  dbscan_cluster,
                  dbscan_is_hotspot,
                  reliability_label,
                  mean_delay_minutes,
                  p95_abs_delay_minutes,
                  prediction_coverage_ratio,
                  sample_count,
                  run_id,
                  updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, NOW())
                ON CONFLICT (model_date, route_id, stop_id) DO UPDATE
                SET
                  route_short_name = EXCLUDED.route_short_name,
                  route_type = EXCLUDED.route_type,
                  stop_name = EXCLUDED.stop_name,
                  latitude = EXCLUDED.latitude,
                  longitude = EXCLUDED.longitude,
                  kmeans_cluster = EXCLUDED.kmeans_cluster,
                  dbscan_cluster = EXCLUDED.dbscan_cluster,
                  dbscan_is_hotspot = EXCLUDED.dbscan_is_hotspot,
                  reliability_label = EXCLUDED.reliability_label,
                  mean_delay_minutes = EXCLUDED.mean_delay_minutes,
                  p95_abs_delay_minutes = EXCLUDED.p95_abs_delay_minutes,
                  prediction_coverage_ratio = EXCLUDED.prediction_coverage_ratio,
                  sample_count = EXCLUDED.sample_count,
                  run_id = EXCLUDED.run_id,
                  updated_at = NOW();
                """,
                assignments,
            )

    metrics = {
        "kmeans_trials": kmeans_trials,
        "dbscan_trials": dbscan_trials,
        "selected_kmeans": best_kmeans[3],
        "selected_dbscan": best_dbscan[3] if best_dbscan else None,
        "derived_thresholds": {
            "coverage_low_threshold": coverage_low_threshold,
            "coverage_watch_threshold": coverage_watch_threshold,
            "delay_hotspot_threshold": delay_hotspot_threshold,
            "late_hotspot_threshold": late_hotspot_threshold,
            "feed_stale_threshold": feed_stale_threshold,
            "has_delay_signal": has_delay_signal,
        },
    }
    params = {
        "kmeans": {"k": best_kmeans[3]["k"], "n_init": 20},
        "dbscan": (
            {"eps": best_dbscan[3]["eps"], "min_samples": best_dbscan[3]["min_samples"]}
            if best_dbscan
            else {}
        ),
        "thresholds": {
            "coverage_low_threshold": round(coverage_low_threshold, 4),
            "coverage_watch_threshold": round(coverage_watch_threshold, 4),
            "delay_hotspot_threshold": round(delay_hotspot_threshold, 4),
            "late_hotspot_threshold": round(late_hotspot_threshold, 4),
            "feed_stale_threshold": round(feed_stale_threshold, 2),
        },
    }
    await _finish_model_run(run_id, "completed", params, metrics)
    hotspot_count = sum(1 for item in assignments if item[10])
    return {
        "run_id": run_id,
        "rows_used": len(rows),
        "status": "completed",
        "assignments": len(assignments),
        "hotspots": hotspot_count,
        "selected_params": params,
    }


async def recompute_anomalies(mode: str = "bus") -> dict[str, Any]:
    await ensure_model_tables()
    await recompute_model_features(mode=mode)
    rows_raw = await fetch(
        """
        SELECT *
        FROM model_feature_windows
        WHERE ($1::int[] IS NULL OR route_type = ANY($1::int[]))
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY bucket DESC
        LIMIT 5000
        """,
        BUS_ROUTE_TYPES if mode == "bus" else None,
    )
    rows = [dict(row) for row in rows_raw]
    run_id = await _start_model_run("anomaly_detection", "isolation_forest_lof", len(rows))
    if len(rows) < 10:
        await _finish_model_run(
            run_id,
            "skipped",
            {},
            {},
            "Not enough feature rows for anomaly detection.",
        )
        return {"run_id": run_id, "rows_used": len(rows), "status": "skipped"}

    matrix = _feature_matrix(rows)
    scaled = StandardScaler().fit_transform(matrix)
    coverage_values = [float(row["prediction_coverage_ratio"] or 0) for row in rows]
    p95_values = [float(row["p95_abs_delay_minutes"] or 0) for row in rows]
    late_values = [float(row["late_ratio"] or 0) for row in rows]
    feed_age_values = [float(row["feed_age_seconds"] or 0) for row in rows]
    positive_p95_values = [value for value in p95_values if value > 0]
    positive_late_values = [value for value in late_values if value > 0]
    has_delay_signal = bool(positive_p95_values or positive_late_values)
    coverage_dropout_threshold = _percentile(coverage_values, 0.05, fallback=0.1)
    feed_stale_threshold = max(300.0, _percentile(feed_age_values, 0.95, fallback=300.0))
    delay_anomaly_threshold = _percentile(positive_p95_values, 0.98, fallback=0.0)
    late_anomaly_threshold = _percentile(positive_late_values, 0.98, fallback=0.0)
    pseudo_labels = np.asarray(
        [
            bool(
                (
                    has_delay_signal
                    and delay_anomaly_threshold > 0
                    and float(row["p95_abs_delay_minutes"] or 0) >= delay_anomaly_threshold
                )
                or (
                    has_delay_signal
                    and late_anomaly_threshold > 0
                    and float(row["late_ratio"] or 0) >= late_anomaly_threshold
                )
                or float(row["prediction_coverage_ratio"] or 0) <= coverage_dropout_threshold
                or float(row["feed_age_seconds"] or 0) >= feed_stale_threshold
            )
            for row in rows
        ],
        dtype=bool,
    )

    if_trials: list[dict[str, Any]] = []
    best_if: tuple[float, IsolationForest, np.ndarray, np.ndarray, dict[str, Any]] | None = None
    for n_estimators in [100, 200, 500]:
        for max_samples in [256, 512, "auto"]:
            for contamination in [0.01, 0.02, 0.05]:
                model = IsolationForest(
                    n_estimators=n_estimators,
                    max_samples=max_samples,
                    contamination=contamination,
                    random_state=42,
                )
                labels = model.fit_predict(scaled) == -1
                scores = -model.decision_function(scaled)
                metrics = _classification_metrics(pseudo_labels, labels)
                score = metrics["precision_at_k"] + metrics["recall"] - metrics["false_alarm_share"]
                trial = {
                    "n_estimators": n_estimators,
                    "max_samples": max_samples,
                    "contamination": contamination,
                    **metrics,
                }
                if_trials.append(trial)
                if best_if is None or score > best_if[0]:
                    best_if = (float(score), model, labels, scores, trial)

    lof_trials: list[dict[str, Any]] = []
    best_lof: tuple[float, LocalOutlierFactor, np.ndarray, np.ndarray, dict[str, Any]] | None = None
    for n_neighbors in [10, 20, 35, 50]:
        if n_neighbors >= len(rows):
            continue
        for contamination in [0.01, 0.02, 0.05]:
            model = LocalOutlierFactor(
                n_neighbors=n_neighbors,
                contamination=contamination,
                novelty=False,
            )
            raw_labels = model.fit_predict(scaled)
            labels = raw_labels == -1
            scores = -model.negative_outlier_factor_
            metrics = _classification_metrics(pseudo_labels, labels)
            score = metrics["precision_at_k"] + metrics["recall"] - metrics["false_alarm_share"]
            trial = {
                "n_neighbors": n_neighbors,
                "contamination": contamination,
                **metrics,
            }
            lof_trials.append(trial)
            if best_lof is None or score > best_lof[0]:
                best_lof = (float(score), model, labels, scores, trial)

    assert best_if is not None
    if_labels = best_if[2]
    if_scores = best_if[3]
    lof_labels = best_lof[2] if best_lof else np.zeros(len(rows), dtype=bool)
    lof_scores = best_lof[3] if best_lof else np.zeros(len(rows), dtype=float)

    assignments = []
    for row, if_label, if_score, lof_label, lof_score, pseudo_label in zip(
        rows,
        if_labels,
        if_scores,
        lof_labels,
        lof_scores,
        pseudo_labels,
    ):
        reasons = []
        if has_delay_signal and delay_anomaly_threshold > 0 and float(row["p95_abs_delay_minutes"] or 0) >= delay_anomaly_threshold:
            reasons.append("extreme delay")
        if has_delay_signal and late_anomaly_threshold > 0 and float(row["late_ratio"] or 0) >= late_anomaly_threshold:
            reasons.append("late-heavy window")
        if float(row["prediction_coverage_ratio"] or 0) <= coverage_dropout_threshold:
            reasons.append("coverage dropout")
        if float(row["feed_age_seconds"] or 0) >= feed_stale_threshold:
            reasons.append("stale feed")
        assignments.append(
            (
                row["bucket"],
                row["route_id"],
                row["route_short_name"],
                row["route_type"],
                row["stop_id"],
                row["stop_name"],
                row["latitude"],
                row["longitude"],
                float(if_score),
                bool(if_label),
                float(lof_score),
                bool(lof_label),
                bool(pseudo_label),
                ", ".join(reasons) if reasons else "model flagged unusual pattern",
                float(row["mean_delay_minutes"] or 0),
                float(row["prediction_coverage_ratio"] or 0),
                float(row["feed_age_seconds"] or 0),
                run_id,
            )
        )

    async with connection() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO anomaly_scores_live (
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
                  run_id,
                  updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, NOW())
                ON CONFLICT (bucket, route_id, stop_id) DO UPDATE
                SET
                  route_short_name = EXCLUDED.route_short_name,
                  route_type = EXCLUDED.route_type,
                  stop_name = EXCLUDED.stop_name,
                  latitude = EXCLUDED.latitude,
                  longitude = EXCLUDED.longitude,
                  isolation_forest_score = EXCLUDED.isolation_forest_score,
                  isolation_forest_is_anomaly = EXCLUDED.isolation_forest_is_anomaly,
                  lof_score = EXCLUDED.lof_score,
                  lof_is_anomaly = EXCLUDED.lof_is_anomaly,
                  pseudo_label = EXCLUDED.pseudo_label,
                  anomaly_reason = EXCLUDED.anomaly_reason,
                  mean_delay_minutes = EXCLUDED.mean_delay_minutes,
                  prediction_coverage_ratio = EXCLUDED.prediction_coverage_ratio,
                  feed_age_seconds = EXCLUDED.feed_age_seconds,
                  run_id = EXCLUDED.run_id,
                  updated_at = NOW();
                """,
                assignments,
            )

    metrics = {
        "isolation_forest_trials": if_trials,
        "lof_trials": lof_trials,
        "selected_isolation_forest": best_if[4],
        "selected_lof": best_lof[4] if best_lof else None,
        "pseudo_label_positive_count": int(np.sum(pseudo_labels)),
        "derived_thresholds": {
            "coverage_dropout_threshold": coverage_dropout_threshold,
            "feed_stale_threshold": feed_stale_threshold,
            "delay_anomaly_threshold": delay_anomaly_threshold,
            "late_anomaly_threshold": late_anomaly_threshold,
            "has_delay_signal": has_delay_signal,
        },
    }
    params = {
        "isolation_forest": {
            "n_estimators": best_if[4]["n_estimators"],
            "max_samples": best_if[4]["max_samples"],
            "contamination": best_if[4]["contamination"],
        },
        "lof": (
            {
                "n_neighbors": best_lof[4]["n_neighbors"],
                "contamination": best_lof[4]["contamination"],
            }
            if best_lof
            else {}
        ),
        "thresholds": {
            "coverage_dropout_threshold": round(coverage_dropout_threshold, 4),
            "feed_stale_threshold": round(feed_stale_threshold, 2),
            "delay_anomaly_threshold": round(delay_anomaly_threshold, 4),
            "late_anomaly_threshold": round(late_anomaly_threshold, 4),
        },
    }
    await _finish_model_run(run_id, "completed", params, metrics)
    return {
        "run_id": run_id,
        "rows_used": len(rows),
        "status": "completed",
        "isolation_forest_anomalies": int(np.sum(if_labels)),
        "lof_anomalies": int(np.sum(lof_labels)),
        "selected_params": params,
    }


async def model_status() -> dict[str, Any]:
    await ensure_model_tables()
    row = await fetchrow(
        """
        SELECT
          (SELECT COUNT(*) FROM model_feature_windows WHERE route_type = ANY($1::int[])) AS feature_windows,
          (SELECT MAX(bucket) FROM model_feature_windows WHERE route_type = ANY($1::int[])) AS latest_feature_bucket,
          (
            SELECT COUNT(*)
            FROM cluster_assignments_daily
            WHERE model_date = (SELECT MAX(model_date) FROM cluster_assignments_daily)
              AND route_type = ANY($1::int[])
          ) AS cluster_assignments,
          (
            SELECT COUNT(*)
            FROM cluster_assignments_daily
            WHERE model_date = (SELECT MAX(model_date) FROM cluster_assignments_daily)
              AND route_type = ANY($1::int[])
              AND dbscan_is_hotspot
          ) AS hotspot_count,
          (
            SELECT COUNT(*)
            FROM anomaly_scores_live
            WHERE bucket >= NOW() - interval '3 hours'
              AND route_type = ANY($1::int[])
              AND (isolation_forest_is_anomaly OR lof_is_anomaly)
          ) AS active_anomalies,
          (
            SELECT COUNT(*)
            FROM anomaly_scores_live
            WHERE bucket >= NOW() - interval '3 hours'
              AND route_type = ANY($1::int[])
          ) AS anomaly_scored_windows,
          (
            SELECT MAX(bucket)
            FROM anomaly_scores_live
            WHERE route_type = ANY($1::int[])
          ) AS latest_anomaly_bucket,
          (
            SELECT AVG(prediction_coverage_ratio)
            FROM model_feature_windows
            WHERE bucket >= NOW() - interval '24 hours'
              AND route_type = ANY($1::int[])
          ) AS avg_prediction_coverage,
          (SELECT MAX(completed_at) FROM model_run_metadata WHERE model_family = 'clustering' AND status = 'completed') AS latest_cluster_run,
          (SELECT MAX(completed_at) FROM model_run_metadata WHERE model_family = 'anomaly_detection' AND status = 'completed') AS latest_anomaly_run
        """,
        BUS_ROUTE_TYPES,
    )
    return {
        "feature_windows": int(row["feature_windows"] or 0),
        "latest_feature_bucket": row["latest_feature_bucket"].isoformat() if row["latest_feature_bucket"] else None,
        "cluster_assignments": int(row["cluster_assignments"] or 0),
        "hotspot_count": int(row["hotspot_count"] or 0),
        "active_anomalies": int(row["active_anomalies"] or 0),
        "anomaly_scored_windows": int(row["anomaly_scored_windows"] or 0),
        "latest_anomaly_bucket": row["latest_anomaly_bucket"].isoformat() if row["latest_anomaly_bucket"] else None,
        "avg_prediction_coverage": float(row["avg_prediction_coverage"] or 0),
        "latest_cluster_run": row["latest_cluster_run"].isoformat() if row["latest_cluster_run"] else None,
        "latest_anomaly_run": row["latest_anomaly_run"].isoformat() if row["latest_anomaly_run"] else None,
    }


def _classification_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    if len(y_true) == 0:
        return {"precision_at_k": 0.0, "recall": 0.0, "f1_proxy": 0.0, "false_alarm_share": 0.0}
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1_proxy = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    false_alarm_share = float(np.mean(np.logical_and(y_pred, np.logical_not(y_true))))
    return {
        "precision_at_k": float(precision),
        "recall": float(recall),
        "f1_proxy": float(f1_proxy),
        "false_alarm_share": false_alarm_share,
    }


async def _start_model_run(model_family: str, algorithm: str, rows_used: int) -> int:
    await ensure_model_tables()
    row = await fetchrow(
        """
        INSERT INTO model_run_metadata (model_family, algorithm, rows_used)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        model_family,
        algorithm,
        rows_used,
    )
    return int(row["id"])


async def _finish_model_run(
    run_id: int,
    status: str,
    selected_params: dict[str, Any],
    metrics: dict[str, Any],
    notes: str | None = None,
) -> None:
    async with connection() as conn:
        await conn.execute(
            """
            UPDATE model_run_metadata
            SET
              completed_at = NOW(),
              status = $2,
              selected_params = $3::jsonb,
              metrics = $4::jsonb,
              notes = $5
            WHERE id = $1
            """,
            run_id,
            status,
            json.dumps(_json_safe(selected_params)),
            json.dumps(_json_safe(metrics)),
            notes,
        )
