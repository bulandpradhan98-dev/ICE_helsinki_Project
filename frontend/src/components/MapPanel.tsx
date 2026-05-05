import { useEffect, useRef, useState } from "react";
import maplibregl, { GeoJSONSource, Map, Popup } from "maplibre-gl";

import {
  fetchLiveAnomalies,
  fetchModelClusters,
  fetchNetworkGeometry,
  fetchNetworkVehicles,
  fetchRouteComparison,
  fetchRouteGeometry,
} from "../lib/api";
import type { LiveAnomalies, ModelClusters, RouteComparison, RouteGeometry, RouteVehicles } from "../types";

type MapPanelProps = {
  selectedRouteId: string | null;
  showStops: boolean;
  autoRefresh: boolean;
  refreshIntervalSeconds: number;
  showClusters: boolean;
  showAnomalies: boolean;
  isFullscreen: boolean;
  onSelectVehicle: (vehicle: RouteVehicles["features"][number] | null) => void;
  onVehiclesUpdate: (vehicles: RouteVehicles["features"]) => void;
  onModelLayersUpdate: (payload: { clusters: ModelClusters | null; anomalies: LiveAnomalies | null }) => void;
  highlightVehicleEntityId: string | null;
};

function formatDelay(delayMinutes: number | null) {
  if (delayMinutes === null) {
    return "No live delay";
  }

  const rounded = delayMinutes.toFixed(1);
  return `${rounded} min`;
}

function formatClusterPopup(feature: ModelClusters["features"][number]) {
  const props = feature.properties;
  return `
    <div class="vehicle-popup">
      <h3>${props.route_short_name ?? props.route_id} - ${props.stop_name ?? props.stop_id}</h3>
      <p class="popup-subtitle">Reliability cluster ${props.kmeans_cluster ?? "unassigned"} | ${
        props.dbscan_is_hotspot ? "DBSCAN hotspot" : "pattern cluster"
      }</p>
      <p><strong>Label:</strong> ${props.reliability_label.replace(/_/g, " ")}</p>
      <p><strong>Mean delay:</strong> ${props.mean_delay_minutes.toFixed(1)} min</p>
      <p><strong>P95 absolute delay:</strong> ${props.p95_abs_delay_minutes.toFixed(1)} min</p>
      <p><strong>Prediction coverage:</strong> ${(props.prediction_coverage_ratio * 100).toFixed(1)}%</p>
    </div>
  `;
}

function formatAnomalyPopup(feature: LiveAnomalies["features"][number]) {
  const props = feature.properties;
  return `
    <div class="vehicle-popup">
      <h3>${props.route_short_name ?? props.route_id} - ${props.stop_name ?? props.stop_id}</h3>
      <p class="popup-subtitle">Live anomaly | ${new Date(props.bucket).toLocaleString()}</p>
      <p><strong>Reason:</strong> ${props.anomaly_reason ?? "Model flagged unusual pattern"}</p>
      <p><strong>Mean delay:</strong> ${props.mean_delay_minutes.toFixed(1)} min</p>
      <p><strong>Isolation Forest:</strong> ${
        props.isolation_forest_score === null ? "not scored" : props.isolation_forest_score.toFixed(3)
      }</p>
      <p><strong>LOF:</strong> ${props.lof_score === null ? "not scored" : props.lof_score.toFixed(3)}</p>
      <p><strong>Coverage:</strong> ${(props.prediction_coverage_ratio * 100).toFixed(1)}%</p>
    </div>
  `;
}

