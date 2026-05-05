# GitHub Upload Guide

This guide explains how to publish the **HSL Bus Reliability Analyzer** project to GitHub in a clean, structured, and explainable way.

## Recommended Repository Name

Use one of these names:

- `hsl-bus-reliability-analyzer`
- `helsinki-bus-reliability-gtfs-rt`
- `transit-performance-analyzer-hsl`

Recommended: `hsl-bus-reliability-analyzer`

## What This Repository Should Contain

The repository should contain the source code, notebooks, documentation, and selected proof artifacts:

| Path | Purpose |
|---|---|
| `backend/` | FastAPI backend, GTFS ingestion, GTFS-RT polling, feature engineering, clustering, anomaly detection |
| `frontend/` | React + TypeScript + MapLibre dashboard |
| `notebooks/` | Course notebooks for Part 3 and Part 4, including executed outputs |
| `docs/` | Architecture, viva guide, exam proof pack, presentation guide |
| `reports/screenshots/` | Selected dashboard screenshots for proof |
| `reports/maps/` | Optional exported map HTML from notebook analysis |
| `scripts/` | Utility/export scripts |
| `docker-compose.yml` | Local reproducible stack |
| `.env.example` | Safe environment variable template |
| `README.md` | Main explanation and running instructions |

## What Should Not Be Uploaded

These are ignored by `.gitignore`:

| Path / Pattern | Why ignored |
|---|---|
| `.env` | May contain local secrets or machine-specific settings |
| `frontend/dist/` | Generated build output; can be rebuilt |
| `node_modules/` | Dependency folder; too large and generated |
| `data/raw/`, `data/processed/`, `data/cache/` | Local data cache/runtime artifacts |
| `reports/history_exports/` | Large GTFS-RT history exports; useful locally but not ideal for GitHub |
| `reference/devrel-gtfs-transit/` | External reference repository, not owned source code |
| `presentation_work/` | Temporary presentation build workspace |
| `.ipynb_checkpoints/` | Jupyter-generated cache |

## Why This Structure Is Good

This structure separates the project into clear layers:

1. **Application layer**: backend and frontend.
2. **Data science layer**: notebooks and model code.
3. **Evidence layer**: screenshots, maps, and reports.
4. **Explanation layer**: README and docs.
5. **Reproducibility layer**: Docker Compose and `.env.example`.

That makes the repository understandable for examiners, classmates, and future employers.

## Suggested GitHub Description

> HSL Helsinki bus reliability analyzer using Static GTFS, GTFS-RT, FastAPI, PostgreSQL/PostGIS/TimescaleDB, React/MapLibre, KMeans/DBSCAN clustering, and Isolation Forest/LOF anomaly detection.

## Suggested GitHub Topics

Add these topics on GitHub:

- `gtfs`
- `gtfs-rt`
- `urban-mobility`
- `public-transport`
- `fastapi`
- `react`
- `maplibre`
- `postgis`
- `timescaledb`
- `data-science`
- `clustering`
- `anomaly-detection`
- `helsinki`
- `hsl`

## Upload Steps

Run these from the project root.

```powershell
git init
git status
git add .
git status
git commit -m "Initial release: HSL bus reliability analyzer"
```

Then create a GitHub repository named `hsl-bus-reliability-analyzer`.

If using GitHub CLI:

```powershell
gh repo create hsl-bus-reliability-analyzer --public --source . --remote origin --push
```

If creating the repository manually in the browser:

```powershell
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/hsl-bus-reliability-analyzer.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

## Before Pushing Checklist

- [ ] `.env` is ignored and not staged.
- [ ] `reference/devrel-gtfs-transit/` is ignored and not staged.
- [ ] `frontend/dist/` is ignored and not staged.
- [ ] `reports/history_exports/` is ignored and not staged.
- [ ] README explains the project objective, data, stack, models, evaluation, and dashboard.
- [ ] Notebooks Part 3 and Part 4 are included.
- [ ] Docker Compose instructions are included.
- [ ] Screenshots are included only if useful and not too large.

## What To Say In The GitHub README

The README should make the project story obvious:

> This project analyzes HSL Helsinki bus reliability by combining planned schedules from Static GTFS with realtime GTFS-RT vehicle/trip updates. It creates bus-only route-stop-hour feature windows, evaluates schedule adherence, applies KMeans and DBSCAN for reliability pattern discovery, applies Isolation Forest and LOF for anomaly detection, and visualizes outputs in a React/MapLibre dashboard.

