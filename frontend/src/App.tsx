import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { MapPanel } from "./components/MapPanel";
import {
  fetchDefaultFeeds,
  fetchIngestionStatus,
  fetchModelStatus,
  fetchRouteComparison,
  fetchRouteModelInsights,
  fetchRoutes,
  fetchStops,
  fetchSummary,
  fetchSystemStatus,
  runAnomalyRecompute,
  runClusterRecompute,
  runModelFeatureRecompute,
  runRealtimePoll,
  runRecompute,
  runStaticImport,
} from "./lib/api";
import type {
  FeedConfig,
  IngestionStatus,
  LiveAnomalies,
  ModelClusters,
  ModelStatus,
  OperationResult,
  RouteComparison,
  RouteMetric,
  RouteModelInsights,
  RouteVehicles,
  StopMetric,
  SummaryResponse,
  SystemStatus,
} from "./types";

const BUS_ROUTE_TYPES = new Set([701, 702, 704]);

function formatRealtimeTime(value: string | null | undefined) {
  if (!value) {
    return "Waiting for live updates";
  }

  return new Date(value).toLocaleTimeString();
}

function getFreshnessLabel(value: string | null | undefined) {
  if (!value) {
    return "No GTFS-RT poll has been stored yet.";
  }

  const recordedAt = new Date(value);
  const ageMinutes = Math.round((Date.now() - recordedAt.getTime()) / 60000);
  if (ageMinutes <= 5) {
    return `Live feed updated ${ageMinutes} min ago.`;
  }
  if (ageMinutes <= 180) {
    return `Feed looks stale: last update ${ageMinutes} min ago.`;
  }
  return `Feed is old: last stored update was ${recordedAt.toLocaleString()}.`;
}

function getVehicleTypeLabel(routeType: number | null | undefined) {
  if (routeType !== null && routeType !== undefined && BUS_ROUTE_TYPES.has(routeType)) {
    return "Bus";
  }
  return "Bus";
}

function formatPercent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return `${value.toFixed(digits)}%`;
}

function getLiveRouteOtp(routeComparison: RouteComparison | null) {
  if (!routeComparison) {
    return null;
  }

  const counts = routeComparison.meta.status_counts;
  const scoredStops = counts.on_time + counts.early + counts.late;
  if (scoredStops <= 0) {
    return null;
  }

  return (counts.on_time / scoredStops) * 100;
}

function getMinutesSince(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  return Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
}

