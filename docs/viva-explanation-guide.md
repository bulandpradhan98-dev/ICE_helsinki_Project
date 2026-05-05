# HSL Bus Reliability Project Explanation Guide

Use this guide as the spoken story for the presentation or viva. The project should be explained as a bus reliability analysis, with the dashboard as supporting evidence.

## 1. Project Objective

The objective is to analyze public transport reliability for HSL bus services in Helsinki using GTFS schedule data and GTFS-Realtime feeds.

The main question is:

How reliably do bus services match their planned schedule, and which routes or stops show patterns that deserve further inspection?

## 2. Dataset Choice

The dataset comes from Helsinki Region Transport (HSL).

The project uses:

- Static GTFS for planned routes, stops, trips, stop times, service calendars, and route shapes.
- GTFS-RT vehicle positions for live bus locations.
- GTFS-RT trip updates for stop-level delay and prediction information where available.

This is suitable for urban mobility analysis because it combines spatial, temporal, categorical, and operational data.

## 3. Why Bus-Only

The original HSL feed is multimodal, but the modelling and dashboard focus only on bus route types `701`, `702`, and `704`.

This is the right scope because:

- buses operate in mixed street traffic and are more exposed to delay;
- bus reliability is directly connected to schedule adherence;
- live vehicle positions are meaningful on a city street map;
- keeping one mode avoids mixing bus, tram, metro, ferry, and rail behavior in the same model.

Explain this as a deliberate modelling decision, not a limitation.

## 4. Data Understanding

The important static GTFS files are:

- `routes.txt`: bus routes and route metadata.
- `stops.txt`: stop names and coordinates.
- `trips.txt`: scheduled trips for each route.
- `stop_times.txt`: planned arrival and departure times.
- `calendar.txt` and `calendar_dates.txt`: service availability.
- `shapes.txt`: route geometry for mapping.

The dataset is relational, so the files must be joined. The largest table is `stop_times.txt`, because every trip has multiple stop events.

## 5. Preprocessing

The preprocessing steps are:

- remove optional columns with missing values when they are not needed for reliability analysis;
- convert scheduled times into features such as hour and rush-hour indicator;
- encode categorical identifiers such as route, stop, and service IDs;
- scale coordinates for modelling while keeping original coordinates for mapping;
- aggregate detailed stop-time records into stop-level or route-stop-hour features.

For the live system, the backend also converts GTFS-RT messages into database tables and computes feature windows for modelling.

## 6. Core Metric

The core reliability metric is schedule adherence.

A bus event is considered on time if it is between `-1` minute early and `+5` minutes late.

In HSL GTFS-RT, the feed commonly gives predicted arrival/departure timestamps rather than an explicit delay value. The project calculates delay by matching each TripUpdate to the static GTFS trip and stop, then subtracting scheduled time from predicted realtime time. Missing delay fields are not treated as zero.

This creates three interpretation classes:

- early;
- on time;
- late.

## 7. Data Mining Techniques

The project uses clustering and anomaly detection.

### KMeans

KMeans groups bus route-stop windows into similar reliability profiles.

It helps answer:

Which bus stops or routes behave similarly?

### DBSCAN

DBSCAN finds dense spatial groups and reliability hotspots.

It helps answer:

Are reliability issues concentrated in specific areas or corridors?

### Isolation Forest

Isolation Forest detects unusual feature windows by finding observations that are easy to isolate from the rest.

It helps answer:

Which bus stop windows look operationally unusual?

### LOF

Local Outlier Factor compares each point with nearby points.

It helps answer:

Which bus stop windows are unusual compared with similar local behavior?

## 8. Model Evaluation

For clustering:

- Silhouette Score measures separation between clusters.
- Davies-Bouldin Index measures compactness and separation.
- Calinski-Harabasz Score measures cluster structure.
- Interpretability checks whether the cluster labels make operational sense.

For anomaly detection:

- precision, recall, F1 score, and Precision@K are calculated against pseudo-labels.
- pseudo-labels represent coverage dropouts, stale feeds, and unusual realtime behavior.

State clearly that pseudo-labels are used because there is no official labelled anomaly dataset.

## 9. Dashboard Walkthrough

The dashboard supports the analysis visually.

Show these parts in order:

1. Bus route map and live bus dots.
2. Route explorer showing bus routes only.
3. Selected vehicle details.
4. Selected route schedule comparison.
5. Cluster layer for reliability patterns.
6. Anomaly layer for unusual bus stop windows.
7. Model metrics and hotspot counts.

The dashboard is not the whole project. It is the interface that makes the analysis easier to inspect and explain.

## 10. Main Insights

The current strongest insights are:

- the HSL static GTFS feed is clean and well structured;
- bus-only filtering creates a focused and explainable analysis problem;
- clustering separates route-stop windows into reliability and coverage groups;
- anomaly detection highlights bus stop windows that deserve inspection;
- current GTFS-RT history is still limited, so coverage and freshness patterns are stronger than delay patterns.

## 11. Limitations

Important limitations:

- GTFS-RT trip matching can be noisy.
- HSL realtime data does not always provide stable trip identifiers.
- The stored realtime history is limited.
- Some delay values are derived from predicted timestamps rather than direct GTFS-RT delay fields.
- Pseudo-labels are not official ground truth.

These limitations should be presented honestly. They show that the project understands real-world transport data problems.

## 12. Future Work

Future improvements:

- collect GTFS-RT continuously for several days or weeks;
- add delay prediction when enough labelled delay history exists;
- compare weekday, weekend, and rush-hour bus reliability;
- improve vehicle-to-trip matching;
- add route-level recommendations for planners.

## 13. Ten-Minute Presentation Flow

Use this order:

1. Problem: bus reliability matters for passengers and planners.
2. Dataset: HSL GTFS and GTFS-RT.
3. Scope: bus-only route types `701`, `702`, `704`.
4. Preprocessing: cleaning, time features, encoding, scaling, aggregation.
5. Metric: schedule adherence from `-1` to `+5` minutes.
6. Models: KMeans, DBSCAN, Isolation Forest, LOF.
7. Evaluation: clustering metrics and anomaly pseudo-label metrics.
8. Dashboard: live map, route inspector, clusters, anomalies.
9. Insights: coverage, hotspots, route reliability.
10. Limitations and future work.
