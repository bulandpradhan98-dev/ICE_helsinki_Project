# HSL Bus Reliability Analyzer

This project is a bus-only urban mobility data-science project for analyzing **Helsinki Region Transport (HSL) bus reliability** using:

- **Static GTFS** for planned routes, stops, trips, stop times, and route shapes.
- **GTFS-RT Vehicle Positions** for live bus locations.
- **GTFS-RT Trip Updates** for realtime prediction and stop-update information.
- **Machine learning / data mining** for route reliability clustering and anomaly detection.
- **React + MapLibre dashboard** for live map inspection and statistical analytics.

The analysis is guided by a focused question:

> How reliable are HSL bus routes, where do reliability patterns or hotspots appear, and which realtime bus-operation windows look unusual?

The raw HSL feed contains multiple public-transport modes, but this project focuses on **bus-family GTFS `route_type` codes: `701` Regional Bus Service, `702` Express Bus Service, and `704` Local Bus Service**. These are **mode/category codes from the imported HSL GTFS feed**, not individual bus line numbers.

---

## 1. Project Objective

The project turns public HSL schedule and realtime feeds into an operational view of bus reliability. It:

1. Imports static GTFS schedules and GTFS-RT observations.
2. Links realtime vehicle and stop updates to the scheduled network.
3. Builds route-stop-hour reliability features.
4. Discovers recurring operating patterns with clustering.
5. Flags unusual operating windows with anomaly detection.
6. Exposes the results through a documented API, notebooks, and an interactive dashboard.

The central question is whether HSL bus routes are operating reliably, where recurring hotspots occur, and which operating windows deserve investigation.

---

## 2. What The Project Builds

The system has four main modules.

| Module | Purpose | Evidence in project |
|---|---|---|
| Ingestor | Downloads and stores static GTFS plus GTFS-RT realtime feeds | `backend/app/jobs/static_gtfs.py`, `backend/app/jobs/gtfs_rt_poller.py` |
| Linker / Feature Builder | Converts raw realtime updates into usable bus reliability feature windows | `backend/app/jobs/modeling.py` |
| Calculator / Models | Runs KMeans, DBSCAN, Isolation Forest, and LOF | `backend/app/jobs/modeling.py`, notebooks |
| Dashboard | Shows live buses, route analytics, clusters, hotspots, and anomalies | `frontend/src/App.tsx`, `frontend/src/components/MapPanel.tsx` |

### Repository Layout

```text
backend/                 FastAPI API, ingestion jobs, feature engineering, and models
frontend/                React, TypeScript, and MapLibre dashboard
notebooks/               Reproducible data-mining and evaluation notebooks
backend/sql/             PostgreSQL/PostGIS/TimescaleDB schema and seed SQL
docs/                    Architecture, dashboard, and implementation documentation
reports/                 Selected snapshots, screenshots, and project reports
scripts/                 Evidence-export and utility scripts
docker-compose.yml       Local multi-service environment
.env.example             Safe configuration template
```

### Data Flow

```text
HSL GTFS + GTFS-RT
        |
        v
Ingestion and PostgreSQL/PostGIS storage
        |
        v
Route-stop-hour feature engineering
        |
        +--> KMeans / DBSCAN clustering
        +--> Isolation Forest / LOF anomaly detection
        |
        v
FastAPI endpoints --> React/MapLibre dashboard
```

---

## 3. Technology Stack

| Layer | Technology | Why used |
|---|---|---|
| Backend API | Python FastAPI | Simple API layer for ingestion, model recompute, and dashboard data |
| Database | PostgreSQL + PostGIS + TimescaleDB | Relational, spatial, and time-series storage |
| GTFS processing | Python, GTFS tables, protobuf parsing | Handles schedule and realtime transit data |
| Data science | pandas, numpy, scikit-learn | Feature engineering, clustering, anomaly detection |
| Frontend | React + TypeScript | Interactive dashboard |
| Map | MapLibre GL JS | Open-source vector map rendering |
| Deployment | Docker Compose | Reproducible local environment |

---

## 4. How To Run

Start Docker Desktop, then create the local environment file:

```powershell
Copy-Item .env.example .env
```

Build and start the services:

```powershell
docker compose up -d --build
```

Open:

- Dashboard: `http://localhost:5173/`
- API docs: `http://localhost:8000/docs`

