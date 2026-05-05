# HSL Bus Reliability Project: Exam Proof Pack

This document is the speaking and evidence guide for the final presentation. It maps the project to the grading rubric and lists the proof files that show the work was completed.

## One-Sentence Project Story

This project analyzes **HSL bus reliability in Helsinki** by combining static GTFS schedules with GTFS-RT realtime vehicle/trip-update feeds, then uses clustering and anomaly detection to identify reliability patterns, hotspots, and unusual bus-operation windows.

## Scope Decision

The official analysis scope is **bus-only HSL transit reliability**.

- Static GTFS contains many HSL modes, but modelling focuses on bus route types `701`, `702`, and `704`.
- This makes the project easier to explain, fairer for modelling, and directly connected to schedule adherence and urban bus-service planning.
- Raw ingestion remains broader so the pipeline is reproducible, but notebooks, model outputs, dashboard interpretation, and presentation are bus-focused.

## Rubric Coverage

| Grading section | Points | What the course asks for | What this project provides | Evidence |
|---|---:|---|---|---|
| Data Understanding | 15 | Dataset choice, problem definition, summary, missing values, anomalies, challenges | HSL GTFS + GTFS-RT chosen as public transport dataset; problem is bus reliability/schedule adherence; dataset types include time series, spatial, categorical, numeric | `Section_1_Data Understanding.ipynb`, `notebooks/03_data_mining_gtfs_rt.ipynb`, `docs/viva-explanation-guide.md` |
| Data Preprocessing | 20 | Missing values, feature engineering, timestamp features, categorical encoding, normalization/aggregation | Bus-only filtering; GTFS/GTFS-RT route matching; hour/day/weekend features; route/stop aggregation; delay, coverage, feed freshness, vehicle count features; scaled model inputs | `notebooks/03_data_mining_gtfs_rt.ipynb`, `reports/history_exports/bus_model_feature_windows_recent.csv` |
| Data Mining Techniques | 30 | At least two techniques with justification, tuning, comparison where possible | KMeans clustering, DBSCAN hotspot discovery, Isolation Forest anomaly detection, LOF anomaly detection | `notebooks/03_data_mining_gtfs_rt.ipynb`, `reports/snapshots/bus_model_snapshot_latest.json` |
| Model Evaluation | 20 | Metrics, visualization, interpretation, trade-offs, urban-mobility implications | Silhouette, Davies-Bouldin, Calinski-Harabasz for clustering; Precision@K, recall, false-alarm share, F1 proxy for anomaly detection; dashboard/map screenshot and interpretation | `notebooks/04_model_evaluation_interpretation.ipynb`, `reports/screenshots/hsl-bus-dashboard-live.png` |
| Presentation | 15 | Clarity, structure, insights, communication, source code | 10-minute story prepared below; dashboard demo available; limitations stated honestly; source code + notebooks + evidence exports available | `docs/exam-proof-pack.md`, `docs/viva-explanation-guide.md`, `README.md` |

## Current Live Evidence Snapshot

Generated from the local API on April 26, 2026.

| Evidence item | Value |
|---|---:|
| Latest GTFS-RT vehicle-position poll | `2026-04-26T13:18:58.568803Z` |
| Latest GTFS-RT trip-update poll | `2026-04-26T13:18:58.702449Z` |
| Feature windows | `125,650` |
| Latest feature bucket | `2026-04-26T13:00:00+00:00` |
| Cluster assignments | `6,000` |
| DBSCAN hotspots | `400` |
| Active live anomalies | `248` |
| Average prediction coverage | `0.974` |
| Latest clustering run | `2026-04-26T13:13:44Z` |
| Latest anomaly run | `2026-04-26T13:15:04Z` |

## Model Choices And Why They Fit The Course

### KMeans Clustering

KMeans groups bus route-stop-hour windows with similar reliability behavior. It is useful for answering: "Which parts of the bus network behave similarly?"

Selected parameters:

- `k = 2`
- `n_init = 20`

Evaluation:

- Silhouette: `0.737`
- Davies-Bouldin: `0.412`
- Calinski-Harabasz: `12,546.421`

How to explain:

"KMeans gives an interpretable grouping of bus reliability windows. A high silhouette score means the groups are reasonably separated, while the low Davies-Bouldin value indicates compact clusters."

