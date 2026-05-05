# Reference Architecture Notes

This project keeps the HSL bus reliability scope, but it borrows ideas from several mature transit dashboard and GTFS-RT projects. These references are used as **design and architecture inspiration**, not as a full fork or replacement of the current project.

## Why We Did Not Fully Fork A Repo

The deadline goal is to finish Part 3 and Part 4 strongly. Replacing the project with a full fork would create avoidable risk:

- The current project already has HSL static GTFS ingestion.
- The current project already has HSL GTFS-RT polling.
- The current project already has bus-only model outputs for KMeans, DBSCAN, Isolation Forest, and LOF.
- The current project already has notebooks and evidence files aligned to the exam.

So the safer strategy is:

> Keep our HSL bus reliability pipeline, then borrow proven layout, metric, and matching ideas from reference projects.

## Reference 1: `crate/devrel-gtfs-transit`

Repository:

- https://github.com/crate/devrel-gtfs-transit

What it does:

- Captures GTFS and GTFS-RT data.
- Stores transit route, trip, stop, and vehicle movement data.
- Provides a map frontend where live vehicles can be inspected.

What we borrowed:

- Live vehicle map concept.
- Vehicle-centric popup/inspector idea.
- GTFS + GTFS-RT storage-first architecture.
- The idea that a demo can be agency-specific while still using standard GTFS concepts.

How our project differs:

- We use PostgreSQL/PostGIS/TimescaleDB instead of CrateDB.
- We focus on HSL buses instead of WMATA/DC Metro.
- We add Part 3/Part 4 data-science modelling: KMeans, DBSCAN, Isolation Forest, and LOF.

## Reference 2: `transitmatters/t-performance-dash`

Repository:

- https://github.com/transitmatters/t-performance-dash

TransitMatters Labs context:

- https://transitmatters.org/transitmatters-labs
- https://transitmatters.org/blog/transitmatters-launches-all-new-data-dashboard

What it does:

- Provides a public-facing transit performance dashboard.
- Frames transit data in a way useful for riders, advocates, journalists, and planners.
- Emphasizes clear metrics and drilldowns rather than raw data dumps.

What we borrowed:

- Dashboard-first storytelling.
- Strong KPI hierarchy.
- Separation between system overview and detail exploration.
- The idea that transit dashboards must explain service quality, not just show dots.

How our project differs:

- Their project focuses on MBTA performance.
- Our project focuses on HSL bus reliability.
- Our dashboard combines live map, model layers, and exam-oriented data-science evidence.

## Reference 3: `zackAemmer/transit-vis`

Repository:

- https://github.com/zackAemmer/transit_vis

What it does:

- Visualizes GTFS-RT bus delays.
- Frames delay as an operational planning problem.
- Uses network/corridor analysis ideas.

What we borrowed:

- Delay and reliability framing.
- The idea that bus delay analysis should help locate problematic stops, streets, or route segments.
- The importance of explaining uncertainty and variation, not only average delay.

How our project differs:

- We use HSL GTFS/GTFS-RT.
- We add clustering and anomaly detection for the course rubric.
- We include a live dashboard and saved evidence exports.

## Reference 4: `derhuerst/hafas-gtfs-rt-feed`

Repository:

- https://github.com/derhuerst/hafas-gtfs-rt-feed

What it does:

- Builds a GTFS-RT feed by polling realtime HAFAS data.
- Matches realtime vehicle/trip data against static GTFS.
- Uses separate pipeline components for monitoring, matching, and serving.

What we borrowed:

- The idea that realtime-to-static matching is a separate hard problem.
- The need for matching logic between live records and GTFS schedules.
- The idea that unmatched or weakly matched realtime records should not be blindly trusted.

How our project differs:

- HSL already provides GTFS-RT, so we do not generate a new GTFS-RT feed.
- Our matching problem is about linking HSL GTFS-RT vehicle/trip updates to static GTFS for reliability analysis.
- We use a simpler FastAPI/Postgres architecture instead of a NATS streaming architecture.

## Reference 5: `OpenDataVBB/gtfs-rt-feed`

Repository:

- https://github.com/OpenDataVBB/gtfs-rt-feed

How it informs our thinking:

- Transit realtime feeds often require agency-specific matching rules.
- Static and realtime data may not share perfect identifiers.
- A robust GTFS-RT system needs to handle imperfect feeds instead of assuming ideal data.

## How These References Map To Our Final Project

| Reference idea | Our implementation |
|---|---|
| Live vehicle map | MapLibre live HSL bus dots |
| Vehicle-centric popup | Bus inspector and selected vehicle panel |
| Performance dashboard layout | Top command center, KPI cards, route ranking, model panels |
| Delay/reliability framing | Delay, coverage, feed freshness, hotspots, anomaly windows |
| GTFS-RT matching challenge | HSL route/start-time/direction/TripUpdate matching and confidence filtering |
| Avoid weak realtime claims | Low-confidence buses are hidden from the dashboard |
| Historical evidence | CSV exports and timestamped JSON snapshots |
| Data mining extension | KMeans, DBSCAN, Isolation Forest, LOF notebooks |

## Final Position For The Report

The project should be described as:

> A custom HSL bus reliability analyzer inspired by existing GTFS/GTFS-RT dashboard and matching projects, but implemented around our own HSL data pipeline, bus-only scope, clustering, anomaly detection, and exam notebooks.

This is stronger than saying we simply forked a project, because it shows independent design and data-science work.
