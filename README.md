# HSL Bus Reliability Analyzer

This project is a bus-only urban mobility data-science project for analyzing **Helsinki Region Transport (HSL) bus reliability** using:

- **Static GTFS** for planned routes, stops, trips, stop times, and route shapes.
- **GTFS-RT Vehicle Positions** for live bus locations.
- **GTFS-RT Trip Updates** for realtime prediction and stop-update information.
- **Machine learning / data mining** for route reliability clustering and anomaly detection.
- **React + MapLibre dashboard** for live map inspection and statistical analytics.

The exam story is intentionally focused:

> How reliable are HSL bus routes, where do reliability patterns or hotspots appear, and which realtime bus-operation windows look unusual?

The raw HSL feed contains multiple public-transport modes, but this project focuses on **bus-family GTFS `route_type` codes -- `701` Regional Bus Service, `702`Express Bus Service , and `704`Local Bus Service** so the modelling and explanation remain consistent. These are **mode/category codes from the imported HSL GTFS feed**, not individual bus line numbers.

---

## 1. Project Objective

The course objective is to apply data science to real urban mobility data. This project satisfies that by:

1. Selecting a real public transport dataset from HSL.
2. Understanding GTFS and GTFS-RT structure.
3. Preprocessing raw schedule and realtime data into route-stop-time features.
4. Applying at least two data mining techniques:
   - Clustering / pattern discovery.
   - Anomaly detection.
5. Evaluating model outputs using appropriate metrics.
6. Communicating insights through notebooks, exported evidence, and a dashboard.

The dashboard is not only a web demo. It is the visual proof layer for the notebook analysis.

---

## 2. What The Project Builds

The system has four main modules.

| Module | Purpose | Evidence in project |
|---|---|---|
| Ingestor | Downloads and stores static GTFS plus GTFS-RT realtime feeds | `backend/app/jobs/static_gtfs.py`, `backend/app/jobs/gtfs_rt_poller.py` |
| Linker / Feature Builder | Converts raw realtime updates into usable bus reliability feature windows | `backend/app/jobs/modeling.py` |
| Calculator / Models | Runs KMeans, DBSCAN, Isolation Forest, and LOF | `backend/app/jobs/modeling.py`, notebooks |
| Dashboard | Shows live buses, route analytics, clusters, hotspots, and anomalies | `frontend/src/App.tsx`, `frontend/src/components/MapPanel.tsx` |

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

Start Docker Desktop first.

```powershell
docker compose up -d
```

Open:

- Dashboard: `http://localhost:5173/`
- API docs: `http://localhost:8000/docs`

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
- The dashboard and report stay focused for the exam.

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

## 6. Part 1: Data Understanding

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

Evidence:

- Existing Part 1 notebook from the course submission.
- `docs/viva-explanation-guide.md`
- `docs/exam-proof-pack.md`

---

## 7. Part 2: Data Preprocessing

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

Evidence:

- `reports/history_exports/bus_model_feature_windows_recent.csv`
- `notebooks/03_data_mining_gtfs_rt.ipynb`

---

## 8. Part 3: Data Mining Techniques

The rubric requires at least two techniques. This project uses two categories and four algorithms.

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

Evidence:

- `notebooks/03_data_mining_gtfs_rt.ipynb`
- `reports/snapshots/bus_model_snapshot_latest.json`
- `reports/history_exports/bus_cluster_assignments_latest.csv`
- `reports/history_exports/bus_anomaly_scores_latest.csv`

---

## 9. Part 4: Model Evaluation And Interpretation

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

Evidence:

- `notebooks/04_model_evaluation_interpretation.ipynb`
- `docs/exam-proof-pack.md`

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

This prevents the map from showing buses that cannot be properly explained in the presentation.

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

Important speaking point:

> The map shows where buses are. The statistical dashboard explains what the data means.

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

## 12. Evidence Files

### Notebooks

- `notebooks/03_data_mining_gtfs_rt.ipynb`
- `notebooks/04_model_evaluation_interpretation.ipynb`

### Reports And Snapshots

