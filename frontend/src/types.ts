export type FeedConfig = {
  city: string;
  agency: string;
  static_gtfs_url: string;
  vehicle_positions_url: string;
  trip_updates_url: string;
  service_alerts_url: string;
  poll_interval_seconds: number;
};

export type SummaryResponse = {
  city: string;
  window_hours: number;
  bootstrap_mode: boolean;
  on_time_percentage: number;
  total_events: number;
  late_events: number;
  early_events: number;
  updated_at: string;
};

export type RouteMetric = {
  route_id: string;
  route_short_name: string;
  route_type?: number | null;
  window_hours: number;
  on_time_percentage: number;
  avg_delay_minutes: number;
  total_events: number;
  status: "good" | "watch" | "poor";
};

export type StopMetric = {
  stop_id: string;
  stop_name: string;
  route_id: string;
  on_time_percentage: number;
  avg_delay_minutes: number;
  total_events: number;
};

export type SystemStatus = {
  city: string;
  agency: string;
  active_metric: string;
  early_threshold_minutes: number;
  late_threshold_minutes: number;
  has_database_connection: boolean;
  notes: string[];
};

export type OperationResult = {
  ok: boolean;
  message: string;
  details: Record<string, unknown>;
};

export type IngestionStatus = {
  latest_batch_id: number | null;
  latest_batch_started_at: string | null;
  latest_vehicle_position_at: string | null;
  latest_trip_update_at: string | null;
  service_start_date: string | null;
  service_end_date: string | null;
  routes_count: number;
  stops_count: number;
  trips_count: number;
  stop_times_count: number;
  vehicle_positions_count: number;
  trip_updates_count: number;
  matched_events_count: number;
  adherence_events_count: number;
};

export type RouteGeometry = {
  type: "Feature";
  properties: {
    route_id: string;
    route_short_name: string;
    route_type: number | null;
    route_color?: string | null;
    route_text_color?: string | null;
  };
  geometry: {
    type: "LineString";
    coordinates: number[][];
  };
};

export type NetworkGeometry = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: {
      route_id: string;
      route_short_name: string;
      route_type: number | null;
      route_color: string | null;
      route_text_color: string | null;
      total_events: number;
    };
    geometry: {
      type: "LineString";
      coordinates: number[][];
    };
  }>;
};

export type RouteVehicles = {
  type: "FeatureCollection";
  meta: {
    route_id: string;
    route_short_name: string;
    vehicle_count: number;
    latest_recorded_at: string | null;
  };
  features: Array<{
    type: "Feature";
    properties: {
      entity_id: string;
      vehicle_id: string | null;
      vehicle_label: string;
      realtime_route_id: string | null;
      route_short_name?: string | null;
      route_type?: number | null;
      route_color?: string | null;
      trip_id: string | null;
      direction_id: number | null;
      start_date: string | null;
      start_time: string | null;
      stop_id: string | null;
      stop_name: string | null;
      next_stop_id: string | null;
      next_stop_name: string | null;
      next_stop_sequence: number | null;
      next_stop_delay_minutes: number | null;
      next_stop_source: string | null;
      current_status: string | null;
      bearing: number | null;
      speed: number | null;
      recorded_at: string;
      trip_update_recorded_at: string | null;
      upcoming_stops: Array<{
        stop_id: string | null;
        stop_name: string | null;
        stop_sequence: number | null;
        delay_minutes: number | null;
      }>;
    };
    geometry: {
      type: "Point";
      coordinates: number[];
    };
  }>;
};

export type RouteComparison = {
  type: "FeatureCollection";
  meta: {
    route_id: string;
    route_short_name: string;
    stop_count: number;
    latest_recorded_at: string | null;
    status_counts: {
      scheduled_only: number;
      early: number;
      on_time: number;
      late: number;
    };
  };
  features: Array<{
    type: "Feature";
    properties: {
      stop_id: string;
      stop_name: string;
      stop_sequence: number;
      live_status: "scheduled_only" | "early" | "on_time" | "late";
      delay_minutes: number | null;
      recorded_at: string | null;
      vehicle_id: string | null;
      trip_id: string | null;
      entity_id: string | null;
      realtime_route_id: string | null;
      update_count: number;
    };
    geometry: {
      type: "Point";
      coordinates: number[];
    };
  }>;
};

export type ModelStatus = {
  feature_windows: number;
  latest_feature_bucket: string | null;
  cluster_assignments: number;
  hotspot_count: number;
  active_anomalies: number;
  anomaly_scored_windows: number;
  latest_anomaly_bucket: string | null;
  avg_prediction_coverage: number;
  latest_cluster_run: string | null;
  latest_anomaly_run: string | null;
};

export type ModelClusters = {
  type: "FeatureCollection";
  meta: {
    count: number;
    hotspots_only: boolean;
    model_date: string | null;
  };
  features: Array<{
    type: "Feature";
    properties: {
      route_id: string;
      route_short_name: string | null;
      route_type: number | null;
      stop_id: string;
      stop_name: string | null;
      kmeans_cluster: number | null;
      dbscan_cluster: number | null;
      dbscan_is_hotspot: boolean;
      reliability_label: string;
      mean_delay_minutes: number;
      p95_abs_delay_minutes: number;
      prediction_coverage_ratio: number;
      sample_count: number;
      updated_at: string | null;
    };
    geometry: {
      type: "Point";
      coordinates: number[];
    };
  }>;
};

export type LiveAnomalies = {
  type: "FeatureCollection";
  meta: {
    count: number;
    window_hours: number;
    latest_bucket: string | null;
  };
  features: Array<{
    type: "Feature";
    properties: {
      bucket: string;
      route_id: string;
      route_short_name: string | null;
      route_type: number | null;
      stop_id: string;
      stop_name: string | null;
      isolation_forest_score: number | null;
      isolation_forest_is_anomaly: boolean;
      lof_score: number | null;
      lof_is_anomaly: boolean;
      pseudo_label: boolean;
      anomaly_reason: string | null;
      mean_delay_minutes: number;
      prediction_coverage_ratio: number;
      feed_age_seconds: number;
      updated_at: string | null;
    };
    geometry: {
      type: "Point";
      coordinates: number[];
    };
  }>;
};

export type RouteModelInsights = {
  route_id: string;
  feature_windows?: number;
  stops_clustered: number;
  hotspots: number;
  avg_cluster_delay?: number;
  avg_p95_abs_delay?: number;
  avg_prediction_coverage?: number;
  reliability_counts?: Record<string, number>;
  active_anomalies: number;
  latest_anomaly_bucket?: string | null;
  avg_anomaly_delay?: number;
  recent_anomalies?: Array<{
    bucket: string;
    stop_id: string;
    stop_name: string | null;
    reason: string | null;
    mean_delay_minutes: number;
    isolation_forest_score: number | null;
    lof_score: number | null;
  }>;
};
