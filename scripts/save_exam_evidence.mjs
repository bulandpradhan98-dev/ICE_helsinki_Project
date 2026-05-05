import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const apiBase = process.env.API_BASE_URL || "http://localhost:8000/api/v1";
const generatedAt = new Date().toISOString();
const runStamp = generatedAt.replace(/[-:]/g, "").replace(/\..+$/, "Z");

const reportsDir = path.join(root, "reports");
const snapshotsDir = path.join(reportsDir, "snapshots");
const screenshotsDir = path.join(reportsDir, "screenshots");
const historyDir = path.join(reportsDir, "history_exports");

for (const dir of [reportsDir, snapshotsDir, screenshotsDir, historyDir]) {
  fs.mkdirSync(dir, { recursive: true });
}

async function getJson(endpoint) {
  const response = await fetch(`${apiBase}${endpoint}`);
  if (!response.ok) {
    throw new Error(`${endpoint} failed with ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

function summarizeRun(run) {
  if (!run) return null;
  const selectedParams = typeof run.selected_params === "string"
    ? JSON.parse(run.selected_params)
    : run.selected_params;
  const metrics = typeof run.metrics === "string" ? JSON.parse(run.metrics) : run.metrics;
  return {
    id: run.id,
    family: run.model_family,
    algorithm: run.algorithm,
    started_at: run.started_at,
    completed_at: run.completed_at,
    rows_used: run.rows_used,
    selected_params: selectedParams,
    metrics,
  };
}

function renderMetric(value, digits = 3) {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(digits);
  return String(value);
}

function upsertNotebookSnapshot(notebookPath, markdown) {
  const notebook = JSON.parse(fs.readFileSync(notebookPath, "utf8"));
  const marker = "<!-- BUS_ONLY_MODEL_SNAPSHOT -->";
  const source = markdown.split("\n").map((line) => `${line}\n`);
  const existingIndex = notebook.cells.findIndex((cell) =>
    cell.cell_type === "markdown" && Array.isArray(cell.source) && cell.source.join("").includes(marker)
  );
  const cell = {
    cell_type: "markdown",
    metadata: {},
    source,
  };
  if (existingIndex >= 0) {
    notebook.cells[existingIndex] = cell;
  } else {
    notebook.cells.splice(1, 0, cell);
  }
  fs.writeFileSync(notebookPath, `${JSON.stringify(notebook, null, 1)}\n`, "utf8");
}

const [status, runs, clusters, anomalies, ingestion] = await Promise.all([
  getJson("/models/status"),
  getJson("/models/runs?limit=8"),
  getJson("/models/clusters?limit=1200"),
  getJson("/models/anomalies/live?hours=72&limit=500"),
  getJson("/ingestion/status"),
]);

const latestClusterRun = runs.runs.find((run) => run.model_family === "clustering");
const latestAnomalyRun = runs.runs.find((run) => run.model_family === "anomaly_detection");
const clusterSummary = summarizeRun(latestClusterRun);
const anomalySummary = summarizeRun(latestAnomalyRun);

const snapshot = {
  generated_at: generatedAt,
  api_base: apiBase,
  scope: "HSL bus-only reliability analysis; route_type IN (701, 702, 704)",
  ingestion,
  model_status: status,
  latest_cluster_run: clusterSummary,
  latest_anomaly_run: anomalySummary,
  cluster_geojson_feature_count: clusters.features?.length ?? 0,
  anomaly_geojson_feature_count: anomalies.features?.length ?? 0,
  cluster_geojson_sample: clusters.features?.slice(0, 5) ?? [],
  anomaly_geojson_sample: anomalies.features?.slice(0, 5) ?? [],
};

const compact = {
  generated_at: generatedAt,
  latest_realtime_vehicle_position_at: ingestion.latest_vehicle_position_at,
  latest_realtime_trip_update_at: ingestion.latest_trip_update_at,
  feature_windows: status.feature_windows,
  latest_feature_bucket: status.latest_feature_bucket,
  cluster_assignments: status.cluster_assignments,
  hotspot_count: status.hotspot_count,
  active_anomalies: status.active_anomalies,
  avg_prediction_coverage: status.avg_prediction_coverage,
  cluster_run_id: clusterSummary?.id,
  anomaly_run_id: anomalySummary?.id,
  kmeans_selected: clusterSummary?.selected_params?.kmeans,
  dbscan_selected: clusterSummary?.selected_params?.dbscan,
  isolation_forest_selected: anomalySummary?.selected_params?.isolation_forest,
  lof_selected: anomalySummary?.selected_params?.lof,
  kmeans_metrics: clusterSummary?.metrics?.selected_kmeans,
  dbscan_metrics: clusterSummary?.metrics?.selected_dbscan,
  isolation_forest_metrics: anomalySummary?.metrics?.selected_isolation_forest,
  lof_metrics: anomalySummary?.metrics?.selected_lof,
};

const snapshotPath = path.join(snapshotsDir, "bus_model_snapshot_latest.json");
const compactPath = path.join(snapshotsDir, "bus_model_snapshot_compact.json");
const stampedSnapshotPath = path.join(snapshotsDir, `bus_model_snapshot_${runStamp}.json`);
const stampedCompactPath = path.join(snapshotsDir, `bus_model_snapshot_compact_${runStamp}.json`);
fs.writeFileSync(snapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
fs.writeFileSync(compactPath, `${JSON.stringify(compact, null, 2)}\n`, "utf8");
fs.writeFileSync(stampedSnapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
fs.writeFileSync(stampedCompactPath, `${JSON.stringify(compact, null, 2)}\n`, "utf8");

const markdown = `<!-- BUS_ONLY_MODEL_SNAPSHOT -->
# Saved Bus-Only Model Snapshot

Generated from the running local API on \`${generatedAt}\`.

This notebook is scoped to **HSL bus reliability only** using GTFS route types \`701\`, \`702\`, and \`704\`. Raw GTFS/GTFS-RT ingestion remains broader for reproducibility, but modelling, interpretation, and dashboard evidence are bus-focused.

## Current API Evidence

| Evidence item | Value |
|---|---:|
| Latest vehicle-position poll | ${renderMetric(ingestion.latest_vehicle_position_at)} |
| Latest trip-update poll | ${renderMetric(ingestion.latest_trip_update_at)} |
| Model feature windows | ${renderMetric(status.feature_windows)} |
| Latest feature bucket | ${renderMetric(status.latest_feature_bucket)} |
| Cluster assignments | ${renderMetric(status.cluster_assignments)} |
| DBSCAN hotspots | ${renderMetric(status.hotspot_count)} |
| Active live anomalies | ${renderMetric(status.active_anomalies)} |
| Average prediction coverage | ${renderMetric(status.avg_prediction_coverage)} |

## Selected Models From Latest Run

| Technique | Selected parameters | Key evaluation |
|---|---|---|
| KMeans | \`${JSON.stringify(compact.kmeans_selected)}\` | silhouette=${renderMetric(compact.kmeans_metrics?.silhouette)}, Davies-Bouldin=${renderMetric(compact.kmeans_metrics?.davies_bouldin)}, Calinski-Harabasz=${renderMetric(compact.kmeans_metrics?.calinski_harabasz)} |
| DBSCAN | \`${JSON.stringify(compact.dbscan_selected)}\` | silhouette=${renderMetric(compact.dbscan_metrics?.silhouette)}, noise share=${renderMetric(compact.dbscan_metrics?.noise_share)}, clusters=${renderMetric(compact.dbscan_metrics?.cluster_count)} |
| Isolation Forest | \`${JSON.stringify(compact.isolation_forest_selected)}\` | Precision@K=${renderMetric(compact.isolation_forest_metrics?.precision_at_k)}, recall=${renderMetric(compact.isolation_forest_metrics?.recall)}, false-alarm share=${renderMetric(compact.isolation_forest_metrics?.false_alarm_share)} |
| Local Outlier Factor | \`${JSON.stringify(compact.lof_selected)}\` | Precision@K=${renderMetric(compact.lof_metrics?.precision_at_k)}, recall=${renderMetric(compact.lof_metrics?.recall)}, false-alarm share=${renderMetric(compact.lof_metrics?.false_alarm_share)} |

Saved machine-readable evidence:

- \`../reports/snapshots/bus_model_snapshot_latest.json\`
- \`../reports/snapshots/bus_model_snapshot_compact.json\`
- \`../reports/snapshots/bus_model_snapshot_${runStamp}.json\`
- \`../reports/snapshots/bus_model_snapshot_compact_${runStamp}.json\`
- \`../reports/history_exports/\` for CSV exports of recent bus GTFS-RT/model history.

Dashboard screenshot evidence:

![HSL bus dashboard live view](../reports/screenshots/hsl-bus-dashboard-live.png)
`;

fs.writeFileSync(path.join(reportsDir, "bus_model_snapshot_summary.md"), markdown, "utf8");

for (const notebookName of [
  "03_data_mining_gtfs_rt.ipynb",
  "04_model_evaluation_interpretation.ipynb",
]) {
  const notebookPath = path.join(root, "notebooks", notebookName);
  if (fs.existsSync(notebookPath)) {
    upsertNotebookSnapshot(notebookPath, markdown);
  }
}

console.log(JSON.stringify(compact, null, 2));