On a new database, import the current static HSL schedule:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/ingestion/static/import
```

The realtime poller runs continuously after startup. Model features, clusters, and anomaly scores can be generated from the dashboard control center or the API endpoints listed below.

Stop safely:

```powershell
docker compose down
```

Important:

- `docker compose down` stops containers but keeps the database volume.
- Do **not** use `docker compose down -v` unless you intentionally want to delete collected GTFS-RT history.

---

## 5. Dataset Explanation

### Static GTFS

Static GTFS describes the scheduled transit system:

| GTFS file/table | Meaning |
|---|---|
| `routes.txt` | Bus routes and route types |
| `stops.txt` | Stop names and coordinates |
| `trips.txt` | Scheduled trips on routes |
| `stop_times.txt` | Scheduled stop arrival/departure times |
| `shapes.txt` | Route geometry for map lines |
| `calendar.txt` / `calendar_dates.txt` | Service days and exceptions |

### GTFS-RT

GTFS-RT gives live or near-live updates:

| Feed | Meaning |
|---|---|
| Vehicle Positions | Where buses are currently reported |
| Trip Updates | Predicted arrival/departure information |
| Service Alerts | Disruptions and notices, parked for future enhancement |

### Why Bus-Only?

The HSL feed is multimodal, but buses are selected because:

- Bus reliability is directly connected to delays and schedule adherence.
- Buses operate on road networks and are sensitive to traffic conditions.
- A bus-only scope makes clustering and anomaly detection easier to explain.
- A single-mode scope keeps feature definitions and model interpretation consistent.

### What Do `701`, `702`, And `704` Mean?

These values are **GTFS `route_type` category codes** in the imported HSL feed. They are not route names like bus `30`, `550`, or `90N`.

In this project they are treated as the HSL bus-family modes:

| `route_type` code | Meaning in this project | Why included |
|---:|---|---|
| `701` | Bus-family service | Core bus operations for reliability analysis |
| `702` | Bus-family service variant | Included so bus services represented with this HSL code are not accidentally excluded |
| `704` | Bus-family service variant | Included for the same reason: it belongs to the bus-focused service family in the imported feed |

Why this matters:

- `route_id` identifies a specific route in the GTFS database.
- `route_short_name` is the user-facing route label, such as `30`, `550`, or `90N`.
- `route_type` identifies the transport mode/category.

So when the project says:

```sql
route_type IN (701, 702, 704)
```

it means:

> Keep only HSL bus-family services and remove other public transport modes from modelling and interpretation.

---

## 6. Data Understanding

### Problem Statement

The project studies:

> HSL bus reliability using static schedules and realtime GTFS-RT data.

The practical questions are:

- Which routes or stops show similar reliability patterns?
- Where do reliability hotspots appear?
- Which bus-operation windows look unusual?
- How fresh and complete is the realtime prediction signal?

### Data Types

| Attribute type | Examples |
|---|---|
| Numerical | delay minutes, speed, coverage ratio, vehicle count |
| Categorical | route ID, stop ID, route type, vehicle status |
| Time series | GTFS-RT recorded timestamps, hourly model buckets |
| Spatial | stop latitude/longitude, route shapes, vehicle coordinates |

### Challenges

- HSL GTFS-RT may not provide stable GTFS `trip_id` values.
- Realtime feed availability changes throughout the day.
- Missing TripUpdates do not automatically mean buses are on time.
- Historical GTFS-RT only accumulates while the local poller is running.
- Matching static GTFS schedules to realtime observations is noisy.

### Reliability Calculation Note

HSL TripUpdates usually provide predicted `arrival.time` and `departure.time` values, not an explicit `delay` field. The project therefore calculates delay as:

`GTFS-RT predicted arrival/departure time - GTFS static scheduled arrival/departure time`

If the protobuf `delay` field is absent, it is treated as missing, not as zero. This is important because otherwise missing delay values would incorrectly make every bus look on time.

---

## 7. Data Preparation

Preprocessing turns raw GTFS and GTFS-RT into model-ready features.

### Main Preprocessing Steps

| Step | What was done |
|---|---|
| Bus filtering | Analysis focuses on `route_type IN (701, 702, 704)`, meaning HSL bus-family mode/category codes rather than individual route numbers |
| Timestamp conversion | Realtime timestamps converted into hour, weekday, weekend flags |
| Aggregation | Raw stop/trip updates aggregated into route-stop-hour windows |
| Feature engineering | Delay, coverage, feed freshness, vehicle count, and spatial features created |
| Missing values | Missing realtime fields are handled using coverage/freshness indicators |
| Encoding | Route, stop, status, and route type fields retained for grouping/interpretation |
| Scaling | Model features are standardized before clustering/anomaly detection |

### Model Features

The feature table includes:

- Mean delay.
- Median delay.
- 95th percentile absolute delay.
- Delay standard deviation.
- On-time ratio.
- Late ratio.
- Early ratio.
- Prediction coverage ratio.
- Vehicle observation count.
- Feed age / freshness.
- Route type.
- Hour of day.
- Day of week.
- Weekend flag.
- Stop latitude and longitude.

Implementation and reproducible analysis are available in `backend/app/jobs/modeling.py` and `notebooks/03_data_mining_gtfs_rt.ipynb`.

---

## 8. Modeling Methods

The project combines complementary pattern-discovery and anomaly-detection methods.

### Technique A: Clustering / Pattern Discovery

#### KMeans

Purpose:

- Groups route-stop-hour windows with similar bus reliability behavior.

Why it fits:

- Easy to explain.
- Good for route reliability segmentation.
- Gives clear cluster labels for dashboard interpretation.

Selected latest run:

- `k = 2`
- `n_init = 20`

Evaluation evidence:

- Silhouette around `0.737`
- Davies-Bouldin around `0.412`
- Calinski-Harabasz around `12,546`

#### DBSCAN

Purpose:

- Finds dense reliability hotspots and separates sparse/noisy windows.

Why it fits:

- Useful for spatial hotspot discovery.
- Does not force every point into a cluster.
- Helps planners see areas requiring investigation.

Selected latest run:

- `eps = 0.4`
- `min_samples = 20`

Evaluation evidence:

- Silhouette around `0.769`
- Noise share around `0.037`
- Cluster count around `2`

### Technique B: Anomaly Detection

#### Isolation Forest

Purpose:

- Detects unusual bus reliability windows.

Why it fits:

- Works well for unsupervised anomaly detection.
- Can handle multiple numerical features.
- Produced a strong balance between precision and recall.

Selected latest run:

- `n_estimators = 200`
- `max_samples = 256`
- `contamination = 0.05`

Evaluation evidence:

- Precision@K around `0.915`
- Recall around `0.464`
- False-alarm share around `0.0042`

#### Local Outlier Factor

Purpose:

- Detects local deviations from nearby reliability behavior.

Why it fits:

- Useful comparison against Isolation Forest.
- More conservative, high-confidence anomaly detection.

Selected latest run:

- `n_neighbors = 35`
- `contamination = 0.01`

Evaluation evidence:

- Precision@K around `1.000`
- Recall around `0.094`
- False-alarm share around `0.000`

Model implementation and saved results are available in `backend/app/jobs/modeling.py`, `notebooks/03_data_mining_gtfs_rt.ipynb`, and `reports/snapshots/bus_model_snapshot_latest.json`.

---

## 9. Model Evaluation And Interpretation

### Clustering Metrics

| Metric | Meaning |
|---|---|
| Silhouette Score | Higher means clusters are better separated |
| Davies-Bouldin Index | Lower means clusters are more compact and separated |
| Calinski-Harabasz Score | Higher means better defined clusters |

### Anomaly Metrics

Because true disruption labels are not available, the project uses pseudo-labels:

- Extreme delay windows.
- Coverage dropouts.
- Stale feed windows.
- Unusual realtime/model behavior.

| Metric | Meaning |
|---|---|
| Precision@K | How many top-ranked anomalies match pseudo-labels |
| Recall | How many pseudo-labelled anomalies were caught |
| F1 proxy | Balance between precision and recall |
| False-alarm share | How much alert noise the model creates |

### Interpretation

The evaluation supports these conclusions:

- Clustering can group bus reliability windows into interpretable operational patterns.
- DBSCAN can identify reliability hotspots.
- Isolation Forest is stronger for broader anomaly discovery.
- LOF is more conservative and useful for high-confidence anomaly flags.
- Realtime coverage is an important limitation and should be shown, not hidden.

The full evaluation workflow is in `notebooks/04_model_evaluation_interpretation.ipynb`.

---

## 10. Dashboard Explanation

The dashboard has two major layers.

### Live Map

| Visual element | Meaning |
|---|---|
| Orange/yellow dots | Live HSL bus vehicles from GTFS-RT that pass the quality filter |
| Route lines | Static GTFS bus route geometry |
| Teal/purple cluster points | Modelled reliability groups |
| Orange hotspot points | DBSCAN reliability hotspots |
| Red anomaly points | Isolation Forest / LOF anomaly windows |

The dashboard intentionally hides low-confidence live bus rows. A vehicle is shown only when it has:

- A recent GTFS-RT vehicle position.
- A matched static GTFS bus route using the bus-family `route_type` filter.
- A matched static GTFS stop name.
- A recent matching GTFS-RT TripUpdate.
- At least one stop-time update in the TripUpdate payload.
- A usable current vehicle status.

This prevents the map from showing buses without enough context for reliable interpretation.

### Statistical Analytics Dashboard

The redesigned dashboard now starts with an industry-style command center.

| Panel | Meaning |
|---|---|
| Live buses | Current GTFS-RT bus vehicles visible in the feed |
| Modelled routes | Routes represented by live vehicles, clusters, or route metrics |
| Prediction coverage | How much realtime prediction signal exists |
| Anomaly watchlist | Current model-generated anomaly windows |
| Selected route intelligence | Route-specific buses, hotspots, anomalies, coverage, and delay |
| Route health distribution | Good/watch/poor route split |
| Highest average delay | Routes ranked by delay or live/model evidence |
| Vehicle status split | Current bus movement/status categories |
| Reliability labels | Cluster interpretation from model output |
| Anomaly reasons | Explainable anomaly categories |

The map shows where buses are, while the statistical panels explain what the available data means.

Evidence:

- `reports/screenshots/hsl-bus-dashboard-live.png`
- `reports/screenshots/hsl-bus-statistical-analytics-dashboard.png`
- `reports/screenshots/hsl-bus-industry-analytics-dashboard.png`
- `docs/dashboard-readme.md`
- `docs/statistical-dashboard-guide.md`

---

## 11. API Endpoints Used

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/ingestion/status` | Static and realtime ingestion status |
| `POST /api/v1/ingestion/realtime/poll` | Manually poll GTFS-RT |
| `GET /api/v1/network/vehicles?mode=bus` | Live bus vehicle GeoJSON |
| `GET /api/v1/network/geometry?mode=bus` | Static bus network geometry |
| `GET /api/v1/models/status` | Feature/cluster/anomaly model status |
| `POST /api/v1/models/features/recompute` | Recompute feature windows |
| `POST /api/v1/models/clusters/recompute` | Recompute KMeans and DBSCAN |
| `POST /api/v1/models/anomalies/recompute` | Recompute Isolation Forest and LOF |
| `GET /api/v1/models/clusters` | Cluster/hotspot GeoJSON |
| `GET /api/v1/models/anomalies/live` | Live anomaly GeoJSON |
| `GET /api/v1/routes/{route_id}/model-insights` | Selected route model details |

