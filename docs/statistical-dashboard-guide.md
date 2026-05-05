# Statistical Analytics Dashboard Guide

This guide explains the new dashboard section added below the live map.

## Design Intent

The dashboard now separates two views:

- **Top command center:** high-level route, live-feed, coverage, and model-health KPIs visible immediately when the dashboard opens.
- **Live map:** operational view of where buses are now.
- **Statistical intelligence:** analytical view of what the data and models say about reliability patterns.

This follows modern dashboard practice: show a small number of high-value KPIs, give context, make anomalies explainable, and avoid overwhelming the user with too many disconnected charts.

## Panels To Explain In The Presentation

### Top Command Center

This is the first thing the viewer sees.

- **Live buses:** number of GTFS-RT bus vehicles currently available.
- **Modelled routes:** routes detected from route metrics, model clusters, anomalies, or live vehicles.
- **Prediction coverage:** how much GTFS-RT prediction signal exists in the model features.
- **Anomaly watchlist:** active anomaly windows and DBSCAN hotspot count.
- **Selected route intelligence:** route-specific live buses, hotspots, anomaly windows, delay, and coverage.

Speaking line:

"This command center makes the route analytics visible immediately, even before exploring the map."

### Bus Network Analytics

This is the high-level command strip.

- **Live bus dots:** number of GTFS-RT bus vehicles currently shown on the map.
- **Freshness:** how many minutes old the latest vehicle-position poll is.
- **Coverage:** average prediction coverage from the latest model feature windows.

Speaking line:

"This tells us whether the live feed is active enough to trust the current dashboard state."

### Route Health Distribution

This stacked bar summarizes route-level performance categories.

- **Good:** routes with stronger observed reliability.
- **Watch:** routes that may need monitoring.
- **Poor:** routes with weaker performance.

Speaking line:

"This is the quickest planner-level view: how much of the bus network is healthy, needs watching, or looks weak."

### Prediction Coverage

This radial gauge shows how complete the GTFS-RT prediction signal is.

Speaking line:

"Coverage is important because a missing realtime prediction should not be interpreted as an on-time bus. It is a data-quality signal."

### Live Model Watchlist

This radial gauge shows active anomaly windows from the model layer.

Speaking line:

"These are not automatically confirmed disruptions. They are model-generated windows that deserve investigation."

### Highest Average Delay

This ranked list shows the bus routes with the highest average delay in the available route metrics.

Speaking line:

"This gives a practical route-prioritization view for planners."

### Vehicle Status Split

This shows current GTFS-RT vehicle status categories such as stopped at, in transit to, or unknown.

Speaking line:

"This panel explains what the live bus dots are doing right now."

### Reliability Labels

This shows cluster labels from the model layer.

Speaking line:

"These labels summarize recurring reliability patterns found by clustering, so the map is not only showing dots but interpretable reliability groups."

### Anomaly Reasons

This panel groups anomaly windows by reason.

Speaking line:

"This makes anomaly detection explainable by showing whether anomalies are driven by coverage, feed freshness, or unusual model behavior."

## Screenshot Evidence

- `reports/screenshots/hsl-bus-statistical-analytics-dashboard.png`
- `reports/screenshots/hsl-bus-industry-analytics-dashboard.png`

## Presentation Advice

Use the statistical dashboard after the map demo:

1. Show live bus dots and route network on the map.
2. Scroll to the statistical dashboard.
3. Explain coverage first because it tells whether realtime data is trustworthy.
4. Explain route health and highest delay routes.
5. Explain clustering as pattern discovery.
6. Explain anomalies as a watchlist, not guaranteed disruption labels.