function formatVehiclePopup(
  routeGeometry: RouteGeometry | null,
  feature: RouteVehicles["features"][number],
) {
  const props = feature.properties;
  const upcomingRows = props.upcoming_stops
    .slice(0, 4)
    .map(
      (stop) =>
        `<tr><td>${stop.stop_name ?? stop.stop_id ?? "Stop"}</td><td>${formatDelay(stop.delay_minutes)}</td></tr>`,
    )
    .join("");

  const lineLabel =
    props.route_short_name ??
    routeGeometry?.properties.route_short_name ??
    props.realtime_route_id ??
    "Bus";

  return `
    <div class="vehicle-popup">
      <h3>${lineLabel} - ${props.vehicle_label}</h3>
      <p class="popup-subtitle">Bus | Trip ${props.trip_id ?? "not provided"} | ${props.current_status ?? "status unavailable"}</p>
      <p><strong>Next stop:</strong> ${props.next_stop_name ?? "Unknown"}</p>
      <p><strong>GTFS-RT stop context:</strong> ${props.stop_name ?? "Unknown"}</p>
      <p><strong>Next stop delay:</strong> ${formatDelay(props.next_stop_delay_minutes)}</p>
      <p><strong>Route:</strong> ${props.realtime_route_id ?? "Unknown"}</p>
      <p><strong>Speed:</strong> ${props.speed !== null ? `${props.speed.toFixed(1)} m/s` : "not reported"}</p>
      <p><strong>Updated:</strong> ${new Date(props.recorded_at).toLocaleTimeString()}</p>
      ${
        upcomingRows
          ? `<table class="popup-table"><thead><tr><th>Upcoming stop</th><th>Delay</th></tr></thead><tbody>${upcomingRows}</tbody></table>`
          : `<p>No upcoming stop predictions available for this vehicle yet.</p>`
      }
    </div>
  `;
}

