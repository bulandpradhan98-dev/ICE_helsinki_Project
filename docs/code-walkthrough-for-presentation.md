# Code Walkthrough For Presentation

This guide explains the project code in a way that can be understood by a mixed audience:

- **General audience**: what the system does in plain language.
- **Mobility audience**: how GTFS, GTFS-RT, bus routes, stops, delays, and reliability are used.
- **Architecture audience**: how backend, database, frontend, and Docker work together.
- **Technical audience**: what the important files, functions, SQL queries, and models do.

The goal is not to memorize every line. The goal is to understand the flow well enough to explain:

> We take planned bus schedules from Static GTFS, take live bus evidence from GTFS-RT, store both in a spatial/time-series database, calculate reliability features, run clustering and anomaly detection, and show the results on a live dashboard.

---

## 1. The One-Minute Project Explanation

In simple language:

> This project checks how reliable Helsinki buses are. It compares the planned schedule with realtime bus data. Then it groups similar reliability patterns, detects unusual behavior, and shows everything on a map dashboard.

In technical language:

> The system ingests HSL Static GTFS and GTFS-RT feeds into PostgreSQL/PostGIS/TimescaleDB, computes route-stop-hour feature windows, applies KMeans and DBSCAN for clustering/pattern discovery, applies Isolation Forest and LOF for anomaly detection, and serves the outputs through FastAPI to a React/MapLibre dashboard.

---

## 2. Project Folder Structure

```text
Project Helsinki/
  backend/                  Python FastAPI backend
  backend/app/api/           API endpoints
  backend/app/core/          configuration and database connection
  backend/app/jobs/          ingestion, metrics, modelling jobs
  backend/app/services/      analytics and helper logic
  backend/sql/               database schema
  frontend/                  React dashboard
  frontend/src/components/   dashboard UI components
  frontend/src/lib/          API calls from frontend to backend
  frontend/src/types.ts      TypeScript data contracts
  notebooks/                 Part 3 and Part 4 data science notebooks
  docs/                      explanation and exam guides
  reports/                   screenshots, snapshots, presentation proof
  docker-compose.yml         starts the whole system
```

Plain-English explanation:

> The backend collects and calculates. The database stores. The frontend shows. The notebooks prove the data science. The docs explain the project.

---

## 3. Docker Compose: How The Whole System Starts

File: `docker-compose.yml`

The Docker file starts four services:

```yaml
services:
  db:
    image: timescale/timescaledb-ha:pg16
```

Plain language:

> This starts the database.

Technical meaning:

> We use TimescaleDB on PostgreSQL 16 because realtime bus positions are time-series data. TimescaleDB helps store repeated snapshots efficiently.

```yaml
ports:
  - "5432:5432"
```

Plain language:

> This lets our computer connect to the database.

Technical meaning:

> The database container exposes PostgreSQL port `5432` to the host machine.

```yaml
volumes:
  - postgres_data:/home/postgres/pgdata/data
  - ./backend/sql:/docker-entrypoint-initdb.d
```

Plain language:

> The database data is saved, and SQL schema files are loaded when the database is first created.

Technical meaning:

> `postgres_data` is a Docker volume, so `docker compose down` does not delete collected history. The SQL folder initializes PostGIS, TimescaleDB, and project tables.

```yaml
backend:
  build:
    context: ./backend
  command: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Plain language:

> This starts the Python API.

Technical meaning:

> FastAPI is served through Uvicorn on port `8000`.

```yaml
realtime-poller:
  command: python -m app.workers.realtime_poller
```

Plain language:

> This is the automatic background worker that keeps collecting live GTFS-RT data.

Technical meaning:

> It runs an infinite async polling loop and stores VehiclePositions and TripUpdates every configured interval.

```yaml
frontend:
  command: npm run dev -- --host 0.0.0.0 --port 5173
```

Plain language:

> This starts the dashboard.

Technical meaning:

> Vite serves the React/TypeScript frontend at `http://localhost:5173`.

Presentation sentence:

> Docker Compose gives us a reproducible local system: one command starts the database, backend API, realtime poller, and dashboard.

---

## 4. Backend Entry Point

File: `backend/app/main.py`

```python
from fastapi import FastAPI
```

Plain language:

> We import FastAPI to build the backend API.

Technical meaning:

> FastAPI handles HTTP requests such as `/api/v1/routes` and returns JSON responses.

```python
from fastapi.middleware.cors import CORSMiddleware
```

Plain language:

> This allows the frontend and backend to talk to each other.

Technical meaning:

> CORS middleware permits browser requests from the React app to the API.

