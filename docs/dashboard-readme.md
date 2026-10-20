# Dashboard README: HSL Bus Reliability Analyzer

This document explains the live dashboard in simple but technical language. Use it when presenting the project, answering viva questions, or teaching someone what each part of the dashboard means.

## 1. Dashboard Purpose

The dashboard is a bus-only reliability command center for Helsinki Region Transport (HSL). It combines:

- Static GTFS data: planned bus routes, stops, trips, stop times, and route shapes.
- GTFS-RT VehiclePositions: live bus locations.
- GTFS-RT TripUpdates: predicted stop arrivals and delays.
- Model outputs: clustering, hotspot detection, and anomaly scoring.
- Schedule adherence metric: whether a bus is early, on time, late, or static-only.

The main question answered by the dashboard is:

> Are HSL bus routes operating reliably compared with their planned GTFS schedule, and where should a transport planner investigate delays, weak realtime coverage, or unusual service behavior?

## 2. Bus-Only Scope

The raw HSL GTFS feed contains multiple public transport modes, but this project intentionally focuses on buses only. The backend and dashboard filter the route family to HSL bus route types `701`, `702`, and `704`.

These numbers are not route numbers. They are GTFS/HSL route type category codes used in the imported feed to identify bus-family services.

This bus-only decision makes the analysis easier to explain because bus reliability is directly connected to:

- route-level delays,
- stop-level delays,
- realtime vehicle movement,
- prediction coverage,
- schedule adherence,
- operational anomalies.

## 3. How To Open The Dashboard

Start the project:

```powershell
docker compose up -d
```

Open the dashboard:

```text
http://localhost:5173/
```

Open the backend API documentation:

```text
http://localhost:8000/docs
```

If the dashboard is empty, first check that Docker Desktop is running and that the backend, database, poller, and frontend containers are healthy.

## 4. Page Structure

The dashboard has four main areas:

- Executive command center: high-level summary at the top.
- Map stage: live bus map, route geometry, stop markers, clusters, and anomalies.
- Analyst dock and route explorer: route selection, live fleet details, and model summaries.
- Statistical intelligence section: analytics cards for reliability, coverage, anomaly pressure, ranking, and model interpretation.

## 5. Executive Command Center

This is the top summary section. It explains the project in one sentence and gives quick KPIs.

### Live Buses

This is the number of live bus vehicle dots currently loaded from GTFS-RT VehiclePositions after filtering.

Important: not every raw GTFS-RT vehicle is displayed. A bus must pass confidence checks:

- it must match a static GTFS bus route,
- it must have usable route context,
- it must have recent GTFS-RT information,
- it must have usable stop prediction context where required.

### Observed Routes

This shows how many bus routes have dashboard/model evidence. A route may appear because:

- it has live vehicles,
- it has model feature windows,
- it has cluster outputs,
- it has anomaly outputs.

### Prediction Coverage

Prediction coverage tells us how much usable GTFS-RT prediction signal is available for the model windows.

In simple words:

> Coverage tells us whether the realtime feed is rich enough to compare the planned schedule with live/predicted bus behavior.

High coverage means the dashboard has enough realtime signal. Low coverage means the route may be hard to judge confidently.

### Anomaly Watchlist

This shows how many model windows were flagged as unusual by anomaly detection.

Important wording for presentation:

> Anomalies are a watchlist, not confirmed incidents.

The model is saying "this route-stop-hour behavior looks unusual compared with the available data." A planner should investigate it, not automatically treat it as a proven disruption.

## 6. Selected Route Intelligence

This card explains the currently selected route.

It shows:

- route short name or route id,
- number of live buses on that route,
- number of model hotspots,
- number of anomaly windows,
- OTP percentage,
- average delay,
- prediction coverage.

### OTP

OTP means On-Time Performance.

In this project, a bus is treated as on time if its delay is between:

```text
-1 minute and +5 minutes
```

That means:

- earlier than -1 minute = early,
- between -1 and +5 minutes = on time,
- later than +5 minutes = late.

OTP percentage is:

```text
on-time observations / total scored observations
```

Example:

```text
OTP 82% means 82 out of every 100 scored observations were within the accepted on-time window.
```

### Average Delay

Average delay is the mean delay in minutes for the selected route from computed model/metric windows.

Positive values mean late on average. Negative values mean early on average.

### Coverage

Coverage shows whether the route has enough realtime prediction information to support the comparison.

If coverage says "waiting for coverage", it means that route has not yet received enough model evidence or usable realtime prediction windows.

## 7. Map Stage

The map is the central visual part of the dashboard. It uses MapLibre and OpenStreetMap tiles.

The map contains several layers:

- bus route network layer,
- selected route layer,
- live bus vehicle layer,
- stop comparison layer,
- model cluster layer,
- live anomaly layer.

### Route Network Layer

This is the faint background route network. It shows the static GTFS bus route shapes.

Meaning:

> This is where buses are scheduled/planned to operate according to GTFS.

