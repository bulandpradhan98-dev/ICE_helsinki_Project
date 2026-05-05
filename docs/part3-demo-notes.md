# Part 3 Dashboard Demo Notes

Use these notes for the report, screenshots, or presentation demo.

## What To Show

- Live vehicle map: orange dots show live HSL bus vehicle positions from GTFS-RT.
- Static-vs-realtime route comparison: selected route line and stop markers show GTFS schedule context and live delay status.
- Cluster layer: teal/orange/red stop markers show KMeans reliability profiles and DBSCAN hotspots.
- Anomaly layer: pulsing red markers show Isolation Forest / LOF anomaly detections.
- Route drilldown: selected route panel shows route OTP, live comparison counts, hotspots, active anomalies, and prediction coverage.

## Suggested Screenshot Sequence

1. Full dashboard with live bus dots.
2. Turn on cluster layer and capture hotspot colors.
3. Turn on anomaly layer and capture pulsing red markers.
4. Click one hotspot or anomaly and capture the popup.
5. Select a route and capture the model-insight chips in the selected route panel.

## Method Summary For Report

The project implements two Part 3 data-mining categories. KMeans and DBSCAN are used for clustering and pattern discovery across route-stop-hour performance windows. Isolation Forest and Local Outlier Factor are used for anomaly detection on rolling GTFS-RT feature windows. The outputs are integrated into the dashboard as map layers and KPI tiles.

## Limitation To Mention

The Helsinki fast path uses available GTFS-RT snapshots and pseudo-labels instead of a long official incident archive. Missing TripUpdates are treated as missing realtime coverage, not as proof that a trip is on time.
