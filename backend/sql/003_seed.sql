INSERT INTO data_sources (
  city_name,
  agency_name,
  static_gtfs_url,
  vehicle_positions_url,
  trip_updates_url,
  service_alerts_url,
  poll_interval_seconds
)
VALUES (
  'Helsinki',
  'HSL',
  'https://infopalvelut.storage.hsldev.com/gtfs/hsl.zip',
  'https://realtime.hsl.fi/realtime/vehicle-positions/v2/hsl',
  'https://realtime.hsl.fi/realtime/trip-updates/v2/hsl',
  'https://realtime.hsl.fi/realtime/service-alerts/v2/hsl',
  30
)
ON CONFLICT DO NOTHING;
