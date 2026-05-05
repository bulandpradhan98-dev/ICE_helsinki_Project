CREATE TABLE IF NOT EXISTS data_sources (
  id SERIAL PRIMARY KEY,
  city_name TEXT NOT NULL,
  agency_name TEXT NOT NULL,
  static_gtfs_url TEXT NOT NULL,
  vehicle_positions_url TEXT NOT NULL,
  trip_updates_url TEXT NOT NULL,
  service_alerts_url TEXT NOT NULL,
  poll_interval_seconds INTEGER NOT NULL DEFAULT 30,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_data_sources_city_agency
ON data_sources (city_name, agency_name);

CREATE TABLE IF NOT EXISTS gtfs_import_batches (
  id BIGSERIAL PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES data_sources(id),
  import_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  import_completed_at TIMESTAMPTZ,
  service_start_date DATE,
  service_end_date DATE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS gtfs_routes (
  batch_id BIGINT NOT NULL REFERENCES gtfs_import_batches(id),
  route_id TEXT NOT NULL,
  agency_id TEXT,
  route_short_name TEXT,
  route_long_name TEXT,
  route_desc TEXT,
  route_type INTEGER,
  route_color TEXT,
  route_text_color TEXT,
  PRIMARY KEY (batch_id, route_id)
);

CREATE TABLE IF NOT EXISTS gtfs_stops (
  batch_id BIGINT NOT NULL REFERENCES gtfs_import_batches(id),
  stop_id TEXT NOT NULL,
  stop_code TEXT,
  stop_name TEXT NOT NULL,
  parent_station TEXT,
  platform_code TEXT,
  geom GEOGRAPHY(POINT, 4326) NOT NULL,
  PRIMARY KEY (batch_id, stop_id)
);

CREATE INDEX IF NOT EXISTS idx_gtfs_stops_geom ON gtfs_stops USING GIST (geom);

CREATE TABLE IF NOT EXISTS gtfs_shapes (
  batch_id BIGINT NOT NULL REFERENCES gtfs_import_batches(id),
  shape_id TEXT NOT NULL,
  shape_pt_sequence INTEGER NOT NULL,
  geom GEOGRAPHY(POINT, 4326) NOT NULL,
  PRIMARY KEY (batch_id, shape_id, shape_pt_sequence)
);

CREATE INDEX IF NOT EXISTS idx_gtfs_shapes_geom ON gtfs_shapes USING GIST (geom);

CREATE TABLE IF NOT EXISTS gtfs_trips (
  batch_id BIGINT NOT NULL REFERENCES gtfs_import_batches(id),
  trip_id TEXT NOT NULL,
  route_id TEXT NOT NULL,
  service_id TEXT,
  trip_headsign TEXT,
  direction_id INTEGER,
  block_id TEXT,
  shape_id TEXT,
  start_time TEXT,
  PRIMARY KEY (batch_id, trip_id),
  FOREIGN KEY (batch_id, route_id) REFERENCES gtfs_routes(batch_id, route_id)
);

CREATE TABLE IF NOT EXISTS gtfs_stop_times (
  batch_id BIGINT NOT NULL,
  trip_id TEXT NOT NULL,
  stop_sequence INTEGER NOT NULL,
  stop_id TEXT NOT NULL,
  arrival_time TEXT,
  departure_time TEXT,
  PRIMARY KEY (batch_id, trip_id, stop_sequence),
  FOREIGN KEY (batch_id, trip_id) REFERENCES gtfs_trips(batch_id, trip_id),
  FOREIGN KEY (batch_id, stop_id) REFERENCES gtfs_stops(batch_id, stop_id)
);

CREATE INDEX IF NOT EXISTS idx_gtfs_stop_times_stop_id ON gtfs_stop_times (batch_id, stop_id);
CREATE INDEX IF NOT EXISTS idx_gtfs_trips_match_lookup ON gtfs_trips (batch_id, route_id, direction_id, start_time);
CREATE INDEX IF NOT EXISTS idx_gtfs_stop_times_trip_stop_lookup ON gtfs_stop_times (batch_id, trip_id, stop_id);
CREATE INDEX IF NOT EXISTS idx_gtfs_stop_times_trip_sequence_lookup ON gtfs_stop_times (batch_id, trip_id, stop_sequence);

CREATE TABLE IF NOT EXISTS rt_vehicle_positions_raw (
  recorded_at TIMESTAMPTZ NOT NULL,
  entity_id TEXT NOT NULL,
  route_id TEXT,
  direction_id INTEGER,
  start_date TEXT,
  start_time TEXT,
  trip_id TEXT,
  stop_id TEXT,
  current_status TEXT,
  schedule_relationship TEXT,
  vehicle_id TEXT,
  vehicle_label TEXT,
  latitude DOUBLE PRECISION NOT NULL,
  longitude DOUBLE PRECISION NOT NULL,
  bearing DOUBLE PRECISION,
  speed DOUBLE PRECISION,
  geom GEOGRAPHY(POINT, 4326) GENERATED ALWAYS AS (
    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
  ) STORED
);

SELECT create_hypertable('rt_vehicle_positions_raw', 'recorded_at', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_rt_vehicle_positions_geom ON rt_vehicle_positions_raw USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_rt_vehicle_positions_route_time ON rt_vehicle_positions_raw (route_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS rt_trip_updates_raw (
  recorded_at TIMESTAMPTZ NOT NULL,
  entity_id TEXT NOT NULL,
  route_id TEXT,
  direction_id INTEGER,
  start_date TEXT,
  start_time TEXT,
  trip_id TEXT,
  vehicle_id TEXT,
  payload JSONB NOT NULL
);

SELECT create_hypertable('rt_trip_updates_raw', 'recorded_at', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_rt_trip_updates_route_time ON rt_trip_updates_raw (route_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS matched_vehicle_events (
  observed_at TIMESTAMPTZ NOT NULL,
  entity_id TEXT NOT NULL,
  vehicle_id TEXT,
  route_id TEXT NOT NULL,
  matched_trip_id TEXT,
  direction_id INTEGER,
  start_date TEXT,
  start_time TEXT,
  stop_id TEXT,
  stop_name TEXT,
  scheduled_arrival_time TEXT,
  observed_delay_minutes DOUBLE PRECISION,
  match_score DOUBLE PRECISION,
  matcher_version TEXT NOT NULL DEFAULT 'hsl-v1',
  geom GEOGRAPHY(POINT, 4326)
);

SELECT create_hypertable('matched_vehicle_events', 'observed_at', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_matched_vehicle_events_route_time ON matched_vehicle_events (route_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS schedule_adherence_events (
  observed_at TIMESTAMPTZ NOT NULL,
  route_id TEXT NOT NULL,
  route_short_name TEXT,
  route_type INTEGER,
  stop_id TEXT,
  stop_name TEXT,
  trip_id TEXT,
  delay_minutes DOUBLE PRECISION NOT NULL,
  adherence_status TEXT NOT NULL CHECK (adherence_status IN ('early', 'on_time', 'late'))
);

SELECT create_hypertable('schedule_adherence_events', 'observed_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS route_otp_hourly (
  bucket TIMESTAMPTZ NOT NULL,
  route_id TEXT NOT NULL,
  route_short_name TEXT,
  route_type INTEGER,
  on_time_percentage DOUBLE PRECISION NOT NULL,
  avg_delay_minutes DOUBLE PRECISION NOT NULL,
  total_events INTEGER NOT NULL,
  early_events INTEGER NOT NULL,
  late_events INTEGER NOT NULL,
  PRIMARY KEY (bucket, route_id)
);

CREATE TABLE IF NOT EXISTS stop_otp_hourly (
  bucket TIMESTAMPTZ NOT NULL,
  stop_id TEXT NOT NULL,
  stop_name TEXT NOT NULL,
  route_id TEXT NOT NULL,
  on_time_percentage DOUBLE PRECISION NOT NULL,
  avg_delay_minutes DOUBLE PRECISION NOT NULL,
  total_events INTEGER NOT NULL,
  PRIMARY KEY (bucket, stop_id, route_id)
);