### Selected Route Layer

When a user selects a route from the route explorer, the selected route is drawn more strongly on the map.

Meaning:

> This is the planned route geometry for the route currently being inspected.

### Live Bus Dots

Orange dots represent live buses from GTFS-RT VehiclePositions.

Meaning:

> This is where the bus is currently reported to be by the realtime feed.

Clicking a live bus opens a vehicle-centric popup with:

- route or line label,
- vehicle label,
- trip id if provided,
- current status,
- next stop if available,
- current stop context,
- next stop delay,
- speed if reported,
- last update time,
- upcoming stop predictions if available.

### Stop Comparison Markers

Stop markers compare selected route stops against realtime status.

They answer:

> At this stop, does the realtime prediction look early, on time, late, or static-only?

## 8. Control Center

The Control Center manages map layers and backend jobs.

### Show Stop Markers

Turns the stop comparison markers on or off.

Use this when the map is crowded. It helps switch between a clean route view and a detailed stop-by-stop reliability view.

### Show Clusters

Turns model clustering points on or off.

These points come from Part 3 data mining. They show reliability groups discovered from bus route-stop-hour features.

### Show Anomalies

Turns anomaly markers on or off.

These are windows flagged by Isolation Forest or LOF as unusual.

### Auto Refresh

Keeps the live layers updated automatically.

The refresh interval can be set to:

- 10 seconds,
- 30 seconds,
- 60 seconds.

### Import Static GTFS

Downloads/imports the latest static HSL GTFS package into the database.

This updates planned routes, stops, trips, stop times, and shapes.

### Poll GTFS-RT

Fetches realtime GTFS-RT data manually.

This is useful if the dashboard looks stale and you want to force a realtime poll.

### Recompute Metrics

Recalculates schedule adherence metrics using the latest static and realtime data.

This supports OTP, early/late/on-time counts, and route-level summaries.

### Build Model Features

Creates route-stop-hour feature windows used by the data science models.

Each feature window summarizes a route and stop during a time bucket. It may include:

- mean delay,
- median delay,
- delay spread,
- on-time ratio,
- late ratio,
- early ratio,
- prediction coverage,
- vehicle observation count,
- route type,
- hour,
- weekday/weekend flag,
- stop geometry.

In simple words:

> Build model features turns raw transit events into clean machine-learning rows.

### Run Clustering

Runs clustering models:

- KMeans: groups route-stop windows by similar reliability behavior.
- DBSCAN: detects dense spatial/operational hotspot groups and noise points.

### Score Anomalies

Runs anomaly detection:

- Isolation Forest,
- Local Outlier Factor (LOF).

This produces the anomaly watchlist shown in the dashboard.

### Refresh Data

Refreshes dashboard API data without necessarily rerunning all backend jobs.

Use this after a backend job completes.

## 9. Route Explorer

The route explorer lists bus routes available in the current dashboard evidence.

Each route card shows:

- route short name,
- number of live buses,
- number of model windows,
- route reliability label or OTP percentage,
- number of model hotspots.

The route explorer does not mean "all HSL routes in the raw GTFS feed." It means routes that currently have live or model evidence in this bus-focused dashboard.

Clicking a route:

- highlights its static GTFS route shape,
- loads stop comparison markers,
- updates selected route intelligence,
- filters the explanation context to that route.

## 10. Analyst Dock

The Analyst Dock has two tabs:

- Fleet,
- Models.

### Fleet Tab

Shows the latest live buses currently available.

Each row normally contains:

- route number,
- vehicle label,
- stop or next-stop context,
- GTFS-RT status such as `IN_TRANSIT_TO`, `INCOMING_AT`, or `STOPPED_AT`,
- latest update time.

Clicking a vehicle selects it on the map and opens the vehicle popup.

### Models Tab

Shows the model evidence for Part 3:

- feature windows,
- model clusters,
- anomaly windows,
- hotspot counts,
- reliability labels.

Use this tab when explaining the data science part of the project.

## 11. Statistical Intelligence Section

This section turns the live system into a presentation-ready analytics dashboard.

### Bus Network Analytics

This is the analytics cockpit. It separates:

- live operations: live bus dots, feed freshness, coverage,
- model interpretation: clusters, route ranking, anomalies, reliability labels.

### Route Health Distribution

This card groups scored routes into:

- Good: OTP >= 90%,
- Watch: OTP from 80% to 89.9%,
- Poor: OTP < 80%.

Important:

> This card is based only on routes with computed 24-hour OTP. Live-only routes can appear in the route explorer before they receive scored OTP.

### Prediction Coverage

This radial meter shows how much realtime prediction signal is available.

High coverage means stronger confidence. Low coverage means the dashboard may know the vehicle exists, but may not have enough prediction detail for strong schedule comparison.

### Live Model Watchlist

This is the anomaly pressure card.

It shows:

- active anomaly windows,
- pressure percentage,
- scored windows,
- latest anomaly bucket.

