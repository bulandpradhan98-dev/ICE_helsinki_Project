import type {
  FeedConfig,
  IngestionStatus,
  LiveAnomalies,
  ModelClusters,
  ModelStatus,
  NetworkGeometry,
  OperationResult,
  RouteComparison,
  RouteGeometry,
  RouteMetric,
  RouteModelInsights,
  RouteVehicles,
  StopMetric,
  SummaryResponse,
  SystemStatus,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed for ${path}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed for ${path}`);
  }
  return response.json() as Promise<T>;
}

export function fetchDefaultFeeds(): Promise<FeedConfig> {
  return readJson<FeedConfig>("/feeds/default");
}

export function fetchSummary(): Promise<SummaryResponse> {
  return readJson<SummaryResponse>("/summary");
}

export function fetchRoutes(): Promise<RouteMetric[]> {
  return readJson<RouteMetric[]>("/routes");
}

export function fetchStops(routeId: string): Promise<StopMetric[]> {
  return readJson<StopMetric[]>(`/routes/${routeId}/stops`);
}

export function fetchRouteGeometry(routeId: string): Promise<RouteGeometry> {
  return readJson<RouteGeometry>(`/routes/${routeId}/geometry`);
}

export function fetchNetworkGeometry(mode = "bus"): Promise<NetworkGeometry> {
  return readJson<NetworkGeometry>(`/network/geometry?mode=${mode}`);
}

export function fetchNetworkVehicles(mode = "bus"): Promise<RouteVehicles> {
  return readJson<RouteVehicles>(`/network/vehicles?mode=${mode}`);
}

export function fetchRouteComparison(routeId: string): Promise<RouteComparison> {
  return readJson<RouteComparison>(`/routes/${routeId}/comparison`);
}

export function fetchRouteVehicles(routeId: string): Promise<RouteVehicles> {
  return readJson<RouteVehicles>(`/routes/${routeId}/vehicles`);
}

export function fetchModelStatus(): Promise<ModelStatus> {
  return readJson<ModelStatus>("/models/status");
}

export function fetchModelClusters(): Promise<ModelClusters> {
  return readJson<ModelClusters>("/models/clusters");
}

export function fetchLiveAnomalies(): Promise<LiveAnomalies> {
  return readJson<LiveAnomalies>("/models/anomalies/live");
}

export function fetchRouteModelInsights(routeId: string): Promise<RouteModelInsights> {
  return readJson<RouteModelInsights>(`/routes/${routeId}/model-insights`);
}

export function fetchSystemStatus(): Promise<SystemStatus> {
  return readJson<SystemStatus>("/system/status");
}

export function fetchIngestionStatus(): Promise<IngestionStatus> {
  return readJson<IngestionStatus>("/ingestion/status");
}

export function runStaticImport(): Promise<OperationResult> {
  return postJson<OperationResult>("/ingestion/static/import");
}

export function runRealtimePoll(): Promise<OperationResult> {
  return postJson<OperationResult>("/ingestion/realtime/poll");
}

export function runRecompute(): Promise<OperationResult> {
  return postJson<OperationResult>("/analytics/recompute");
}

export function runModelFeatureRecompute(): Promise<OperationResult> {
  return postJson<OperationResult>("/models/features/recompute");
}

export function runClusterRecompute(): Promise<OperationResult> {
  return postJson<OperationResult>("/models/clusters/recompute");
}

export function runAnomalyRecompute(): Promise<OperationResult> {
  return postJson<OperationResult>("/models/anomalies/recompute");
}