### DBSCAN Hotspot Discovery

DBSCAN finds dense spatial/operational reliability groups and labels sparse unusual points as noise. It is useful for hotspot-style interpretation.

Selected parameters:

- `eps = 0.4`
- `min_samples = 20`

Evaluation:

- Silhouette: `0.769`
- Noise share: `0.037`
- Cluster count: `2`
- Davies-Bouldin: `0.350`
- Calinski-Harabasz: `18,398.673`

How to explain:

"DBSCAN is better than KMeans for hotspot discovery because it does not force every point into a cluster. It can show dense reliability areas and separate unusual/noisy locations."

### Isolation Forest

Isolation Forest detects unusual bus reliability windows by isolating rows that behave differently from the normal population.

Selected parameters:

- `n_estimators = 200`
- `max_samples = 256`
- `contamination = 0.05`

Evaluation:

- Precision@K: `0.915`
- Recall: `0.464`
- F1 proxy: `0.616`
- False-alarm share: `0.0042`

How to explain:

"Isolation Forest was selected because it produced the best balance between catching meaningful anomalies and keeping false alarms low."

### Local Outlier Factor

LOF compares each bus window to its local neighborhood. It is useful as a second anomaly method because it can catch local deviations.

Selected parameters:

- `n_neighbors = 35`
- `contamination = 0.01`

Evaluation:

- Precision@K: `1.000`
- Recall: `0.094`
- F1 proxy: `0.172`
- False-alarm share: `0.000`

How to explain:

"LOF is more conservative in this run. It has excellent precision but low recall, so it is good for high-confidence anomaly flags, while Isolation Forest catches more cases."

## Feature Engineering Proof

The model feature windows include:

- Mean delay
- Median delay
- 95th percentile absolute delay
- Delay standard deviation
- On-time ratio
- Late ratio
- Early ratio
- Prediction coverage ratio
- Vehicle observation count
- Feed age/freshness
- Route type
- Hour of day
- Day of week
- Weekend flag
- Stop latitude/longitude

Why these features matter:

- Delay and on-time ratios measure reliability.
- Coverage and feed age measure realtime data quality.
- Hour/day/weekend capture temporal mobility patterns.
- Stop geometry allows map layers and hotspot interpretation.

## Dashboard Proof

Dashboard URL while Docker is running:

- `http://localhost:5173/`

Screenshot evidence:

- `reports/screenshots/hsl-bus-dashboard-live.png`
- `reports/screenshots/hsl-bus-statistical-analytics-dashboard.png`

What the dashboard shows:

- Live HSL bus vehicle markers from GTFS-RT.
- Bus network route geometry from static GTFS.
- Cluster layer for reliability groups.
- Hotspot layer from DBSCAN.
- Anomaly layer for unusual realtime/model windows.
- Vehicle/route detail panels for interpretation.
- Statistical analytics cockpit with route health, prediction coverage, delay ranking, fleet status, reliability labels, and anomaly reasons.

## Reproducibility Proof Files

Snapshot files:

- `reports/snapshots/bus_model_snapshot_compact.json`
- `reports/snapshots/bus_model_snapshot_latest.json`
- `reports/bus_model_snapshot_summary.md`

CSV evidence exports:

- `reports/history_exports/bus_vehicle_positions_recent.csv`
- `reports/history_exports/bus_trip_updates_recent.csv`
- `reports/history_exports/bus_model_feature_windows_recent.csv`
- `reports/history_exports/bus_cluster_assignments_latest.csv`
- `reports/history_exports/bus_anomaly_scores_latest.csv`

Notebook evidence:

- `notebooks/03_data_mining_gtfs_rt.ipynb`
- `notebooks/04_model_evaluation_interpretation.ipynb`

Documentation evidence:

- `docs/viva-explanation-guide.md`
- `docs/historical-gtfs-rt-notes.md`
- `docs/exam-proof-pack.md`

## Honest Limitations

These are not weaknesses if explained clearly.