function countBy<T>(items: T[], getKey: (item: T) => string | null | undefined) {
  return items.reduce<Record<string, number>>((counts, item) => {
    const key = getKey(item) || "Unknown";
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}

function maxCount(entries: Array<[string, number]>) {
  return Math.max(1, ...entries.map(([, count]) => count));
}

function fallbackEntries(entries: Array<[string, number]>, label: string): Array<[string, number]> {
  return entries.length ? entries : [[label, 0]];
}

function formatCount(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : null;
}

function formatOperationMessage(label: string, result: OperationResult) {
  const details = result.details ?? {};

  if (label === "Anomaly recompute") {
    const rows = formatCount(details.rows_used);
    const isolationForest = formatCount(details.isolation_forest_anomalies);
    const lof = formatCount(details.lof_anomalies);
    return [
      "Anomaly scoring complete.",
      rows ? `${rows} bus model windows scored` : null,
      isolationForest ? `${isolationForest} Isolation Forest flags` : null,
      lof ? `${lof} LOF flags` : null,
    ]
      .filter(Boolean)
      .join(" ");
  }

  if (label === "Cluster recompute") {
    const rows = formatCount(details.rows_used);
    const assignments = formatCount(details.assignments);
    const hotspots = formatCount(details.hotspots);
    return [
      "Clustering complete.",
      rows ? `${rows} bus windows used` : null,
      assignments ? `${assignments} cluster assignments` : null,
      hotspots ? `${hotspots} model hotspots` : null,
    ]
      .filter(Boolean)
      .join(" ");
  }

  if (label === "Feature recompute") {
    const windows = formatCount(details.feature_windows);
    return windows
      ? `Feature rebuild complete. ${windows} bus model windows are ready for clustering and anomaly detection.`
      : result.message;
  }

  if (label === "Metric recompute") {
    const adherence = formatCount(details.adherence_events);
    const routes = formatCount(details.route_buckets);
    return [
      "Schedule-adherence metrics recomputed.",
      adherence ? `${adherence} stop events` : null,
      routes ? `${routes} route-hour buckets` : null,
    ]
      .filter(Boolean)
      .join(" ");
  }

  if (label === "Realtime poll") {
    const vehicles = formatCount(details.vehicle_positions);
    const trips = formatCount(details.trip_updates);
    return [
      "GTFS-RT poll stored.",
      vehicles ? `${vehicles} vehicle positions` : null,
      trips ? `${trips} trip updates` : null,
    ]
      .filter(Boolean)
      .join(" ");
  }

  if (label === "Static import") {
    const routes = formatCount(details.routes);
    const stops = formatCount(details.stops);
    const trips = formatCount(details.trips);
    return [
      "Static GTFS import complete.",
      routes ? `${routes} routes` : null,
      stops ? `${stops} stops` : null,
      trips ? `${trips} trips` : null,
    ]
      .filter(Boolean)
      .join(" ");
  }

  return result.message;
}

type RouteAnalyticsItem = {
  route_id: string;
  route_short_name: string;
  on_time_percentage: number | null;
  avg_delay_minutes: number;
  total_events: number;
  live_vehicle_count: number;
  hotspot_count: number;
  anomaly_count: number;
  avg_prediction_coverage: number | null;
  reliability_label: string;
  status: "good" | "watch" | "poor";
};

export default function App() {
  const [feeds, setFeeds] = useState<FeedConfig | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [routes, setRoutes] = useState<RouteMetric[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [ingestionStatus, setIngestionStatus] = useState<IngestionStatus | null>(null);
  const [stops, setStops] = useState<StopMetric[]>([]);
  const [routeComparison, setRouteComparison] = useState<RouteComparison | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [showStops, setShowStops] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshIntervalSeconds, setRefreshIntervalSeconds] = useState(30);
  const [selectedVehicle, setSelectedVehicle] = useState<RouteVehicles["features"][number] | null>(null);
  const [liveVehicles, setLiveVehicles] = useState<RouteVehicles["features"]>([]);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [routeModelInsights, setRouteModelInsights] = useState<RouteModelInsights | null>(null);
  const [modelLayers, setModelLayers] = useState<{
    clusters: ModelClusters | null;
    anomalies: LiveAnomalies | null;
  }>({ clusters: null, anomalies: null });
  const [showClusters, setShowClusters] = useState(true);
  const [showAnomalies, setShowAnomalies] = useState(true);
  const [isMapFullscreen, setIsMapFullscreen] = useState(false);
  const [activeDockPanel, setActiveDockPanel] = useState<"fleet" | "models">("fleet");

  const busRoutes = useMemo(
    () =>
      routes.filter(
        (route) => typeof route.route_type === "number" && BUS_ROUTE_TYPES.has(route.route_type),
      ),
    [routes],
  );
  const routeAnalyticsItems = useMemo<RouteAnalyticsItem[]>(() => {
    const byRoute = new Map<string, RouteAnalyticsItem>();

    for (const route of busRoutes) {
      byRoute.set(route.route_id, {
        route_id: route.route_id,
        route_short_name: route.route_short_name || route.route_id,
        on_time_percentage: route.on_time_percentage,
        avg_delay_minutes: route.avg_delay_minutes,
        total_events: route.total_events,
        live_vehicle_count: 0,
        hotspot_count: 0,
        anomaly_count: 0,
        avg_prediction_coverage: null,
        reliability_label: route.status,
        status: route.status,
      });
    }

    const clusterAccumulator = new Map<
      string,
      {
        route_short_name: string;
        delayTotal: number;
        coverageTotal: number;
        samples: number;
        hotspots: number;
        labels: Record<string, number>;
      }
    >();

    for (const feature of modelLayers.clusters?.features ?? []) {
      const routeId = feature.properties.route_id;
      const existing = clusterAccumulator.get(routeId) ?? {
        route_short_name: feature.properties.route_short_name || routeId,
        delayTotal: 0,
        coverageTotal: 0,
        samples: 0,
        hotspots: 0,
        labels: {},
      };
      existing.delayTotal += feature.properties.mean_delay_minutes ?? 0;
      existing.coverageTotal += feature.properties.prediction_coverage_ratio ?? 0;
      existing.samples += 1;
      existing.hotspots += feature.properties.dbscan_is_hotspot ? 1 : 0;
      existing.labels[feature.properties.reliability_label] =
        (existing.labels[feature.properties.reliability_label] ?? 0) + 1;
      clusterAccumulator.set(routeId, existing);
    }

    const anomalyCounts = new Map<string, number>();
    for (const feature of modelLayers.anomalies?.features ?? []) {
      anomalyCounts.set(feature.properties.route_id, (anomalyCounts.get(feature.properties.route_id) ?? 0) + 1);
    }

    const liveCounts = new Map<string, { route_short_name: string; count: number }>();
    for (const vehicle of liveVehicles) {
      const routeId = vehicle.properties.realtime_route_id;
      if (!routeId) continue;
      const existing = liveCounts.get(routeId) ?? {
        route_short_name: vehicle.properties.route_short_name || routeId,
        count: 0,
      };
      existing.count += 1;
      liveCounts.set(routeId, existing);
    }

    const allRouteIds = new Set([
      ...byRoute.keys(),
      ...clusterAccumulator.keys(),
      ...anomalyCounts.keys(),
      ...liveCounts.keys(),
    ]);

    for (const routeId of allRouteIds) {
      const cluster = clusterAccumulator.get(routeId);
      const live = liveCounts.get(routeId);
      const current = byRoute.get(routeId);
      const samples = cluster?.samples ?? 0;
      const avgDelay = current?.avg_delay_minutes ?? (samples ? (cluster?.delayTotal ?? 0) / samples : 0);
      const avgCoverage = samples ? (cluster?.coverageTotal ?? 0) / samples : current?.avg_prediction_coverage ?? null;
      const dominantLabel = cluster
        ? Object.entries(cluster.labels).sort((left, right) => right[1] - left[1])[0]?.[0] ?? "Modelled route"
        : current?.reliability_label ?? "Live route";
      const status: RouteAnalyticsItem["status"] =
        current?.status ??
        (anomalyCounts.get(routeId)
          ? "poor"
          : avgCoverage !== null && avgCoverage < 0.9
            ? "watch"
            : "good");

      byRoute.set(routeId, {
        route_id: routeId,
        route_short_name: current?.route_short_name || cluster?.route_short_name || live?.route_short_name || routeId,
        on_time_percentage: current?.on_time_percentage ?? null,
        avg_delay_minutes: avgDelay,
        total_events: current?.total_events ?? samples,
        live_vehicle_count: live?.count ?? current?.live_vehicle_count ?? 0,
        hotspot_count: cluster?.hotspots ?? current?.hotspot_count ?? 0,
        anomaly_count: anomalyCounts.get(routeId) ?? current?.anomaly_count ?? 0,
        avg_prediction_coverage: avgCoverage,
        reliability_label: dominantLabel,
        status,
      });
    }

    return [...byRoute.values()].sort((left, right) => {
      const liveDiff = right.live_vehicle_count - left.live_vehicle_count;
      if (liveDiff !== 0) return liveDiff;
      const anomalyDiff = right.anomaly_count - left.anomaly_count;
      if (anomalyDiff !== 0) return anomalyDiff;
      return right.total_events - left.total_events;
    });
  }, [busRoutes, liveVehicles, modelLayers.anomalies, modelLayers.clusters]);

  const selectedRoute = useMemo(
    () => busRoutes.find((route) => route.route_id === selectedRouteId) ?? null,
    [busRoutes, selectedRouteId],
  );
  const selectedRouteAnalytics = useMemo(
    () => routeAnalyticsItems.find((route) => route.route_id === selectedRouteId) ?? null,
    [routeAnalyticsItems, selectedRouteId],
  );
  const selectedRouteCoverage =
    selectedRouteAnalytics?.avg_prediction_coverage ??
    (routeModelInsights?.feature_windows || routeModelInsights?.stops_clustered
      ? routeModelInsights.avg_prediction_coverage
      : null);
  const selectedRouteOtp = selectedRouteAnalytics?.on_time_percentage ?? getLiveRouteOtp(routeComparison);
  const selectedRouteLabel =
    selectedRouteAnalytics?.route_short_name || selectedRoute?.route_short_name || selectedRouteId || "HSL Bus Network";
  const realtimeFreshness = getFreshnessLabel(ingestionStatus?.latest_vehicle_position_at);
  const isRealtimeStale = Boolean(
    ingestionStatus?.latest_vehicle_position_at &&
      Date.now() - new Date(ingestionStatus.latest_vehicle_position_at).getTime() > 15 * 60 * 1000,
  );
  const routeMetricHealthCounts = useMemo(
    () => ({
      good: busRoutes.filter((route) => route.status === "good").length,
      watch: busRoutes.filter((route) => route.status === "watch").length,
      poor: busRoutes.filter((route) => route.status === "poor").length,
    }),
    [busRoutes],
  );
  const routeMetricHealthTotal = Math.max(
    1,
    routeMetricHealthCounts.good + routeMetricHealthCounts.watch + routeMetricHealthCounts.poor,
  );
  const rankedDelayRoutes = useMemo(
    () =>
      [...routeAnalyticsItems]
        .sort((left, right) => {
          const delayDiff = right.avg_delay_minutes - left.avg_delay_minutes;
          if (delayDiff !== 0) return delayDiff;
          return right.live_vehicle_count - left.live_vehicle_count;
        })
        .slice(0, 6),
    [routeAnalyticsItems],
  );
  const fleetStatusEntries = useMemo(
    () =>
      Object.entries(
        countBy(liveVehicles, (vehicle) => vehicle.properties.current_status?.replace(/_/g, " ")),
      ).sort((left, right) => right[1] - left[1]),
    [liveVehicles],
  );
  const clusterReliabilityEntries = useMemo(
    () =>
      Object.entries(
        countBy(
          modelLayers.clusters?.features ?? [],
          (feature) => feature.properties.reliability_label,
        ),
      ).sort((left, right) => right[1] - left[1]),
    [modelLayers.clusters],
  );
  const anomalyReasonEntries = useMemo(
    () =>
      Object.entries(
        countBy(
          modelLayers.anomalies?.features ?? [],
          (feature) => feature.properties.anomaly_reason ?? "Model anomaly",
        ),
      )
        .sort((left, right) => right[1] - left[1])
        .slice(0, 5),
    [modelLayers.anomalies],
  );
  const freshnessMinutes = getMinutesSince(ingestionStatus?.latest_vehicle_position_at);
  const coveragePercent = modelStatus ? modelStatus.avg_prediction_coverage * 100 : null;
  const anomalyScoredWindows = modelStatus?.anomaly_scored_windows ?? null;
  const anomalyLoadPercent = modelStatus
    ? Math.min(100, (modelStatus.active_anomalies / Math.max(1, anomalyScoredWindows ?? modelStatus.active_anomalies)) * 100)
    : null;
  const insightLine = modelStatus?.active_anomalies
    ? `${modelStatus.active_anomalies.toLocaleString()} of ${(anomalyScoredWindows ?? 0).toLocaleString()} scored windows are active anomalies (${formatPercent(anomalyLoadPercent)}). This changes when the anomaly scoring job is refreshed.`
    : "No active anomaly windows are visible in the latest model status.";
  const liveRouteCount = routeAnalyticsItems.filter((route) => route.live_vehicle_count > 0).length;
  const selectedRouteSummary = selectedRouteAnalytics
    ? `${selectedRouteAnalytics.live_vehicle_count} live buses, ${selectedRouteAnalytics.hotspot_count} model hotspots, ${selectedRouteAnalytics.anomaly_count} anomaly windows`
    : "Select a route or bus to inspect route-level analytics.";

  async function refreshDashboard() {
    const [feedConfig, summaryData, routeData, systemStatus, pipelineStatus, modelPipelineStatus] =
      await Promise.allSettled([
        fetchDefaultFeeds(),
        fetchSummary(),
        fetchRoutes(),
        fetchSystemStatus(),
        fetchIngestionStatus(),
        fetchModelStatus(),
      ]);

    if (feedConfig.status === "fulfilled") {
      setFeeds(feedConfig.value);
    }
    if (summaryData.status === "fulfilled") {
      setSummary(summaryData.value);
    }
    if (routeData.status === "fulfilled") {
      setRoutes(routeData.value);
      const busOnly = routeData.value.filter(
        (route) => typeof route.route_type === "number" && BUS_ROUTE_TYPES.has(route.route_type),
      );
      if ((!selectedRouteId || !busOnly.some((route) => route.route_id === selectedRouteId)) && busOnly[0]) {
        setSelectedRouteId(busOnly[0].route_id);
      }
    }
    if (systemStatus.status === "fulfilled") {
      setStatus(systemStatus.value);
    }
    if (pipelineStatus.status === "fulfilled") {
      setIngestionStatus(pipelineStatus.value);
    }
    if (modelPipelineStatus.status === "fulfilled") {
      setModelStatus(modelPipelineStatus.value);
    }

    const failedLoads = [
      feedConfig,
      summaryData,
      routeData,
      systemStatus,
      pipelineStatus,
      modelPipelineStatus,
    ].filter((result) => result.status === "rejected");

    setLoadError(
      failedLoads.length > 0
        ? "Some dashboard data could not be loaded yet. The page will keep showing what is available."
        : null,
    );
  }

  async function refreshSelectedRoute(routeId: string | null) {
    if (!routeId) {
      setStops([]);
      setRouteComparison(null);
      setRouteModelInsights(null);
      return;
    }

    const [stopData, comparisonData, modelInsightData] = await Promise.allSettled([
      fetchStops(routeId),
      fetchRouteComparison(routeId),
      fetchRouteModelInsights(routeId),
    ]);

    setStops(stopData.status === "fulfilled" ? stopData.value : []);
    setRouteComparison(comparisonData.status === "fulfilled" ? comparisonData.value : null);
    setRouteModelInsights(modelInsightData.status === "fulfilled" ? modelInsightData.value : null);
  }

  async function handleAction(label: string, action: () => Promise<OperationResult>) {
    setBusyAction(label);
    setActionMessage(null);
    try {
      const result = await action();
      await refreshDashboard();
      await refreshSelectedRoute(selectedRouteId);
      setActionMessage(formatOperationMessage(label, result));
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : `${label} failed.`);
    } finally {
      setBusyAction(null);
    }
  }

  useEffect(() => {
    async function loadDashboard() {
      try {
        await refreshDashboard();
      } catch (error) {
        setLoadError(
          error instanceof Error
            ? error.message
            : "Dashboard bootstrap failed while contacting the API.",
        );
      }
    }

    void loadDashboard();
  }, []);

  useEffect(() => {
    void refreshSelectedRoute(selectedRouteId);
  }, [selectedRouteId]);

  useEffect(() => {
    if (routeAnalyticsItems.length && (!selectedRouteId || !routeAnalyticsItems.some((route) => route.route_id === selectedRouteId))) {
      setSelectedRouteId(routeAnalyticsItems[0].route_id);
    }
  }, [routeAnalyticsItems, selectedRouteId]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsMapFullscreen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <main className={`metro-shell ${isMapFullscreen ? "metro-shell-fullscreen" : ""}`}>
      {!isMapFullscreen ? (
        <section className="command-center">
          <div className="command-center-copy">
            <p className="panel-kicker">HSL bus reliability intelligence</p>
            <h1>Transit analytics built around routes, live buses, and model evidence.</h1>
            <p>
              This view combines GTFS schedules, GTFS-RT live vehicles, route-level model features,
              clustering, and anomaly detection into one presentation-ready command center.
            </p>
            <p>
              Low-confidence buses are filtered out: a bus must match a static GTFS bus route, static stop,
              recent GTFS-RT TripUpdate, and usable stop prediction context before it is displayed.
            </p>
          </div>
          <div className="executive-kpis">
            <article>
              <span>Live buses</span>
              <strong>{liveVehicles.length.toLocaleString()}</strong>
              <small>{liveRouteCount.toLocaleString()} active bus routes</small>
            </article>
            <article>
              <span>Observed routes</span>
              <strong>{routeAnalyticsItems.length.toLocaleString()}</strong>
              <small>
                {modelStatus
                  ? `${routeMetricHealthTotal.toLocaleString()} OTP-scored | ${modelStatus.feature_windows.toLocaleString()} feature windows`
                  : "waiting for model status"}
              </small>
            </article>
            <article>
              <span>Prediction coverage</span>
              <strong>{formatPercent(coveragePercent)}</strong>
              <small>{freshnessMinutes === null ? "feed waiting" : `feed age ${freshnessMinutes} min`}</small>
            </article>
            <article>
              <span>Anomaly watchlist</span>
              <strong>{modelStatus ? modelStatus.active_anomalies.toLocaleString() : "--"}</strong>
              <small>{modelStatus ? `${modelStatus.hotspot_count.toLocaleString()} DBSCAN hotspots` : "waiting for model status"}</small>
            </article>
          </div>
          <div className="route-focus-card">
            <p className="panel-kicker">Selected route intelligence</p>
            <h2>{selectedRouteLabel}</h2>
            <p>{selectedRouteSummary}</p>
            <div className="route-focus-grid">
              <span>OTP {selectedRouteOtp === null ? "waiting for scored stops" : formatPercent(selectedRouteOtp)}</span>
              <span>Delay {selectedRouteAnalytics ? `${selectedRouteAnalytics.avg_delay_minutes.toFixed(1)} min` : "waiting for model window"}</span>
              <span>Coverage {selectedRouteCoverage === null || selectedRouteCoverage === undefined ? "waiting for coverage" : formatPercent(selectedRouteCoverage * 100)}</span>
            </div>
          </div>
        </section>
      ) : null}

      <section className={`map-stage ${isMapFullscreen ? "map-stage-fullscreen" : ""}`}>
        <MapPanel
          selectedRouteId={selectedRouteId}
          showStops={showStops}
          autoRefresh={autoRefresh}
          refreshIntervalSeconds={refreshIntervalSeconds}
          showClusters={showClusters}
          showAnomalies={showAnomalies}
          isFullscreen={isMapFullscreen}
          onSelectVehicle={setSelectedVehicle}
          onVehiclesUpdate={setLiveVehicles}
          onModelLayersUpdate={setModelLayers}
          highlightVehicleEntityId={selectedVehicle?.properties.entity_id ?? null}
        />

        {isMapFullscreen ? (
          <div className="floating-card fullscreen-toolbar">
            <div>
              <p className="panel-kicker">Full screen map</p>
              <strong>{selectedRouteLabel}</strong>
              <p className="toolbar-copy">{realtimeFreshness}</p>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setIsMapFullscreen(false)}
            >
              Exit full screen
            </button>
          </div>
        ) : null}

        {!isMapFullscreen ? (
          <div className="floating-card top-commandbar">
            <div className="command-brand">
              <p className="panel-kicker">HSL bus operations</p>
              <h2>Bus Reliability Console</h2>
              <span className="command-subtitle">{selectedRouteLabel}</span>
            </div>
            <div className="command-chip-group">
              <article className="command-chip">
                <span>Live feed</span>
                <strong>
                  {ingestionStatus?.latest_vehicle_position_at
                    ? formatRealtimeTime(ingestionStatus.latest_vehicle_position_at)
                    : "Waiting"}
                </strong>
              </article>
              <article className="command-chip">
                <span>Live routes</span>
                <strong>{liveRouteCount.toLocaleString()}</strong>
              </article>
              <article className="command-chip">
                <span>Model hotspots</span>
                <strong>{modelStatus ? modelStatus.hotspot_count.toLocaleString() : "--"}</strong>
              </article>
              <article className="command-chip">
                <span>Metric</span>
                <strong>{status?.active_metric ?? "Schedule adherence"}</strong>
              </article>
            </div>
            <div className="command-actions">
              <button
                type="button"
                className="secondary-button command-button"
                onClick={() => void refreshDashboard()}
                disabled={busyAction !== null}
              >
                Refresh
              </button>
              <button
                type="button"
                className="secondary-button command-button"
                onClick={() => setIsMapFullscreen(true)}
                disabled={busyAction !== null}
              >
                Full screen
              </button>
            </div>
          </div>
        ) : null}

        {(loadError || actionMessage) && !isMapFullscreen ? (
          <div className="floating-card map-message-panel">
            {loadError ? <p className="inline-message warning-copy">{loadError}</p> : null}
            {actionMessage ? <p className="inline-message">{actionMessage}</p> : null}
          </div>
        ) : null}

        <div className="floating-card controls-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Layers & jobs</p>
              <h2>Control center</h2>
            </div>
            <span className="micro-badge">{feeds?.city ?? "Helsinki"}</span>
          </div>

          <label className="control-row">
            <span>Show stop markers</span>
            <input
              type="checkbox"
              checked={showStops}
              onChange={(event) => setShowStops(event.target.checked)}
            />
          </label>

          <label className="control-row">
            <span>Show clusters</span>
            <input
              type="checkbox"
              checked={showClusters}
              onChange={(event) => setShowClusters(event.target.checked)}
            />
          </label>

          <label className="control-row">
            <span>Show anomalies</span>
            <input
              type="checkbox"
              checked={showAnomalies}
              onChange={(event) => setShowAnomalies(event.target.checked)}
            />
          </label>

          <label className="control-row">
            <span>Auto refresh</span>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
            />
          </label>

          <label className="select-row">
            <span>Refresh interval</span>
            <select
              value={refreshIntervalSeconds}
              onChange={(event) => setRefreshIntervalSeconds(Number(event.target.value))}
              disabled={!autoRefresh}
            >
              <option value={10}>10 sec</option>
              <option value={30}>30 sec</option>
              <option value={60}>60 sec</option>
            </select>
          </label>

          <div className="button-stack">
            <button
              type="button"
              onClick={() => void handleAction("Static import", runStaticImport)}
              disabled={busyAction !== null}
            >
              {busyAction === "Static import" ? "Importing..." : "Import static GTFS"}
            </button>
            <button
              type="button"
              onClick={() => void handleAction("Realtime poll", runRealtimePoll)}
              disabled={busyAction !== null}
            >
              {busyAction === "Realtime poll" ? "Polling..." : "Poll GTFS-RT"}
            </button>
            <button
              type="button"
              onClick={() => void handleAction("Metric recompute", runRecompute)}
              disabled={busyAction !== null}
            >
              {busyAction === "Metric recompute" ? "Computing..." : "Recompute metrics"}
            </button>
            <button
              type="button"
              onClick={() => void handleAction("Feature recompute", runModelFeatureRecompute)}
              disabled={busyAction !== null}
            >
              {busyAction === "Feature recompute" ? "Building..." : "Build model features"}
            </button>
            <button
              type="button"
              onClick={() => void handleAction("Cluster recompute", runClusterRecompute)}
              disabled={busyAction !== null}
            >
              {busyAction === "Cluster recompute" ? "Clustering..." : "Run clustering"}
            </button>
            <button
              type="button"
              onClick={() => void handleAction("Anomaly recompute", runAnomalyRecompute)}
              disabled={busyAction !== null}
            >
              {busyAction === "Anomaly recompute" ? "Scoring..." : "Score anomalies"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void refreshDashboard()}
              disabled={busyAction !== null}
            >
              Refresh data
            </button>
          </div>

          {ingestionStatus?.service_end_date ? (
            <p className="inline-message">
              Static GTFS service window ends on {new Date(ingestionStatus.service_end_date).toLocaleDateString()}.
            </p>
          ) : null}

          <div className="legend-grid">
            <span className="legend-chip status-on-time">On time</span>
            <span className="legend-chip status-late">Late</span>
            <span className="legend-chip status-early">Early</span>
            <span className="legend-chip status-scheduled-only">Static only</span>
            <span className="legend-chip status-hotspot">Model hotspot</span>
            <span className="legend-chip status-anomaly">Anomaly</span>
          </div>
        </div>

        <div className="floating-card routes-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Route explorer</p>
              <h2>Routes</h2>
            </div>
            <span className="micro-badge">{routeAnalyticsItems.length}</span>
          </div>

          {!routeAnalyticsItems.length ? (
            <p className="panel-copy">
              Bus route analytics will appear here after live vehicles or model clusters are available.
            </p>
          ) : (
            <div className="route-list">
              {routeAnalyticsItems.slice(0, 42).map((route) => (
                <button
                  key={route.route_id}
                  type="button"
                  className={`route-item ${selectedRouteId === route.route_id ? "route-item-active" : ""}`}
                  onClick={() => setSelectedRouteId(route.route_id)}
                >
                  <div>
                    <strong>{route.route_short_name || route.route_id}</strong>
                    <span>
                      {route.live_vehicle_count.toLocaleString()} live buses | {route.total_events.toLocaleString()} model windows
                    </span>
                  </div>
                  <div className="route-item-meta">
                    <span className={`status-pill status-${route.status}`}>
                      {route.on_time_percentage === null ? route.reliability_label : `${route.on_time_percentage.toFixed(1)}%`}
                    </span>
                    <small>{route.hotspot_count} model hotspots</small>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="floating-card dock-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Analyst dock</p>
              <h2>{activeDockPanel === "fleet" ? "Live fleet" : "Part 3 models"}</h2>
            </div>
            <div className="dock-tabs">
              <button
                type="button"
                className={`dock-tab ${activeDockPanel === "fleet" ? "dock-tab-active" : ""}`}
                onClick={() => setActiveDockPanel("fleet")}
              >
                Fleet
              </button>
              <button
                type="button"
                className={`dock-tab ${activeDockPanel === "models" ? "dock-tab-active" : ""}`}
                onClick={() => setActiveDockPanel("models")}
              >
                Models
              </button>
            </div>
          </div>
          {activeDockPanel === "fleet" ? (
            liveVehicles.length ? (
              <div className="detail-scroll dock-scroll">
                {liveVehicles.slice(0, 10).map((vehicle) => (
                  <button
                    key={vehicle.properties.entity_id}
                    type="button"
                    className={`route-item ${
                      selectedVehicle?.properties.entity_id === vehicle.properties.entity_id
                        ? "route-item-active"
                        : ""
                    }`}
                    onClick={() => {
                      setSelectedVehicle(vehicle);
                      if (vehicle.properties.realtime_route_id) {
                        setSelectedRouteId(vehicle.properties.realtime_route_id);
                      }
                    }}
                  >
                    <div>
                      <strong>
                        {vehicle.properties.route_short_name ?? vehicle.properties.realtime_route_id ?? "Line"} -{" "}
                        {vehicle.properties.vehicle_label}
                      </strong>
                      <span>{vehicle.properties.stop_name ?? "Stop unknown"}</span>
                    </div>
                    <div className="route-item-meta">
                      <span className="status-pill status-scheduled-only">
                        {vehicle.properties.current_status ?? "Status unknown"}
                      </span>
                      <small>{formatRealtimeTime(vehicle.properties.recorded_at)}</small>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <p className="panel-copy">
                Live bus vehicles will appear here after they pass the quality filter: static route match,
                static stop match, recent TripUpdate, and upcoming stop prediction context.
              </p>
            )
          ) : (
            <>
              <div className="detail-metrics">
                <article>
                  <span>Feature windows</span>
                  <strong>{modelStatus ? modelStatus.feature_windows.toLocaleString() : "--"}</strong>
                </article>
                <article>
                  <span>Model hotspots</span>
                  <strong>{modelStatus ? modelStatus.hotspot_count.toLocaleString() : "--"}</strong>
                </article>
                <article>
                  <span>Cluster stops</span>
                  <strong>{modelLayers.clusters?.meta.count.toLocaleString() ?? "--"}</strong>
                </article>
                <article>
                  <span>Anomaly layer</span>
                  <strong>{modelLayers.anomalies?.meta.latest_bucket ? "Ready" : "Waiting"}</strong>
                </article>
              </div>
              <p className="inline-message compact-message">
                Teal points show recurring reliability patterns. Orange DBSCAN hotspots mark delay or low
                real-time coverage windows; pulsing red markers show live anomaly scores.
              </p>
            </>
          )}
        </div>

        <div className="floating-card detail-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Inspector rail</p>
              <h2>{selectedRouteAnalytics ? selectedRouteAnalytics.route_short_name : selectedRoute ? selectedRoute.route_short_name : "No route selected"}</h2>
            </div>
            {selectedRouteAnalytics || selectedRoute ? (
              <span className="micro-badge">{selectedRouteAnalytics?.route_id ?? selectedRoute?.route_id}</span>
            ) : null}
          </div>

          {selectedRouteAnalytics || selectedRoute ? (
            <>
              <div className="detail-metrics">
                <article>
                  <span>On-time</span>
                  <strong>{selectedRouteOtp === null ? "Waiting" : `${selectedRouteOtp.toFixed(1)}%`}</strong>
                </article>
                <article>
                  <span>Avg delay</span>
                  <strong>{selectedRouteAnalytics ? `${selectedRouteAnalytics.avg_delay_minutes.toFixed(1)} min` : "--"}</strong>
                </article>
                <article>
                  <span>Live buses</span>
                  <strong>{selectedRouteAnalytics ? selectedRouteAnalytics.live_vehicle_count.toLocaleString() : "--"}</strong>
                </article>
                <article>
                  <span>Coverage</span>
                  <strong>
                    {selectedRouteCoverage === null || selectedRouteCoverage === undefined
                      ? "--"
                      : `${(selectedRouteCoverage * 100).toFixed(1)}%`}
                  </strong>
                </article>
              </div>

              {routeComparison ? (
                <div className="compare-breakdown">
                  <span className="legend-chip status-on-time">
                    {routeComparison.meta.status_counts.on_time} on time
                  </span>
                  <span className="legend-chip status-late">
                    {routeComparison.meta.status_counts.late} late
                  </span>
                  <span className="legend-chip status-early">
                    {routeComparison.meta.status_counts.early} early
                  </span>
                  <span className="legend-chip status-scheduled-only">
                    {routeComparison.meta.status_counts.scheduled_only} static only
                  </span>
                </div>
              ) : null}

              {routeModelInsights ? (
                <div className="compare-breakdown">
                  <span className="legend-chip status-hotspot">
                    {routeModelInsights.hotspots} model hotspots
                  </span>
                  <span className="legend-chip status-anomaly">
                    {routeModelInsights.active_anomalies} active anomalies
                  </span>
                  <span className="legend-chip status-scheduled-only">
                    Coverage {((routeModelInsights.avg_prediction_coverage ?? 0) * 100).toFixed(1)}%
                  </span>
                </div>
              ) : selectedRouteAnalytics ? (
                <div className="compare-breakdown">
                  <span className="legend-chip status-hotspot">
                    {selectedRouteAnalytics.hotspot_count} model hotspots
                  </span>
                  <span className="legend-chip status-anomaly">
                    {selectedRouteAnalytics.anomaly_count} anomalies
                  </span>
                  <span className="legend-chip status-scheduled-only">
                    {selectedRouteAnalytics.reliability_label}
                  </span>
                </div>
              ) : null}

              <div className="detail-scroll">
                {routeComparison?.features.length ? (
                  routeComparison.features.slice(0, 10).map((feature) => (
                    <article key={feature.properties.stop_id} className="stop-row">
                      <div>
                        <strong>
                          #{feature.properties.stop_sequence} {feature.properties.stop_name}
                        </strong>
                        <span>{feature.properties.stop_id}</span>
                      </div>
                      <div className="stop-row-meta">
                        <span
                          className={`status-pill status-${feature.properties.live_status.replace("_", "-")}`}
                        >
                          {feature.properties.live_status.replace("_", " ")}
                        </span>
                        <small>
                          {feature.properties.delay_minutes === null
                            ? "No live delay"
                            : `${feature.properties.delay_minutes.toFixed(1)} min`}
                        </small>
                      </div>
                    </article>
                  ))
                ) : stops.length ? (
                  stops.slice(0, 10).map((stop) => (
                    <article key={stop.stop_id} className="stop-row">
                      <div>
                        <strong>{stop.stop_name}</strong>
                        <span>{stop.stop_id}</span>
                      </div>
                      <div className="stop-row-meta">
                        <span className="status-pill status-good">{stop.on_time_percentage.toFixed(1)}%</span>
                        <small>{stop.avg_delay_minutes.toFixed(1)} min</small>
                      </div>
                    </article>
                  ))
                ) : (
                  <p className="panel-copy">Stop-level details will appear here after selecting a populated route.</p>
                )}
              </div>
            </>
          ) : (
            <p className="panel-copy">Pick a route from the explorer to load live and aggregate details.</p>
          )}
        </div>

        {selectedVehicle ? (
        <div className="floating-card vehicle-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Live vehicle</p>
              <h2>{selectedVehicle ? selectedVehicle.properties.vehicle_label : "Click a bus dot"}</h2>
            </div>
            {selectedVehicle?.properties.route_short_name ? (
              <span className="micro-badge">{selectedVehicle.properties.route_short_name}</span>
            ) : null}
          </div>
          <>
              <div className="detail-metrics">
                <article>
                  <span>Vehicle type</span>
                  <strong>{getVehicleTypeLabel(selectedVehicle.properties.route_type)}</strong>
                </article>
                <article>
                  <span>Status</span>
                  <strong>{selectedVehicle.properties.current_status ?? "Unknown"}</strong>
                </article>
                <article>
                  <span>Next stop</span>
                  <strong>{selectedVehicle.properties.next_stop_name ?? "Unknown"}</strong>
                </article>
                <article>
                  <span>GTFS-RT context</span>
                  <strong>{selectedVehicle.properties.stop_name ?? "Unknown"}</strong>
                </article>
                <article>
                  <span>Speed</span>
                  <strong>
                    {selectedVehicle.properties.speed !== null
                      ? `${selectedVehicle.properties.speed.toFixed(1)} m/s`
                      : "Not reported"}
                  </strong>
                </article>
                <article>
                  <span>Updated</span>
                  <strong>{formatRealtimeTime(selectedVehicle.properties.recorded_at)}</strong>
                </article>
              </div>
              {selectedRouteAnalytics || selectedRoute ? (
                <div className="compare-breakdown">
                  <span className="legend-chip status-on-time">
                    Next delay{" "}
                    {selectedVehicle.properties.next_stop_delay_minutes === null
                      ? "not predicted"
                      : `${selectedVehicle.properties.next_stop_delay_minutes.toFixed(1)} min`}
                  </span>
                  <span className="legend-chip status-on-time">
                    Route OTP {selectedRouteOtp === null ? "waiting for scored stops" : `${selectedRouteOtp.toFixed(1)}%`}
                  </span>
                  <span className="legend-chip status-scheduled-only">
                    Avg delay {selectedRouteAnalytics ? selectedRouteAnalytics.avg_delay_minutes.toFixed(1) : selectedRoute?.avg_delay_minutes.toFixed(1)} min
                  </span>
                </div>
              ) : null}
              <div className="detail-scroll">
                {selectedVehicle.properties.upcoming_stops.length ? (
                  selectedVehicle.properties.upcoming_stops.map((stop, index) => (
                    <article
                      key={`${selectedVehicle.properties.entity_id}-${stop.stop_id ?? index}`}
                      className="stop-row"
                    >
                      <div>
                        <strong>{stop.stop_name ?? stop.stop_id ?? "Upcoming stop"}</strong>
                        <span>
                      {stop.stop_sequence !== null ? `Sequence ${stop.stop_sequence}` : "Sequence unavailable"}
                        </span>
                      </div>
                      <div className="stop-row-meta">
                        <span className="status-pill status-scheduled-only">
                          {stop.delay_minutes === null ? "No delay" : `${stop.delay_minutes.toFixed(1)} min`}
                        </span>
                      </div>
                    </article>
                  ))
                ) : (
                  <p className="panel-copy">
                    This bus passed the static route/stop filter, but there are no extra upcoming-stop rows to show
                    beyond the current vehicle context.
                  </p>
                )}
              </div>
          </>
        </div>
        ) : null}
      </section>

      <section className="analytics-lab">
        <div className="analytics-hero">
          <div>
            <p className="panel-kicker">Statistical intelligence</p>
            <h2>Bus Network Analytics</h2>
            <p>
              A presentation-ready analytics cockpit that separates live operations from model interpretation:
              reliability distribution, realtime coverage, route ranking, clusters, and anomaly signals.
            </p>
          </div>
          <div className="analytics-hero-metrics">
            <article>
              <span>Live bus dots</span>
              <strong>{liveVehicles.length.toLocaleString()}</strong>
            </article>
            <article>
              <span>Freshness</span>
              <strong>{freshnessMinutes === null ? "--" : `${freshnessMinutes} min`}</strong>
            </article>
            <article>
              <span>Coverage</span>
              <strong>{formatPercent(coveragePercent)}</strong>
            </article>
          </div>
        </div>

        <div className="analytics-grid">
          <article className="analytics-card analytics-card-wide">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Reliability mix</p>
                <h3>Route health distribution</h3>
              </div>
              <span className="micro-badge">{routeMetricHealthTotal} scored routes</span>
            </div>
            <div className="stacked-bar" aria-label="Route health distribution">
              <span
                className="stack-segment stack-good"
                style={{ width: `${(routeMetricHealthCounts.good / routeMetricHealthTotal) * 100}%` }}
              />
              <span
                className="stack-segment stack-watch"
                style={{ width: `${(routeMetricHealthCounts.watch / routeMetricHealthTotal) * 100}%` }}
              />
              <span
                className="stack-segment stack-poor"
                style={{ width: `${(routeMetricHealthCounts.poor / routeMetricHealthTotal) * 100}%` }}
              />
            </div>
            <div className="analytics-legend">
              <span><i className="legend-dot stack-good" />Good {routeMetricHealthCounts.good}</span>
              <span><i className="legend-dot stack-watch" />Watch {routeMetricHealthCounts.watch}</span>
              <span><i className="legend-dot stack-poor" />Poor {routeMetricHealthCounts.poor}</span>
            </div>
            <p className="analytics-note">
              Based only on bus routes with computed 24-hour OTP: good {"\u2265"} 90%, watch 80-89.9%, poor {"<"} 80%.
              Live-only routes may still appear in the route explorer before they receive a scored OTP window.
            </p>
          </article>

          <article className="analytics-card">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Realtime quality</p>
                <h3>Prediction coverage</h3>
              </div>
              <span className="micro-badge">{formatPercent(coveragePercent)}</span>
            </div>
            <div
              className="radial-meter"
              style={{ "--meter-value": `${coveragePercent ?? 0}%` } as CSSProperties}
            >
              <strong>{formatPercent(coveragePercent)}</strong>
              <span>GTFS-RT coverage</span>
            </div>
            <p className="analytics-note">
              Coverage shows how much realtime prediction signal is available for the model windows.
            </p>
          </article>

          <article className="analytics-card">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Anomaly pressure</p>
                <h3>Live model watchlist</h3>
              </div>
              <span className="micro-badge">{modelStatus?.active_anomalies ?? "--"}</span>
            </div>
            <div
              className="radial-meter radial-meter-alert"
              style={{ "--meter-value": `${anomalyLoadPercent ?? 0}%` } as CSSProperties}
            >
              <strong>{modelStatus ? modelStatus.active_anomalies.toLocaleString() : "--"}</strong>
              <span>active anomaly windows</span>
            </div>
            <div className="compare-breakdown">
              <span className="legend-chip status-anomaly">
                {formatPercent(anomalyLoadPercent)} pressure
              </span>
              <span className="legend-chip status-scheduled-only">
                {(anomalyScoredWindows ?? 0).toLocaleString()} scored
              </span>
              <span className="legend-chip status-hotspot">
                {modelStatus?.latest_anomaly_bucket
                  ? `Bucket ${formatRealtimeTime(modelStatus.latest_anomaly_bucket)}`
                  : "Bucket waiting"}
              </span>
            </div>
            <p className="analytics-note">{insightLine}</p>
          </article>

          <article className="analytics-card analytics-card-tall">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Route ranking</p>
                <h3>Highest average delay</h3>
              </div>
              <span className="micro-badge">Top 6</span>
            </div>
            <div className="rank-list">
              {rankedDelayRoutes.map((route, index) => {
                const maxDelay = Math.max(1, ...rankedDelayRoutes.map((item) => item.avg_delay_minutes));
                return (
                  <div className="rank-row" key={route.route_id}>
                    <span className="rank-index">{index + 1}</span>
                    <div>
                      <strong>{route.route_short_name || route.route_id}</strong>
                      <span>{route.total_events.toLocaleString()} observations</span>
                      <div className="mini-bar">
                        <i style={{ width: `${Math.min(100, (route.avg_delay_minutes / maxDelay) * 100)}%` }} />
                      </div>
                    </div>
                    <b>{route.avg_delay_minutes.toFixed(1)} min</b>
                  </div>
                );
              })}
            </div>
          </article>

          <article className="analytics-card analytics-card-tall">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Fleet pulse</p>
                <h3>Vehicle status split</h3>
              </div>
              <span className="micro-badge">{liveVehicles.length}</span>
            </div>
            <div className="bar-list">
              {fallbackEntries(fleetStatusEntries, "Waiting for vehicles").map(([label, count]) => (
                <div className="bar-row" key={label}>
                  <div>
                    <strong>{label.toLowerCase()}</strong>
                    <span>{count.toLocaleString()} vehicles</span>
                  </div>
                  <div className="horizontal-bar">
                    <i style={{ width: `${(count / maxCount(fleetStatusEntries)) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article className="analytics-card analytics-card-tall">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Cluster profile</p>
                <h3>Reliability labels</h3>
              </div>
              <span className="micro-badge">{modelLayers.clusters?.meta.count ?? "--"}</span>
            </div>
            <div className="bar-list">
              {fallbackEntries(clusterReliabilityEntries, "No cluster layer loaded").map(
                ([label, count]) => (
                  <div className="bar-row" key={label}>
                    <div>
                      <strong>{label}</strong>
                      <span>{count.toLocaleString()} cluster points</span>
                    </div>
                    <div className="horizontal-bar horizontal-bar-teal">
                      <i style={{ width: `${(count / maxCount(clusterReliabilityEntries)) * 100}%` }} />
                    </div>
                  </div>
                ),
              )}
            </div>
          </article>

          <article className="analytics-card analytics-card-tall">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Explainability</p>
                <h3>Anomaly reasons</h3>
              </div>
              <span className="micro-badge">{modelLayers.anomalies?.meta.count ?? "--"}</span>
            </div>
            <div className="bar-list">
              {fallbackEntries(anomalyReasonEntries, "No live anomalies loaded").map(
                ([label, count]) => (
                  <div className="bar-row" key={label}>
                    <div>
                      <strong>{label}</strong>
                      <span>{count.toLocaleString()} windows</span>
                    </div>
                    <div className="horizontal-bar horizontal-bar-red">
                      <i style={{ width: `${(count / maxCount(anomalyReasonEntries)) * 100}%` }} />
                    </div>
                  </div>
                ),
              )}
            </div>
          </article>
        </div>
      </section>

      <section className="system-ribbon">
        <div>
          <p className="panel-kicker">Pipeline</p>
          <strong>
            Batch {ingestionStatus?.latest_batch_id ?? "--"} | {ingestionStatus?.routes_count ?? 0} routes |{" "}
            {ingestionStatus?.stops_count ?? 0} stops
          </strong>
        </div>
        <div>
          <p className="panel-kicker">Live feed</p>
          <strong>{ingestionStatus?.latest_vehicle_position_at ? formatRealtimeTime(ingestionStatus.latest_vehicle_position_at) : "Not polled yet"}</strong>
        </div>
        <div>
          <p className="panel-kicker">Metric</p>
          <strong>{status?.active_metric ?? "Schedule adherence"}</strong>
        </div>
      </section>
    </main>
  );
}