export function MapPanel({
  selectedRouteId,
  showStops,
  autoRefresh,
  refreshIntervalSeconds,
  showClusters,
  showAnomalies,
  isFullscreen,
  onSelectVehicle,
  onVehiclesUpdate,
  onModelLayersUpdate,
  highlightVehicleEntityId,
}: MapPanelProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const popupRef = useRef<Popup | null>(null);
  const selectedRouteGeometryRef = useRef<RouteGeometry | null>(null);
  const latestVehiclesRef = useRef<RouteVehicles | null>(null);
  const latestClustersRef = useRef<ModelClusters | null>(null);
  const latestAnomaliesRef = useRef<LiveAnomalies | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [selectedRouteGeometry, setSelectedRouteGeometry] = useState<RouteGeometry | null>(null);
  const [latestVehicles, setLatestVehicles] = useState<RouteVehicles | null>(null);
  const emptyComparison: RouteComparison = {
    type: "FeatureCollection",
    meta: {
      route_id: "",
      route_short_name: "",
      stop_count: 0,
      latest_recorded_at: null,
      status_counts: {
        scheduled_only: 0,
        early: 0,
        on_time: 0,
        late: 0,
      },
    },
    features: [],
  };

  useEffect(() => {
    selectedRouteGeometryRef.current = selectedRouteGeometry;
  }, [selectedRouteGeometry]);

  useEffect(() => {
    latestVehiclesRef.current = latestVehicles;
  }, [latestVehicles]);

  useEffect(() => {
    if (!mapRef.current) {
      return;
    }

    const resizeHandle = window.setTimeout(() => {
      mapRef.current?.resize();
    }, 180);

    return () => window.clearTimeout(resizeHandle);
  }, [isFullscreen]);

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) {
      return;
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "OpenStreetMap contributors",
          },
        },
        layers: [
          {
            id: "osm",
            type: "raster",
            source: "osm",
            paint: {
              "raster-opacity": 0.52,
              "raster-saturation": -1,
              "raster-brightness-max": 0.84,
              "raster-contrast": -0.08,
            },
          },
        ],
      },
      center: [24.9384, 60.1699],
      zoom: 9,
    });

    popupRef.current = new maplibregl.Popup({
      closeButton: true,
      closeOnClick: false,
      maxWidth: "340px",
      offset: 18,
    });

    map.on("load", () => {
      map.addSource("network-routes", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });
      map.addSource("selected-route", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });
      map.addSource("live-vehicles", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });
      map.addSource("route-comparison-stops", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });
      map.addSource("model-clusters", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });
      map.addSource("live-anomalies", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });

      map.addLayer({
        id: "network-routes-line",
        type: "line",
        source: "network-routes",
        paint: {
          "line-color": [
            "case",
            ["has", "route_color"],
            ["concat", "#", ["get", "route_color"]],
            "#6b7280",
          ],
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            8,
            1.2,
            12,
            2.5,
          ],
          "line-opacity": 0.18,
        },
      });
      map.addLayer({
        id: "selected-route-glow",
        type: "line",
        source: "selected-route",
        paint: {
          "line-color": [
            "case",
            ["has", "route_color"],
            ["concat", "#", ["get", "route_color"]],
            "#111827",
          ],
          "line-width": 10,
          "line-blur": 5,
          "line-opacity": 0.18,
        },
      });
      map.addLayer({
        id: "selected-route-line",
        type: "line",
        source: "selected-route",
        paint: {
          "line-color": [
            "case",
            ["has", "route_color"],
            ["concat", "#", ["get", "route_color"]],
            "#111827",
          ],
          "line-width": 4.2,
          "line-opacity": 0.96,
        },
      });
      map.addLayer({
        id: "route-comparison-stops-circle",
        type: "circle",
        source: "route-comparison-stops",
        paint: {
          "circle-radius": [
            "match",
            ["get", "live_status"],
            "late",
            7,
            "early",
            6,
            "on_time",
            6,
            5,
          ],
          "circle-color": [
            "match",
            ["get", "live_status"],
            "late",
            "#ef4444",
            "early",
            "#2563eb",
            "on_time",
            "#22c55e",
            "#6b7280",
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.94,
        },
      });
      map.addLayer({
        id: "live-vehicles-circle",
        type: "circle",
        source: "live-vehicles",
        paint: {
          "circle-radius": 8,
          "circle-color": "#f59e0b",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 1,
        },
      });
      map.addLayer({
        id: "model-clusters-circle",
        type: "circle",
        source: "model-clusters",
        layout: {
          visibility: "none",
        },
        paint: {
          "circle-radius": [
            "case",
            ["get", "dbscan_is_hotspot"],
            10,
            6,
          ],
          "circle-color": [
            "match",
            ["get", "reliability_label"],
            "delay_hotspot",
            "#dc2626",
            "low_realtime_coverage",
            "#7c3aed",
            "watch",
            "#f97316",
            "#14b8a6",
          ],
          "circle-stroke-width": [
            "case",
            ["get", "dbscan_is_hotspot"],
            3,
            1,
          ],
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.78,
        },
      });
      map.addLayer({
        id: "live-anomalies-pulse",
        type: "circle",
        source: "live-anomalies",
        layout: {
          visibility: "none",
        },
        paint: {
          "circle-radius": 15,
          "circle-color": "#ef4444",
          "circle-opacity": 0.18,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fecaca",
        },
      });
      map.addLayer({
        id: "live-anomalies-core",
        type: "circle",
        source: "live-anomalies",
        layout: {
          visibility: "none",
        },
        paint: {
          "circle-radius": 7,
          "circle-color": "#b91c1c",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.96,
        },
      });

      map.on("mouseenter", "live-vehicles-circle", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "live-vehicles-circle", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("click", "live-vehicles-circle", (event) => {
        const clickedFeature = event.features?.[0];
        if (!clickedFeature || !popupRef.current || !latestVehiclesRef.current) {
          return;
        }

        const vehicle = latestVehiclesRef.current.features.find(
          (item) => item.properties.entity_id === clickedFeature.properties?.entity_id,
        );
        if (!vehicle) {
          return;
        }

        onSelectVehicle(vehicle);

        popupRef.current
          .setLngLat(event.lngLat)
          .setHTML(formatVehiclePopup(selectedRouteGeometryRef.current, vehicle))
          .addTo(map);
      });

      map.on("mouseenter", "route-comparison-stops-circle", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "route-comparison-stops-circle", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("mouseenter", "model-clusters-circle", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "model-clusters-circle", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("click", "model-clusters-circle", (event) => {
        const clickedFeature = event.features?.[0];
        if (!clickedFeature || !popupRef.current || !latestClustersRef.current) {
          return;
        }
        const cluster = latestClustersRef.current.features.find(
          (item) =>
            item.properties.route_id === clickedFeature.properties?.route_id &&
            item.properties.stop_id === clickedFeature.properties?.stop_id,
        );
        if (!cluster) {
          return;
        }
        popupRef.current
          .setLngLat(event.lngLat)
          .setHTML(formatClusterPopup(cluster))
          .addTo(map);
      });
      map.on("mouseenter", "live-anomalies-core", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "live-anomalies-core", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("click", "live-anomalies-core", (event) => {
        const clickedFeature = event.features?.[0];
        if (!clickedFeature || !popupRef.current || !latestAnomaliesRef.current) {
          return;
        }
        const anomaly = latestAnomaliesRef.current.features.find(
          (item) =>
            item.properties.bucket === clickedFeature.properties?.bucket &&
            item.properties.route_id === clickedFeature.properties?.route_id &&
            item.properties.stop_id === clickedFeature.properties?.stop_id,
        );
        if (!anomaly) {
          return;
        }
        popupRef.current
          .setLngLat(event.lngLat)
          .setHTML(formatAnomalyPopup(anomaly))
          .addTo(map);
      });

      setMapReady(true);
    });

    mapRef.current = map;

    return () => {
      popupRef.current?.remove();
      map.remove();
      mapRef.current = null;
      popupRef.current = null;
    };
  }, []);

  useEffect(() => {
    async function loadNetwork() {
      if (!mapRef.current || !mapReady) {
        return;
      }

      try {
        const network = await fetchNetworkGeometry("bus");
        const source = mapRef.current.getSource("network-routes") as GeoJSONSource | undefined;
        source?.setData(network);
      } catch {
        const source = mapRef.current.getSource("network-routes") as GeoJSONSource | undefined;
        source?.setData({
          type: "FeatureCollection",
          features: [],
        });
      }
    }

    void loadNetwork();
  }, [mapReady]);

  useEffect(() => {
    if (!mapRef.current || !mapReady) {
      return;
    }

    mapRef.current.setLayoutProperty(
      "route-comparison-stops-circle",
      "visibility",
      showStops ? "visible" : "none",
    );
  }, [mapReady, showStops]);

  useEffect(() => {
    if (!mapRef.current || !mapReady) {
      return;
    }

    mapRef.current.setLayoutProperty(
      "model-clusters-circle",
      "visibility",
      showClusters ? "visible" : "none",
    );
    mapRef.current.setLayoutProperty(
      "live-anomalies-pulse",
      "visibility",
      showAnomalies ? "visible" : "none",
    );
    mapRef.current.setLayoutProperty(
      "live-anomalies-core",
      "visibility",
      showAnomalies ? "visible" : "none",
    );
  }, [mapReady, showAnomalies, showClusters]);

  useEffect(() => {
    async function updateRoute() {
      if (!selectedRouteId || !mapRef.current || !mapReady) {
        return;
      }

      const routeSource = mapRef.current.getSource("selected-route") as GeoJSONSource | undefined;

      try {
        const feature = await fetchRouteGeometry(selectedRouteId);
        routeSource?.setData(feature);
        setSelectedRouteGeometry(feature);

        const coordinates = feature.geometry.coordinates;
        if (coordinates.length > 0) {
          const bounds = coordinates.reduce(
            (accumulator, coordinate) => accumulator.extend(coordinate as [number, number]),
            new maplibregl.LngLatBounds(
              coordinates[0] as [number, number],
              coordinates[0] as [number, number],
            ),
          );
          mapRef.current.fitBounds(bounds, { padding: 90, duration: 700 });
        }
      } catch {
        routeSource?.setData({
          type: "FeatureCollection",
          features: [],
        });
        setSelectedRouteGeometry(null);
      }
    }

    void updateRoute();
  }, [mapReady, selectedRouteId]);

  useEffect(() => {
    async function updateLiveLayers() {
      if (!mapRef.current || !mapReady) {
        return;
      }

      const vehiclePromise = fetchNetworkVehicles("bus");
      const comparisonPromise = selectedRouteId ? fetchRouteComparison(selectedRouteId) : null;
      const clusterPromise = fetchModelClusters();
      const anomalyPromise = fetchLiveAnomalies();

      const [vehicles, routeComparison, clusters, anomalies] = await Promise.allSettled([
        vehiclePromise,
        comparisonPromise ?? Promise.resolve(emptyComparison),
        clusterPromise,
        anomalyPromise,
      ]);

      const vehicleSource = mapRef.current.getSource("live-vehicles") as GeoJSONSource | undefined;
      const comparisonSource = mapRef.current.getSource(
        "route-comparison-stops",
      ) as GeoJSONSource | undefined;
      const clusterSource = mapRef.current.getSource("model-clusters") as GeoJSONSource | undefined;
      const anomalySource = mapRef.current.getSource("live-anomalies") as GeoJSONSource | undefined;

      if (vehicles.status === "fulfilled") {
        setLatestVehicles(vehicles.value);
        onVehiclesUpdate(vehicles.value.features);
        vehicleSource?.setData(vehicles.value);
      } else {
        setLatestVehicles(null);
        onVehiclesUpdate([]);
        vehicleSource?.setData({
          type: "FeatureCollection",
          features: [],
        });
      }

      if (selectedRouteId && routeComparison.status === "fulfilled") {
        comparisonSource?.setData(routeComparison.value);
      } else {
        comparisonSource?.setData({
          type: "FeatureCollection",
          features: [],
        });
      }

      if (clusters.status === "fulfilled") {
        latestClustersRef.current = clusters.value;
        clusterSource?.setData(clusters.value);
      } else {
        latestClustersRef.current = null;
        clusterSource?.setData({
          type: "FeatureCollection",
          features: [],
        });
      }

      if (anomalies.status === "fulfilled") {
        latestAnomaliesRef.current = anomalies.value;
        anomalySource?.setData(anomalies.value);
      } else {
        latestAnomaliesRef.current = null;
        anomalySource?.setData({
          type: "FeatureCollection",
          features: [],
        });
      }

      onModelLayersUpdate({
        clusters: clusters.status === "fulfilled" ? clusters.value : null,
        anomalies: anomalies.status === "fulfilled" ? anomalies.value : null,
      });
    }

    void updateLiveLayers();

    if (!autoRefresh) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void updateLiveLayers();
    }, refreshIntervalSeconds * 1000);

    return () => window.clearInterval(intervalId);
  }, [
    autoRefresh,
    mapReady,
    onModelLayersUpdate,
    onSelectVehicle,
    onVehiclesUpdate,
    refreshIntervalSeconds,
    selectedRouteId,
  ]);

  useEffect(() => {
    if (!mapRef.current || !mapReady || !highlightVehicleEntityId || !latestVehicles) {
      return;
    }

    const vehicle = latestVehicles.features.find(
      (item) => item.properties.entity_id === highlightVehicleEntityId,
    );
    if (!vehicle || !popupRef.current) {
      return;
    }

    const [longitude, latitude] = vehicle.geometry.coordinates as [number, number];
    mapRef.current.flyTo({
      center: [longitude, latitude],
      zoom: Math.max(mapRef.current.getZoom(), 12.5),
      duration: 700,
    });
    popupRef.current
      .setLngLat([longitude, latitude])
      .setHTML(formatVehiclePopup(selectedRouteGeometryRef.current, vehicle))
      .addTo(mapRef.current);
  }, [highlightVehicleEntityId, latestVehicles, mapReady]);

  return <div ref={mapContainerRef} className="map-canvas-full" />;
}