- Historical GTFS-RT is only collected while Docker is running.
- HSL GTFS-RT does not always provide a clean static GTFS `trip_id`, so matching GTFS to GTFS-RT is noisy.
- Missing TripUpdates do not necessarily mean buses were on time; they may mean the feed had limited prediction coverage.
- The project does not implement predictive modelling because the exam requires at least two techniques, and clustering plus anomaly detection are enough for Part 3.
- The dashboard supports interpretation, but the graded core is the notebook analysis and evaluation.

## 10-Minute Presentation Structure

### 1. Problem And Objective

"My project studies HSL bus reliability in Helsinki. The goal is to combine scheduled GTFS data with realtime GTFS-RT data and identify where bus service is reliable, where hotspots appear, and where unusual operation patterns occur."

### 2. Dataset

"I used HSL's public transport data. Static GTFS gives the planned network: routes, stops, trips, stop times, and shapes. GTFS-RT gives live vehicle positions and trip updates. Because the full HSL feed is multimodal, I narrowed the modelling scope to bus-only route types."

### 3. Preprocessing

"I transformed raw realtime pings and trip updates into route-stop-hour feature windows. I engineered time features, reliability features, coverage features, and spatial features. This turns raw transit data into a clean table suitable for data mining."

### 4. Data Mining Technique 1: Clustering

"I used KMeans for general reliability grouping and DBSCAN for hotspot discovery. KMeans gives interpretable groups, while DBSCAN is better for spatially dense hotspots and noise."

### 5. Data Mining Technique 2: Anomaly Detection

"I used Isolation Forest and LOF. Isolation Forest catches more anomalies and gives the best balance overall; LOF is more conservative and useful for high-confidence anomalies."

### 6. Evaluation

"For clustering, I used Silhouette, Davies-Bouldin, and Calinski-Harabasz. For anomaly detection, I used Precision@K, recall, false-alarm share, and F1 proxy using pseudo-labels such as feed freshness and coverage dropouts."

### 7. Dashboard

"The dashboard connects the analysis back to urban mobility. It shows the bus network, live bus vehicles, clusters, hotspots, and anomalies on a map."

### 8. Insights

"The project helps planners see which parts of the bus network have similar reliability patterns, where realtime prediction coverage is weaker, and where unusual bus operation windows appear."

### 9. Limitations

"The main limitation is historical GTFS-RT availability. Since public HSL historical GTFS-RT archives are not clearly available, the project stores history locally while Docker is running and exports reproducible CSV snapshots."

### 10. Conclusion

"The project satisfies the course objective by using real urban mobility data, preprocessing it into meaningful features, applying clustering and anomaly detection, evaluating models quantitatively, and presenting results through notebooks and an interactive dashboard."

## Likely Viva Questions And Safe Answers

| Question | Strong answer |
|---|---|
| Why bus-only? | The full HSL feed is multimodal, but bus reliability is easier to compare consistently because buses share similar operating conditions and schedule-adherence interpretation. |
| Why not predictive modelling? | The rubric requires at least two techniques. I selected clustering and anomaly detection because they directly answer reliability-pattern and disruption-detection questions with the available history. |
| What is schedule adherence? | Whether service is close to scheduled time; in this project the target concept is on-time performance, with delay and coverage features used for model analysis. |
| Why use KMeans? | It gives simple, interpretable groups of similar route-stop-hour reliability windows. |
| Why use DBSCAN? | It discovers dense hotspots and can label noisy points instead of forcing every point into a cluster. |
| Why use Isolation Forest? | It is suitable for unsupervised anomaly detection and performed best on the pseudo-label evaluation. |
| What are pseudo-labels? | They are rule-based labels created from extreme operational conditions like stale feeds, coverage dropouts, and unusual realtime behavior because true anomaly labels are not available. |
| What is the biggest limitation? | Limited historical GTFS-RT data and noisy matching between realtime data and scheduled trips. |
| How can this help a city? | It helps identify unreliable route segments, weak realtime coverage, operational hotspots, and areas needing schedule or service-quality review. |

## Final Readiness Assessment

The project is well aligned with the marking scheme. To maximize marks before submission:

- Run both notebooks top-to-bottom once in Jupyter and save outputs.
- Put the dashboard screenshot and two evaluation charts into the PPT.
- Keep the bus-only story consistent from first slide to final slide.
- Be transparent about limited GTFS-RT history.
- Do not overclaim prediction; this is clustering plus anomaly detection, which satisfies Part 3.
