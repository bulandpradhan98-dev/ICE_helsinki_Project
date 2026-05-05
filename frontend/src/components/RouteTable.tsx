import type { RouteMetric } from "../types";

type RouteTableProps = {
  routes: RouteMetric[];
  selectedRouteId: string | null;
  onSelectRoute: (routeId: string) => void;
};

export function RouteTable({ routes, selectedRouteId, onSelectRoute }: RouteTableProps) {
  if (!routes.length) {
    return <p className="muted">No aggregated route data yet. Start the ingestion pipeline to populate OTP tables.</p>;
  }

  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            <th>Route</th>
            <th>On-time %</th>
            <th>Avg delay</th>
            <th>Events</th>
          </tr>
        </thead>
        <tbody>
          {routes.map((route) => (
            <tr
              key={route.route_id}
              className={selectedRouteId === route.route_id ? "selected-row" : undefined}
              onClick={() => onSelectRoute(route.route_id)}
            >
              <td>{route.route_short_name || route.route_id}</td>
              <td>{route.on_time_percentage.toFixed(1)}%</td>
              <td>{route.avg_delay_minutes.toFixed(1)} min</td>
              <td>{route.total_events}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