- `reports/snapshots/bus_model_snapshot_compact.json`
- `reports/snapshots/bus_model_snapshot_latest.json`
- `reports/bus_model_snapshot_summary.md`

### CSV Exports

- `reports/history_exports/bus_vehicle_positions_recent.csv`
- `reports/history_exports/bus_trip_updates_recent.csv`
- `reports/history_exports/bus_model_feature_windows_recent.csv`
- `reports/history_exports/bus_cluster_assignments_latest.csv`
- `reports/history_exports/bus_anomaly_scores_latest.csv`

### Documentation

- `docs/dashboard-readme.md`
- `docs/exam-proof-pack.md`
- `docs/viva-explanation-guide.md`
- `docs/statistical-dashboard-guide.md`
- `docs/code-walkthrough-for-presentation.md`
- `docs/historical-gtfs-rt-notes.md`

---

## 13. Presentation Structure

Use this 10-minute structure.

### Slide 1: Title

HSL Bus Reliability Analyzer: GTFS vs GTFS-RT Data Science Dashboard.

### Slide 2: Problem

Municipal planners need to understand bus reliability using real schedule and realtime data.

### Slide 3: Dataset

Explain static GTFS and GTFS-RT.

### Slide 4: Why Bus-Only

Explain that `701`, `702`, and `704` are HSL GTFS `route_type` mode/category codes for bus-family services, not individual bus line numbers.

### Slide 5: Preprocessing

Show feature engineering: delay, coverage, freshness, time features, route-stop-hour windows.

### Slide 6: Clustering

Explain KMeans and DBSCAN with metrics.

### Slide 7: Anomaly Detection

Explain Isolation Forest and LOF with metrics.

### Slide 8: Dashboard

Show live map and statistical analytics dashboard screenshots.

### Slide 9: Insights

Explain route health, hotspots, anomaly watchlist, and coverage.

### Slide 10: Limitations And Future Work

Mention limited GTFS-RT history, noisy trip matching, and possible future predictive modelling.

---

## 14. Key Viva Answers

### Why did you choose HSL?

HSL provides real public GTFS and GTFS-RT data, making it suitable for urban mobility analysis.

### Why bus-only?

The full feed is multimodal, but bus reliability is a clearer and more consistent modelling problem.

### What is the main target?

Bus reliability and schedule adherence, supported by delay, coverage, and anomaly features.

### Why clustering?

To discover similar route-stop-hour reliability patterns without predefined labels.

### Why anomaly detection?

To identify unusual bus operation windows when true disruption labels are unavailable.

### Why no predictive modelling?

The rubric requires at least two data mining techniques. Clustering and anomaly detection satisfy the requirement and fit the available data better than prediction with limited historical GTFS-RT.

### What is the biggest limitation?

Historical GTFS-RT data only accumulates when the poller is running, and HSL realtime matching can be noisy.

---

## 15. Current Readiness

The project is ready for PPT preparation because it has:

- A focused bus-only story.
- Part 1 and Part 2 explanation.
- Part 3 data mining notebook.
- Part 4 evaluation notebook.
- Dashboard with live map and statistical analytics.
- Saved screenshots and CSV evidence.
- Documentation for presentation and viva.

Before final submission:

1. Run both notebooks top-to-bottom in Jupyter.
2. Save notebook outputs.
3. Add dashboard screenshots to the PPT.
4. Keep the presentation wording bus-only and HSL-focused.
5. Be honest about GTFS-RT history limitations.

---

## 16. Notebook Execution Troubleshooting

Use this section if Part 3 or Part 4 notebook cells fail.

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

### Step 7: What To Submit If Live API Fails

If the live API has an issue near the deadline, submit the notebooks using the saved snapshot evidence:

- `reports/snapshots/bus_model_snapshot_compact_20260426T131928Z.json`
- `reports/snapshots/bus_model_snapshot_compact_20260427T062030Z.json`
- `reports/history_exports/bus_model_feature_windows_recent_20260427_092121.csv`
- `reports/history_exports/bus_cluster_assignments_latest_20260427_092121.csv`
- `reports/history_exports/bus_anomaly_scores_latest_20260427_092121.csv`

That is acceptable because these files are reproducible saved outputs from the project pipeline.