Use this language:

> A high anomaly pressure means the system found many unusual route-stop-hour windows. It is a prioritization signal for planners, not a final diagnosis.

### Highest Average Delay

This ranks routes by average delay.

It helps answer:

> Which bus routes should planners inspect first because their average delay is highest?

### Vehicle Status Split

This groups live vehicles by GTFS-RT current status.

Common statuses:

- `IN_TRANSIT_TO`: bus is moving toward a stop,
- `INCOMING_AT`: bus is approaching a stop,
- `STOPPED_AT`: bus is at a stop.

### Reliability Labels

This summarizes the model cluster labels.

Common labels:

- `reliable`: good realtime and delay profile,
- `watch`: moderate reliability concern,
- `delay_hotspot`: delay-heavy pattern,
- `low_realtime_coverage`: weak realtime prediction signal.

### Anomaly Reasons

This explains why anomaly windows were flagged.

Examples:

- extreme delay,
- coverage dropout,
- stale feed,
- unusual realtime behavior.

## 12. Color Meaning

Use this as the dashboard color legend.

| Color | Where Used | Meaning |
| --- | --- | --- |
| Orange | Live vehicle dots | Live GTFS-RT bus vehicle location |
| Green | On-time/status/reliable charts | On time or reliable |
| Red | Late/anomaly/poor health | Late, unusual, or poor reliability |
| Blue | Early status or delay-hotspot category in notebook plots | Early in stop comparison, or delay hotspot in some static notebook plots |
| Grey | Static-only/no live comparison | Scheduled GTFS exists but usable realtime comparison is missing |
| Purple | Low realtime coverage cluster | Realtime prediction signal is weak |
| Teal | Reliable/default cluster points | More stable/reliable model pattern |
| Dark route line | Selected route | Static GTFS geometry of the route being inspected |
| Faint colored lines | Network background | Planned bus route network from static GTFS |

## 13. What The Dashboard Can Answer

The dashboard can answer:

- Which HSL bus routes are live right now?
- Where are buses on the map?
- Which selected route is performing well or poorly?
- Which stops are on time, early, late, or static-only?
- Which route-stop-hour windows form similar reliability groups?
- Where are model hotspots?
- Which windows are unusual and should be investigated?
- Is the GTFS-RT feed fresh enough to trust?
- Is prediction coverage strong enough for reliability analysis?

## 14. What The Dashboard Cannot Fully Prove

The dashboard is useful, but it has honest limitations.

It cannot always prove the true cause of delay. It can show that a bus or stop window looks late or unusual, but the reason may require external context such as traffic, roadworks, weather, events, or disruptions.

Missing TripUpdates do not automatically mean the bus is on time. Sometimes missing realtime data means the feed did not provide enough prediction detail.

Anomalies are not confirmed disruptions. They are model-generated watchlist items.

Next stop is shown only when the realtime feed and static schedule can be linked confidently. If the vehicle lacks usable stop/trip context, the dashboard avoids guessing.

## 15. Recommended 5-Minute Dashboard Walkthrough

Use this script when presenting.

1. Start with the project goal: "This dashboard checks HSL bus reliability by comparing planned GTFS schedules with live GTFS-RT data."
2. Point to the executive KPIs: "Here we see live buses, observed routes, prediction coverage, and anomaly watchlist."
3. Open the route explorer: "Routes shown here are bus routes with live/model evidence, not every raw HSL route."
4. Select a route: "The map now highlights the static planned route, while orange dots show live buses."
5. Click a bus dot: "This popup shows vehicle, trip, route, status, stop context, next stop, delay, speed, and update time if available."
6. Turn on stop markers: "Green means on time, red late, blue early, grey static-only."
7. Turn on clusters: "These are Part 3 model groups. They show reliability patterns discovered from feature windows."
8. Turn on anomalies: "These red pulsing markers are unusual windows from anomaly models."
9. Scroll to analytics: "This section summarizes route health, coverage, anomaly pressure, high-delay routes, fleet status, reliability labels, and anomaly reasons."
10. Finish with the planner conclusion: "The dashboard helps prioritize which routes and stops need investigation."

## 16. Main Conclusion

The dashboard shows that a GTFS plus GTFS-RT pipeline can support practical bus reliability analysis for Helsinki. It does not replace expert transport planning, but it gives planners a fast way to see live bus movement, compare it with the scheduled network, detect weak reliability patterns, and prioritize routes or stops for deeper investigation.

The strongest interpretation is:

> HSL bus reliability can be monitored using schedule adherence, realtime coverage, clustering, and anomaly detection. The dashboard turns raw transit feeds into operational evidence that helps planners decide where to investigate delays and service quality problems.

## 17. Best Presentation Sentence

If you need one simple explanation, say:

> This dashboard compares where buses are planned to be, where they are reported live, and what the models learn from repeated route-stop-hour patterns, so we can identify reliable routes, delay hotspots, weak realtime coverage, and unusual service behavior.

