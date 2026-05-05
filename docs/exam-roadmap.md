# Exam Alignment Roadmap

## Part 1: Data understanding

- dataset: HSL static GTFS and GTFS-RT feeds
- problem statement: analyze schedule adherence and reliability for HSL bus routes in Helsinki
- modelling scope: bus route types `701`, `702`, and `704`
- summary targets:
  - record counts per GTFS table
  - attribute categories: spatial, temporal, categorical, numerical
  - missingness and GTFS-RT matching constraints

## Part 2: Data preprocessing

- timestamp features: weekday, hour, peak flag, service date
- route and stop encoding
- GPS cleaning and invalid coordinate filtering
- trip-event aggregation to route and stop windows

## Part 3: Data mining techniques

- clustering: use KMeans to group bus route-stop windows by reliability and realtime coverage patterns
- hotspot discovery: use DBSCAN to identify spatially dense reliability or coverage hotspots
- anomaly detection: use Isolation Forest and LOF to flag unusual bus route-stop-hour windows
- predictive modelling: parked as future work until more labelled delay history is collected

## Part 4: Model evaluation and interpretation

- clustering metrics: Silhouette Score, Davies-Bouldin Index, Calinski-Harabasz Score
- anomaly metrics: precision, recall, F1, Precision@K, false alarm share against pseudo-labels
- visuals: route maps, cluster maps, anomaly maps, route/stop summary tables
- interpretation: explain how bus reliability patterns can support service planning and operational monitoring

## Presentation

- tell one story: HSL bus reliability, not full multimodal transit
- demo order: live bus map, route explorer, selected bus details, cluster layer, anomaly layer, route insight panel
- state limitations clearly: limited GTFS-RT history, noisy trip matching, pseudo-labels instead of official incident labels
