import type { FeedConfig } from "../types";

type FeedFormProps = {
  feeds: FeedConfig | null;
};

export function FeedForm({ feeds }: FeedFormProps) {
  if (!feeds) {
    return <p className="muted">Loading feed configuration...</p>;
  }

  return (
    <div className="feed-grid">
      <label>
        <span>Static GTFS</span>
        <input readOnly value={feeds.static_gtfs_url} />
      </label>
      <label>
        <span>Vehicle Positions</span>
        <input readOnly value={feeds.vehicle_positions_url} />
      </label>
      <label>
        <span>Trip Updates</span>
        <input readOnly value={feeds.trip_updates_url} />
      </label>
      <label>
        <span>Service Alerts</span>
        <input readOnly value={feeds.service_alerts_url} />
      </label>
    </div>
  );
}