```python
from app.api.routes import router
```

Plain language:

> This imports all API endpoints.

Technical meaning:

> Endpoint definitions are kept in `routes.py` and attached to the FastAPI app.

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await get_pool()
    except Exception:
        pass
    yield
```

Plain language:

> When the API starts, it tries to connect to the database.

Technical meaning:

> The lifespan hook initializes the async PostgreSQL connection pool. If the database is not ready immediately, the app does not crash during startup.

```python
app = FastAPI(
    title="Transit Performance Analyzer API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)
```

Plain language:

> This creates the API application.

Technical meaning:

> FastAPI app metadata is defined, JSON responses use `ORJSONResponse` for faster serialization, and startup/shutdown behavior uses `lifespan`.

```python
app.include_router(router)
```

Plain language:

> This connects all routes/endpoints to the app.

Technical meaning:

> The router prefix is `/api/v1`, so endpoints become `/api/v1/health`, `/api/v1/routes`, etc.

---

## 5. Configuration File

File: `backend/app/core/config.py`

```python
class Settings(BaseSettings):
```

Plain language:

> This class stores all project settings.

Technical meaning:

> Pydantic Settings reads environment variables from `.env` and validates types.

Important settings:

```python
database_url: str = "postgresql://transit:transit@db:5432/transit_performance"
```

Plain language:

> This tells the API how to connect to the database.

```python
hsl_static_gtfs_url = "https://infopalvelut.storage.hsldev.com/gtfs/hsl.zip"
```

Plain language:

> This is the URL for the scheduled HSL transit data.

```python
hsl_vehicle_positions_url = "https://realtime.hsl.fi/realtime/vehicle-positions/v2/hsl"
hsl_trip_updates_url = "https://realtime.hsl.fi/realtime/trip-updates/v2/hsl"
```

Plain language:

> These are the live HSL feeds: one for bus positions and one for predicted stop updates.

```python
schedule_early_threshold_minutes: int = -1
schedule_late_threshold_minutes: int = 5
```

Plain language:

> A bus is on time if it is no more than 1 minute early and no more than 5 minutes late.

Technical meaning:

> These thresholds define schedule adherence / OTP.

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Plain language:

> Load settings once and reuse them.

Technical meaning:

> `lru_cache` avoids repeatedly parsing `.env`.

---

## 6. Database Connection Code

File: `backend/app/core/database.py`

```python
_pool: asyncpg.Pool | None = None
```

Plain language:

> This stores the database connection pool.

Technical meaning:

> A global asyncpg pool is reused across API requests.

```python
async def get_pool() -> asyncpg.Pool:
```

Plain language:

> This function gives the app a database connection pool.

```python
_pool = await asyncpg.create_pool(
    dsn=settings.database_url,
    min_size=1,
    max_size=10,
    command_timeout=1800,
)
```

Plain language:

> Create up to 10 reusable database connections.

Technical meaning:

> Pooling avoids opening a new PostgreSQL connection for every request.

```python
async def fetch(query: str, *args: Any)
```

Plain language:

> Run a SQL query and return multiple rows.

```python
async def fetchrow(query: str, *args: Any)
```

Plain language:

> Run a SQL query and return one row.

```python
async def execute(query: str, *args: Any)
```

Plain language:

> Run SQL that changes data.

Presentation sentence:

> The database layer hides connection details, so the rest of the backend can simply call `fetch`, `fetchrow`, or `execute`.

---

## 7. Database Schema

Files: `backend/sql/001_extensions.sql`, `backend/sql/002_schema.sql`

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

Plain language:

> We enable map/spatial support and time-series support.

Technical meaning:

> PostGIS stores stop/vehicle coordinates. TimescaleDB optimizes high-frequency GTFS-RT snapshots.

```sql
CREATE TABLE IF NOT EXISTS gtfs_routes
```

Plain language:

> Stores bus route metadata from `routes.txt`.

Mobility meaning:

> Includes route ID, short name, route type, and color.

```sql
CREATE TABLE IF NOT EXISTS gtfs_stops
```

Plain language:

> Stores stops and their coordinates.

Technical meaning:

> `geom GEOGRAPHY(POINT, 4326)` stores latitude/longitude as spatial data.

```sql
CREATE TABLE IF NOT EXISTS gtfs_trips
```

Plain language:

> Stores scheduled trips on each route.

Mobility meaning:

> A route like `550` has many scheduled trips throughout the day.

```sql
CREATE TABLE IF NOT EXISTS gtfs_stop_times
```

Plain language:

> Stores scheduled arrival/departure times at each stop.

Mobility meaning:

> This is the timetable baseline used to compare realtime predictions.

```sql
CREATE TABLE IF NOT EXISTS rt_vehicle_positions_raw
```

Plain language:

> Stores live bus location snapshots.

Technical meaning:

> This table is a Timescale hypertable because many records arrive repeatedly over time.

```sql
SELECT create_hypertable('rt_vehicle_positions_raw', 'recorded_at', if_not_exists => TRUE);
```

Plain language:

> Tell TimescaleDB this table is time-series data.

```sql
CREATE TABLE IF NOT EXISTS rt_trip_updates_raw
```

Plain language:

> Stores live predicted stop arrivals/departures.

Mobility meaning:

> TripUpdates tell us what the realtime system expects to happen at upcoming stops.

```sql
CREATE TABLE IF NOT EXISTS schedule_adherence_events
```

Plain language:

> Stores calculated early/on-time/late events.

```sql
CREATE TABLE IF NOT EXISTS route_otp_hourly
```

Plain language:

> Stores route-level hourly reliability summaries.

```sql
CREATE TABLE IF NOT EXISTS stop_otp_hourly
```

Plain language:

> Stores stop-level hourly reliability summaries.

Presentation sentence:

> The schema separates scheduled data, realtime raw data, calculated reliability events, and aggregated analytics.

---

## 8. Static GTFS Import

File: `backend/app/jobs/static_gtfs.py`

Static GTFS is the planned transit system.

```python
import zipfile
import csv
```

Plain language:

> Static GTFS comes as a `.zip` containing CSV text files.

```python
def _read_csv_tables(content: bytes) -> dict[str, list[dict[str, str]]]:
```

Plain language:

> Read the GTFS zip and turn every `.txt` file into rows.

Technical meaning:

> Each GTFS file becomes a list of dictionaries, where column names are keys.

```python
with zipfile.ZipFile(io.BytesIO(content)) as archive:
```

Plain language:

> Open the downloaded GTFS zip in memory.

```python
if not name.endswith(".txt"):
    continue
```

Plain language:

> Ignore files that are not GTFS text tables.

```python
reader = csv.DictReader(text)
tables[name] = list(reader)
```

Plain language:

> Convert CSV rows into Python dictionaries.

```python
def summarize_gtfs_tables(...)
```

Plain language:

> Count the rows and find the service date range.

Mobility meaning:

> This tells us how many routes, stops, trips, and timetable rows were imported.

```python
async def fetch_static_gtfs_tables(url: str)
```

Plain language:

> Download the latest HSL GTFS zip from the internet.

```python
response.raise_for_status()
```

Plain language:

> Stop if the download fails.

```python
async def import_static_gtfs(url: str)
```

Plain language:

> This is the main import function.

Important block:

```python
routes = tables.get("routes.txt", [])
stops = tables.get("stops.txt", [])
trips = tables.get("trips.txt", [])
stop_times = tables.get("stop_times.txt", [])
shapes = tables.get("shapes.txt", [])
```

Plain language:

> Extract the important GTFS tables.

Mobility meaning:

> Routes are bus lines, stops are physical stop locations, trips are scheduled journeys, stop_times are timetable entries, and shapes are route lines for the map.

```python
route_records = [...]
```

Plain language:

> Prepare route rows for database insert.

```python
int(row["route_type"]) if row.get("route_type") else None
```

Plain language:

> Convert route type from text into number.

Why it matters:

> Later we filter only bus-family route types `701`, `702`, and `704`.

```python
stop_records = [...]
```

Plain language:

> Prepare stop rows with latitude and longitude.

```python
float(row["stop_lat"])
float(row["stop_lon"])
```

Plain language:

> Convert stop coordinates into numbers for mapping.

```python
async with conn.transaction():
```

Plain language:

> Save everything safely as one database transaction.

Technical meaning:

> If one part fails, the database does not get a half-imported GTFS batch.

---

## 9. GTFS-RT Polling

File: `backend/app/jobs/gtfs_rt_poller.py`

GTFS-RT is live or near-live data.

```python
from google.transit import gtfs_realtime_pb2
```

Plain language:

> This library understands GTFS-RT protocol buffer files.

Technical meaning:

> GTFS-RT is not normal CSV/JSON. It is binary protobuf data.

```python
async def fetch_protobuf(url: str) -> gtfs_realtime_pb2.FeedMessage:
```

Plain language:

> Download one realtime feed.

```python
feed.ParseFromString(response.content)
```

Plain language:

> Decode the binary GTFS-RT file into readable objects.

```python
def normalize_vehicle_positions(feed)
```

Plain language:

> Convert live vehicle positions into simple rows.

Important fields:

```python
"route_id": trip.route_id or None
"trip_id": trip.trip_id or None
"stop_id": entity.vehicle.stop_id or None
"current_status": ...
"latitude": position.latitude
"longitude": position.longitude
"speed": ...
```

Plain language:

> For each bus, we store route, trip, current stop context, position, speed, and timestamp.

Mobility meaning:

> This creates the orange live bus dots on the dashboard.

```python
def normalize_trip_updates(feed)
```

Plain language:

> Convert realtime stop predictions into simple rows.

Important fields:

```python
"arrival_delay_seconds"
"departure_delay_seconds"
"arrival_time"
"departure_time"
```

Plain language:

> These are the values used to estimate whether the bus is early, on time, or late.

Important limitation:

> HSL does not always provide explicit delay. Sometimes we calculate delay by comparing predicted arrival time with scheduled GTFS time.

```python
async def poll_and_store_realtime()
```

Plain language:

> Download both live feeds and save them to the database.

```python
INSERT INTO rt_vehicle_positions_raw
```

Plain language:

> Save live bus locations.

```python
INSERT INTO rt_trip_updates_raw
```

Plain language:

> Save predicted stop updates as JSON payload.

Presentation sentence:

> VehiclePositions show where buses are. TripUpdates help compare live predictions against the schedule.

---

## 10. Automatic Realtime Worker

File: `backend/app/workers/realtime_poller.py`

```python
async def run_forever() -> None:
```

Plain language:

> This worker never stops while Docker is running.

```python
interval_seconds = max(settings.gtfs_rt_poll_interval_seconds, 5)
```

Plain language:

> Poll at the configured interval, but never faster than 5 seconds.

```python
while True:
```

Plain language:

> Repeat forever.

```python
details = await poll_and_store_realtime()
```

Plain language:

> Fetch the latest realtime data and store it.

```python
await asyncio.sleep(interval_seconds)
```

Plain language:

> Wait before the next poll.

Mobility explanation:

> The longer this worker runs, the more GTFS-RT history we collect for analysis.

---

## 11. Schedule Adherence Logic

File: `backend/app/services/schedule_adherence.py`

```python
def classify_delay(delay_minutes: float, early_threshold: int, late_threshold: int) -> str:
```

Plain language:

> Decide whether one bus event is early, on time, or late.

```python
if delay_minutes < early_threshold:
    return "early"
```

Plain language:

> If the bus is more than 1 minute early, classify it as early.

```python
if delay_minutes > late_threshold:
    return "late"
```

Plain language:

> If the bus is more than 5 minutes late, classify it as late.

```python
return "on_time"
```

Plain language:

> Otherwise, it is on time.

Technical definition:

```text
on time = delay between -1 and +5 minutes
```

```python
def on_time_ratio(...)
```

Plain language:

> Count how many events are on time and convert that into a percentage.

```python
def average_delay(...)
```

Plain language:

> Calculate average delay in minutes.

Presentation sentence:

> Schedule adherence is the core metric. It translates raw delay minutes into an operational category: early, on time, or late.

---

## 12. Analytics Queries

File: `backend/app/services/analytics.py`

```python
BUS_ROUTE_TYPES = [701, 702, 704]
```

Plain language:

> Only bus-family route types are included.

Mobility meaning:

> We exclude tram, metro, rail, ferry, and other modes so the analysis remains bus-specific.

```sql
FROM route_otp_hourly
WHERE bucket >= NOW() - ($1 * interval '1 hour')
  AND route_type = ANY($2::int[]);
```

Plain language:

> Look at recent route reliability and only keep buses.

Technical meaning:

> `$1` is the time window, usually 24 hours. `$2` is `[701, 702, 704]`.

```python
async def fetch_summary(window_hours: int = 24)
```

Plain language:

> Get network-wide bus reliability summary.

```python
async def fetch_route_metrics(...)
```

Plain language:

> Get reliability per bus route.

```python
if on_time_percentage < 80:
    status = "poor"
elif on_time_percentage < 90:
    status = "watch"
```

Plain language:

> Convert numbers into readable labels: good, watch, or poor.

Mobility meaning:

> Planners do not only need percentages; they need priority categories.

---

## 13. API Routes

File: `backend/app/api/routes.py`

This file exposes the backend data to the frontend and notebooks.

```python
router = APIRouter(prefix="/api/v1")
```

Plain language:

> All API endpoints start with `/api/v1`.

```python
BUS_ROUTE_TYPES = [701, 702, 704]
```

Plain language:

> Every important route/model endpoint is filtered to buses.

```python
@router.get("/health")
```

Plain language:

> Simple endpoint to check whether the API is alive.

```python
@router.get("/summary")
```

Plain language:

> Gives high-level network reliability summary.

```python
@router.get("/routes")
```

Plain language:

> Gives route-level metrics for the route explorer.

```python
@router.get("/routes/{route_id}/geometry")
```

Plain language:

> Gives the route line geometry shown on the map.

Technical meaning:

> The SQL selects the most common shape for a route and converts it to GeoJSON using `ST_AsGeoJSON`.

```sql
ST_AsGeoJSON(ST_MakeLine(gs.geom::geometry ORDER BY gs.shape_pt_sequence)) AS geometry
```

Plain language:

> Convert many route shape points into one route line.

```python
@router.get("/network/vehicles")
```

Plain language:

> Gives live bus vehicle points for the orange dots on the map.

```python
@router.get("/routes/{route_id}/comparison")
```

Plain language:

> Compares scheduled stops with realtime evidence for one selected route.

```python
@router.get("/models/status")
```

Plain language:

> Shows how many feature windows, clusters, hotspots, and anomalies exist.

```python
@router.post("/models/features/recompute")
```

Plain language:

> Rebuild model-ready feature windows.

```python
@router.post("/models/clusters/recompute")
```

Plain language:

> Re-run KMeans and DBSCAN.

```python
@router.post("/models/anomalies/recompute")
```

Plain language:

> Re-run Isolation Forest and LOF anomaly detection.

Presentation sentence:

> The API is the bridge between the database, notebooks, and dashboard.

---

## 14. Model Feature Windows

File: `backend/app/jobs/modeling.py`

This is the main data science engine.

```python
MODEL_FEATURE_COLUMNS = [...]
```

Plain language:

> These are the numerical columns used by the machine learning models.

Important features:

| Feature | Plain meaning |
|---|---|
| `mean_delay_minutes` | average delay in that window |
| `median_delay_minutes` | middle delay value |
| `p95_abs_delay_minutes` | near-worst delay magnitude |
| `delay_std_minutes` | how variable delay is |
| `on_time_ratio` | share of on-time observations |
| `late_ratio` | share of late observations |
| `early_ratio` | share of early observations |
| `prediction_coverage_ratio` | how complete realtime predictions are |
| `vehicle_observation_count` | how many vehicle snapshots exist |
| `feed_age_seconds` | how fresh/stale the feed is |
| `hour_of_day` | time-of-day feature |
| `day_of_week` | weekday feature |
| `is_weekend` | weekend indicator |

Presentation sentence:

> A feature window is one summarized route-stop-hour row used by the models.

Example:

```text
Route 560 + Itäkeskus stop + 08:00-09:00
= mean delay, p95 delay, coverage, on-time ratio, late ratio, etc.
```

---

## 15. Model Output Tables

File: `backend/app/jobs/modeling.py`

```sql
CREATE TABLE IF NOT EXISTS model_run_metadata
```

Plain language:

> Stores when each model run happened and what settings were selected.

```sql
CREATE TABLE IF NOT EXISTS model_feature_windows
```

Plain language:

> Stores route-stop-hour features.

```sql
CREATE TABLE IF NOT EXISTS cluster_assignments_daily
```

Plain language:

> Stores KMeans/DBSCAN cluster labels and reliability categories.

```sql
CREATE TABLE IF NOT EXISTS anomaly_scores_live
```

Plain language:

> Stores Isolation Forest and LOF anomaly scores.

Architecture meaning:

> Model outputs are saved in the database, so the dashboard can load them quickly without retraining models every time.

---

## 16. Feature Recompute SQL

File: `backend/app/jobs/modeling.py`

The SQL called `FEATURE_RECOMPUTE_SQL` is long, but its logic is simple.

### Step 1: Pick latest GTFS batch

```sql
WITH latest_batch AS (
  SELECT id
  FROM gtfs_import_batches
  ORDER BY import_started_at DESC
  LIMIT 1
)
```

Plain language:

> Use the latest imported HSL schedule.

### Step 2: Expand TripUpdates

```sql
CROSS JOIN LATERAL jsonb_array_elements(...)
```

Plain language:

> TripUpdates store many stop updates inside one JSON payload. This expands them into one row per stop update.

### Step 3: Calculate delay

```sql
predicted arrival time - scheduled GTFS arrival time
```

Plain language:

> Compare live prediction with scheduled timetable.

Technical meaning:

> The query uses GTFS-RT epoch prediction times and GTFS static `arrival_time` / `departure_time`.

### Step 4: Aggregate by route-stop-hour

```sql
GROUP BY e.bucket, e.route_id, e.stop_id
```

Plain language:

> Summarize many observations into one model row.

### Step 5: Store features

```sql
INSERT INTO model_feature_windows (...)
```

Plain language:

> Save the features so KMeans, DBSCAN, Isolation Forest, and LOF can use them.

---

## 17. KMeans In The Project

File: `backend/app/jobs/modeling.py`, notebooks Part 3/4

```python
from sklearn.cluster import KMeans
```

Plain language:

> Import a clustering algorithm.

What KMeans does:

> KMeans groups bus reliability windows into a fixed number of groups.

In our project:

```text
k = 2
```

Why:

> We tested `k = 2` to `k = 10`. `k = 2` had the highest Silhouette Score and was easiest to explain as broad reliable/normal vs watch/problem behavior.

Technical explanation:

> KMeans minimizes within-cluster distance after feature scaling. The selected `k` is supported by Silhouette, Davies-Bouldin, Calinski-Harabasz, and interpretability.

---

## 18. DBSCAN In The Project

File: `backend/app/jobs/modeling.py`, notebooks Part 3/4

```python
from sklearn.cluster import DBSCAN
```

Plain language:

> Import a clustering algorithm that finds dense groups and leaves out noise.

What DBSCAN does:

> Finds hotspot-like groups without forcing every point into a cluster.

In our project:

```text
eps = 0.8
min_samples = 20
```

Why:

> This gave strong separation and meaningful hotspot groups. `eps` is the neighborhood radius, and `min_samples` means a hotspot needs at least 20 nearby similar points.

Mobility meaning:

> DBSCAN is useful because reliability problems often concentrate around stops, corridors, terminals, or specific operational areas.

---

## 19. Isolation Forest In The Project

File: `backend/app/jobs/modeling.py`, notebooks Part 3/4

```python
from sklearn.ensemble import IsolationForest
```

Plain language:

> Import an anomaly detection model.

What Isolation Forest does:

> It finds rows that are easy to separate from normal data.

In our project:

> It flags unusual bus reliability windows, such as extreme delay, stale feed, or coverage dropout.

Result:

```text
Precision@K = 0.872
```

Plain language:

> Of the top anomaly windows it flagged, 87.2% matched our operational warning rules.

Important limitation:

> These are not official disruption labels. They are pseudo-labels from practical warning signals.

---

## 20. LOF In The Project

File: `backend/app/jobs/modeling.py`, notebooks Part 3/4

```python
from sklearn.neighbors import LocalOutlierFactor
```

Plain language:

> Import a model that checks whether a point looks unusual compared to nearby points.

What LOF does:

> It compares each bus window with its local neighborhood.

Mobility meaning:

> What is normal for one corridor might be unusual for another. LOF helps capture local abnormal behavior.

---

## 21. Model Evaluation Metrics

Used in Part 3 and Part 4 notebooks.

### Silhouette

Plain language:

> Measures how clearly separated clusters are.

Technical:

> Higher is better.

### Davies-Bouldin

Plain language:

> Measures cluster overlap.

Technical:

> Lower is better.

### Calinski-Harabasz

Plain language:

> Measures compactness and separation.

Technical:

> Higher is better.

### Precision@K

Plain language:

> Of the top K anomalies, how many matched our warning labels?

Technical:

> Used because anomaly detection produces ranked suspicious windows.

### False alarm share

Plain language:

> How many alerts might waste planner attention?

Mobility meaning:

> In operations, too many false alarms reduce trust.

---

## 22. Frontend API Layer

File: `frontend/src/lib/api.ts`

```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
```

Plain language:

> This tells the frontend where the backend API lives.

Technical meaning:

> Vite reads `VITE_API_BASE_URL` from environment variables; otherwise it uses localhost.

```typescript
async function readJson<T>(path: string): Promise<T>
```

Plain language:

> Fetch JSON data from the backend.

Technical meaning:

> Generic TypeScript function that returns strongly typed API responses.

```typescript
if (!response.ok) {
  throw new Error(...)
}
```

Plain language:

> If the backend fails, show an error instead of pretending the data exists.

```typescript
export function fetchRoutes()
```

Plain language:

> Get bus route metrics for the route explorer.

```typescript
export function fetchNetworkVehicles(mode = "bus")
```

Plain language:

> Get live bus dots for the map.

```typescript
export function runClusterRecompute()
```

Plain language:

> Button action to re-run clustering from the dashboard.

Presentation sentence:

> The frontend API layer is the clean bridge between React components and FastAPI endpoints.

---

## 23. TypeScript Data Contracts

File: `frontend/src/types.ts`

```typescript
export type RouteMetric = { ... }
```

Plain language:

> Defines what a route metric looks like.

Technical meaning:

> TypeScript catches mistakes if the UI tries to use a field that does not exist.

```typescript
export type RouteVehicles = { type: "FeatureCollection"; ... }
```

Plain language:

> Defines live bus vehicle map data.

Mobility meaning:

> Each vehicle has route, vehicle label, trip ID, next stop, delay, speed, and map coordinates.

```typescript
export type ModelClusters = { ... }
```

Plain language:

> Defines the cluster map layer.

```typescript
export type LiveAnomalies = { ... }
```

Plain language:

> Defines the anomaly map layer.

Presentation sentence:

> Types keep the frontend and backend speaking the same language.

---

## 24. Main Dashboard Component

File: `frontend/src/App.tsx`

```typescript
const BUS_ROUTE_TYPES = new Set([701, 702, 704]);
```

Plain language:

> The dashboard only shows HSL bus-family services.

```typescript
const [routes, setRoutes] = useState<RouteMetric[]>([]);
```

Plain language:

> Store route data in the browser.

Technical:

> React state triggers UI updates when API data changes.

```typescript
const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
```

Plain language:

> Remember which route the user clicked.

```typescript
const [selectedVehicle, setSelectedVehicle] = useState(...)
```

Plain language:

> Remember which live bus dot the user clicked.

```typescript
const busRoutes = useMemo(...)
```

Plain language:

> Filter all routes down to bus routes.

Technical:

> `useMemo` avoids recalculating the filtered route list unnecessarily.

```typescript
formatOperationMessage(...)
```

Plain language:

> Converts backend operation results into readable dashboard messages.

Example:

```text
Feature rebuild complete. 402,576 bus model windows are ready.
```

Presentation sentence:

> `App.tsx` is the dashboard brain: it loads data, stores user selections, runs recompute buttons, and passes map data into components.

---

## 25. Map Component

File: `frontend/src/components/MapPanel.tsx`

```typescript
import maplibregl from "maplibre-gl";
```

Plain language:

> Import the map library.

```typescript
const map = new maplibregl.Map(...)
```

Plain language:

> Create the map centered on Helsinki.

```typescript
center: [24.9384, 60.1699]
```

Plain language:

> Helsinki coordinates.

```typescript
tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]
```

Plain language:

> Use OpenStreetMap as the background map.

```typescript
map.addSource("network-routes", ...)
```

Plain language:

> Add the static bus network layer.

```typescript
map.addSource("selected-route", ...)
```

Plain language:

> Add the highlighted selected route.

```typescript
map.addSource("live-vehicles", ...)
```

Plain language:

> Add live bus dots.

```typescript
formatVehiclePopup(...)
```

Plain language:

> Creates the popup shown when clicking a bus.

Important popup fields:

| Field | Meaning |
|---|---|
| `vehicle_label` | bus vehicle identifier |
| `trip_id` | realtime trip ID if available |
| `current_status` | stopped, incoming, or in transit |
| `next_stop_name` | best available next stop |
| `next_stop_delay_minutes` | predicted delay at next stop |
| `speed` | reported speed if available |
| `upcoming_stops` | next predicted stops from TripUpdates |

```typescript
formatClusterPopup(...)
```

Plain language:

> Creates popup text for reliability cluster markers.

```typescript
formatAnomalyPopup(...)
```

Plain language:

> Creates popup text for anomaly markers.

Presentation sentence:

> The map combines planned route geometry, live bus locations, stop reliability, clusters, and anomalies in one spatial view.

---

## 26. What Each Map Color Means

| Color | Meaning |
|---|---|
| Orange dots | live GTFS-RT bus vehicles |
| Green stop markers | reliable bus stop windows |
| Blue stop markers | delay hotspot windows |
| Red markers | watch/anomaly/late-heavy behavior |
| Orange cluster markers | low realtime coverage or hotspot warning |
| Grey | static-only, unavailable, or neutral background |

Short explanation:

> Green means reliable, blue means delay hotspot, red means warning/anomaly, orange means live buses or coverage/hotspot warning, and grey means no enough live comparison.

---

## 27. Notebooks: Part 3 And Part 4

Files:

- `notebooks/03_data_mining_gtfs_rt.ipynb`
- `notebooks/04_model_evaluation_interpretation.ipynb`
- `notebooks/04_model_evaluation_interpretation_explained.ipynb`

Part 3 notebook:

> Explains model development: KMeans, DBSCAN, Isolation Forest, and LOF.

Part 4 notebook:

> Evaluates the models using clustering metrics, anomaly metrics, maps, tables, and interpretation.

Explained notebook:

> Teaching/viva version of Part 4 in plain language.

Presentation sentence:

> The dashboard proves the system works visually, but the notebooks prove the data science process for grading.

---

## 28. How To Explain The Full Data Flow

Use this step-by-step story:

1. **Static GTFS import**

   > We download the official HSL schedule zip and store routes, stops, trips, stop times, and shapes.

2. **GTFS-RT polling**

   > Every 30 seconds, the poller stores live bus positions and trip updates.

3. **Schedule comparison**

   > We compare realtime predicted arrival/departure times with static scheduled times.

4. **Feature windows**

   > We aggregate raw data into route-stop-hour rows with delay, coverage, and freshness features.

5. **Clustering**

   > KMeans groups similar reliability patterns. DBSCAN finds hotspot-like dense areas.

6. **Anomaly detection**

   > Isolation Forest and LOF find unusual bus reliability windows.

7. **API**

   > FastAPI exposes routes, stops, vehicles, clusters, anomalies, and status.

8. **Dashboard**

   > React and MapLibre show live buses, selected routes, reliability layers, and model explanations.

---

## 29. How To Explain To Different Audiences

### For General Audience

> The system checks whether buses are following the timetable and shows problem areas on a map.

### For Mobility Planners

> It identifies routes, stops, and time windows where bus reliability is strong, weak, or unusual. It can support investigation of delays, low prediction coverage, and recurring hotspots.

### For Data Science Audience

> The project engineers route-stop-hour features from GTFS and GTFS-RT, standardizes model inputs, tunes KMeans/DBSCAN, evaluates clusters with internal metrics, and evaluates anomalies using pseudo-labels.

### For Software/Architecture Audience

> The project is modular: Docker Compose runs a FastAPI backend, PostgreSQL/PostGIS/TimescaleDB database, realtime worker, and React/MapLibre frontend. API endpoints serve precomputed analytics to the dashboard.

---

## 30. Important Limitations To Explain Honestly

1. **GTFS-RT history is limited**

   > History is collected while Docker and the poller are running.

2. **Missing TripUpdates are ambiguous**

   > Missing predictions do not automatically mean buses are on time or late.

3. **Pseudo-labels are not official incident labels**

   > They are practical warning signals such as extreme delay, stale feed, and coverage dropout.

4. **Next stop is best-effort**

   > We can show next stop when GTFS-RT or static context provides enough information, but not every live bus reports complete stop/trip details.

5. **Predictive modelling is future work**

   > The current project focuses on clustering and anomaly detection, which satisfy the exam requirement.

---

## 31. Final Explanation Script

Use this when presenting the code:

> The project starts with Docker Compose. It launches a Timescale/PostGIS database, a FastAPI backend, a GTFS-RT poller, and a React dashboard. The backend reads configuration from `.env`, connects to PostgreSQL using an async connection pool, and exposes API endpoints under `/api/v1`.
>
> Static GTFS import downloads the HSL schedule zip and stores routes, stops, trips, stop times, and shapes. The realtime poller downloads GTFS-RT VehiclePositions and TripUpdates, decodes protobuf messages, normalizes them into database rows, and repeats this process in the background.
>
> The schedule-adherence logic compares realtime prediction evidence with static schedule times. Events are classified as early, on time, or late using the rule: on time is between -1 and +5 minutes. Then the modelling job aggregates raw observations into route-stop-hour feature windows.
>
> These feature windows are used by KMeans and DBSCAN to discover reliability patterns and hotspots. Isolation Forest and LOF detect unusual windows. The outputs are saved into model tables so the dashboard can display them quickly.
>
> On the frontend, React stores the current routes, selected route, selected vehicle, live vehicles, model layers, and dashboard state. MapLibre renders the Helsinki map, static bus routes, orange live bus dots, green reliable stops, blue delay hotspots, and red anomaly markers.
>
> The notebooks explain and evaluate the data science process. The dashboard makes the same analysis visible and interactive.

---

## 32. Short Answer If Someone Asks "What Did You Code?"

> I built a full-stack urban mobility analytics system. The backend ingests GTFS and GTFS-RT data, stores it in a spatial time-series database, calculates schedule adherence, creates machine-learning feature windows, runs clustering and anomaly detection, and exposes everything through FastAPI. The frontend uses React and MapLibre to show live buses, routes, reliability clusters, hotspots, anomalies, and route-level intelligence. The notebooks validate the data science methods and explain the results.

