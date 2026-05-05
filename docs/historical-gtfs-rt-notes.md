# Historical GTFS-RT Notes For The Exam

Generated during the April 26, 2026 evidence run.

## What We Can Use Immediately

- The local database stores HSL GTFS-RT vehicle positions and trip updates while Docker is running.
- Docker volumes keep the database when using `docker compose down`; do not use `docker compose down -v` unless you intentionally want to delete the collected history.
- The current evidence export is stored in `reports/history_exports/` so the notebooks and presentation can still use a frozen bus-only snapshot if Docker is off or the live feed changes.

## HSL-Specific Findings

- HSL publishes GTFS-RT service alerts, trip updates, and vehicle positions, but the public documentation describes live endpoints, not a public multi-day historical GTFS-RT download archive.
- HSL vehicle positions and trip updates do not expose stable GTFS `trip_id` values. HSL recommends matching by `route_id`, `start_date`, `start_time`, and `direction_id`; this is why our project treats the linker/matching step as a real data-science challenge.
- HSL's own transitdata repository mentions internal Azure Blob publishing and archiving of HFP/EKE CSV messages, but I did not find a public documented URL for downloading several days of historical HSL GTFS-RT vehicle/trip-update data.

## External Historical Options

- Transitland is useful for archived static GTFS feed versions, including HSL, but it is not a direct source for multi-day HSL GTFS-RT vehicle-position history.
- Bus Observatory is a strong public historical realtime archive for some transit systems. It stores daily compacted Parquet files of minute-by-minute observations in a public S3 bucket, but I did not verify Helsinki/HSL as a currently available feed there.
- MobilityData's GTFS resources list tools such as `gtfsrdb`, `GTFS-Realtime-Capsule`, and GTFS-realtime-to-SQL. These are useful if we want to run our own collector for several days before final submission.

## Recommended Exam Strategy

- Keep the official project as HSL bus reliability using our collected GTFS-RT history.
- Use the CSV exports in `reports/history_exports/` as the reproducible snapshot for Part 3 and Part 4.
- State the limitation honestly: the historical window is limited to periods when our Docker poller was running.
- If we need more history, run Docker for longer collection windows or add a scheduled Windows task that starts the poller during the day.
- Do not switch to another city just to get more history unless the instructor allows changing the dataset scope; that would weaken the Helsinki-focused story.

## Sources Checked

- HSL GTFS-RT docs: https://hsldevcom.github.io/gtfs_rt/
- HSL open data: https://www.hsl.fi/en/hsl/open-data
- HSL transitdata repository: https://github.com/HSLdevcom/transitdata
- Transitland historical static GTFS discussion: https://www.transit.land/news/2017/10/10/transitland-historical-feed-versions.html
- Transitland HSL static feed page: https://www.transit.land/feeds/f-ud9-helsinginseudunliikenne
- Bus Observatory docs: https://api.busobservatory.org/docs
- MobilityData/GTFS archival-tool list: https://staging.gtfs.org/resources/gtfs-realtime/