---

## 12. Project Artifacts

### Notebooks

- `notebooks/03_data_mining_gtfs_rt.ipynb`
- `notebooks/04_model_evaluation_interpretation.ipynb`

### Reports And Snapshots

- `reports/snapshots/bus_model_snapshot_compact.json`
- `reports/snapshots/bus_model_snapshot_latest.json`
- `reports/bus_model_snapshot_summary.md`

### Documentation

- `docs/dashboard-readme.md`
- `docs/statistical-dashboard-guide.md`
- `docs/architecture.md`
- `docs/reference-architecture-notes.md`
- `docs/historical-gtfs-rt-notes.md`

---

## 13. Troubleshooting

Use this section if the application or notebook cells fail.

### Step 1: Start Docker

```powershell
docker compose up -d
```

### Step 2: Confirm The API Is Alive

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```

Expected:

```text
status: ok
```

### Step 3: Confirm Model Outputs Exist

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/models/status
```

If feature windows, clusters, or anomalies are missing, run:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/models/features/recompute
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/models/clusters/recompute
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/models/anomalies/recompute
```

### Step 4: If Python Packages Are Missing

Install notebook dependencies in the Jupyter/Anaconda environment:

```powershell
pip install -r requirements-notebooks.txt
```

Common missing packages:

- `pandas`
- `numpy`
- `scikit-learn`
- `matplotlib`
- `requests`
- `seaborn`

### Step 5: If API Cells Fail

Check:

- Docker is running.
- Backend is on `http://localhost:8000`.
- Notebook `API_BASE` is set to `http://localhost:8000/api/v1`.

If the API is not available, the notebooks should still use saved evidence from:

- `reports/snapshots/`
- `reports/history_exports/`

### Step 6: If Plots Do Not Show

Run this inside the notebook:

```python
%matplotlib inline
```

Then rerun the plotting cells.

### Step 7: Use Saved Snapshots Offline

If the live API is unavailable, the notebooks can use the reproducible snapshots under `reports/snapshots/` for offline inspection.
