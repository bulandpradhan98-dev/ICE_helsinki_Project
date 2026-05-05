# Architecture Notes

## Critical path

1. database
2. static GTFS ETL
3. GTFS-RT poller
4. trip matching
5. analytics API
6. dashboard

## Why precomputed analytics

The dashboard should query pre-aggregated route and stop metrics instead of scanning raw vehicle traces on every request. This keeps the frontend responsive and reduces repeated computation.

## Why TimescaleDB and PostGIS

- `TimescaleDB` fits GTFS-RT vehicle position writes and time-window aggregations.
- `PostGIS` supports route shapes, nearest stop lookups, and spatial indexing.
- The combination lets the project stay close to the raw mobility problem instead of flattening everything into non-spatial tables.

