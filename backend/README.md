# Step 7: backend (FastAPI + PostgreSQL/PostGIS)

The backend puts everything Steps 0-6 produced into one PostGIS database and serves it to the dashboard over a REST API. It can also run new simulations and what-if scenarios on request.

## Run it

**1. Start PostgreSQL with PostGIS.** Pick one of these:

- **Docker (easiest, works on Windows with Docker Desktop):** from the repo root, run `docker compose up -d db`.
- **Windows without Docker:** install PostgreSQL 16 from postgresql.org and tick **PostGIS** in Stack Builder at the end of the installer. Then create a user and database called `relief` with password `relief`, e.g. in pgAdmin.

**2. Load the data and start the API** (from the repo root):

```
pip install -r requirements.txt
python -m backend.app.load                 # creates tables, loads all data (~10 s)
uvicorn backend.app.main:app --reload      # API on http://localhost:8000
```

Open **http://localhost:8000/docs** for interactive docs, where you can try every endpoint in the browser (this replaces Postman for quick tests).

To use a different database, set `DATABASE_URL`, e.g. `postgresql+psycopg://user:pass@host:5432/dbname`.

**3. Tests:** `python -m pytest backend/tests -q` (12 tests; needs the loaded database).

## Database (`app/models.py`, `app/load.py`)

| Table | Rows | Content | Geometry |
|---|---|---|---|
| `districts` | 14 | population, vulnerability, flood exposure | boundary (MultiPolygon) and HQ (Point), from the official shapefile reprojected to WGS84 |
| `centres` | 19 | stock and vehicles | Point |
| `roads` | 21 | distance, travel time | LineString HQ to HQ (estimated roads) |
| `road_events` | 33 | day-by-day closures and slowdowns | – |
| `demand` | 98 | 7 days × 14 districts | – |
| `severity` | 364 | GAT severity (Step 2), 26 days | – |
| `reports` | 7,984 | classified tweets (Step 1) | – |
| `events` | 524 | Step 6 event log: reports, road changes, dispatches, alerts | – |
| `allocations` | 14,053+ | Step 6 shipments, plus every shipment from API simulations | – |
| `metrics` | 50 | results tables from Steps 3-6 | – |
| `artifacts` | 2 | `graph` (GAT embeddings and attention per day, from `python -m ml.gnn.export_embeddings`) and `analytics` (NLP, GAT, MARL and FL summaries for the dashboard) | – |

## Endpoints (`app/main.py`)

| Endpoint | What it returns |
|---|---|
| `GET /districts?day=3` | GeoJSON district map with severity and demand for that day (for the choropleth) |
| `GET /districts/locate?lat=&lon=` | Which district a point is in (PostGIS `ST_Contains`) |
| `GET /centres` | GeoJSON relief-centre markers |
| `GET /centres/nearest?lat=&lon=&k=3` | Nearest centres with distance in km (PostGIS geography distance) |
| `GET /roads?day=3` | GeoJSON road links with that day's status (open / slowed / blocked) |
| `GET /demand`, `GET /severity` | Demand and severity tables, filter by `day` / `district` |
| `GET /reports?district=&date=&actionable=true` | Crisis tweets, most urgent first |
| `GET /events?day=&type=`, `GET /alerts` | Step 6 event log and alerts |
| `GET /allocations?day=&group_by=district` | Shipments, or totals per district / centre / resource |
| `GET /metrics?step=4` | Results tables (fulfilment, worst district, Gini...) |
| `GET /policies` | Available policies: `local_first`, `greedy`, `lp`, `lp_fair`, `lp_rationed`, `mappo` |
| `POST /simulate` | Start a 7-day session: `{"policy": "mappo", "seed": null, "closed_edges": [], "stock_factor": 1, "demand_factor": 1}` |
| `POST /simulate/{id}/step` | Play the next day. Returns per-district coverage and shipments, and saves the shipments to `allocations` |
| `POST /simulate/{id}/close_road` | `{"edge_id": 4}`: close a road from today on (live what-if) |
| `GET /simulate/{id}` | Session state: day, remaining stock, metrics so far |
| `POST /whatif` | Play a whole week with changes and return metrics compared with the unchanged week |
| `GET /graph?day=3` | District graph for the GAT Network page: nodes with severity, 16-feature GAT embedding and centres; edges with road status and learned attention |
| `GET /analytics` | Summaries for the Model Analytics page (NLP scores and counts, GAT error table, MAPPO learning curves, FL rounds) |
| `GET /decisions?day=3` | Crisis reports the reallocation loop acted on that day, most urgent first |
| `GET /decision/{tweet_id}` | Trace one report: district need vs plan, shipments at the next dispatch wave (with route time), coverage under every strategy, alerts |
| `POST /evaluate` | `{"policy": "mappo", "baseline": "lp_rationed", "closed_edges": [], "stock_factor": 1, "demand_factor": 1}`: play the week with both strategies; per-resource, per-district and daily results plus an event timeline |

Sessions are kept in memory (enough for a demo; they're lost when the server restarts).

### Live operations (`app/live.py`)

| Endpoint | What it does |
|---|---|
| `POST /live` | Start a live session `{"policy": "mappo"}` (or `lp_rationed`): the official week on a clock at Day 1 00:00 |
| `POST /live/{id}/advance` | `{"hours": 1}` moves the clock; `{"until": "event"}` stops after the next report, road change or dispatch wave. Returns the new events and the state |
| `POST /live/{id}/report` | `{"text": "...", "district": null}`: a new field report. Runs the Step 1 NLP, adds the people it mentions as new need, releases reserve stock from the nearest centres and re-plans the next wave. Returns the NLP result and the before/after plan change |
| `GET /live/{id}?since=N` | State plus events after sequence number N |
| `POST /analyse` | Step 1 NLP on one message, no plan change |

A live session is the Step 6 loop (`ml/realloc/loop.py`) run event by event: played to the end without typed reports it reproduces the Step 6 official result exactly (one of the tests).

**Tests:** `python -m pytest backend/tests -q` (17 tests).

**Checked:** the API's simulation reproduces the Step 3 result exactly (LP max coverage, 67.8%). It's one of the tests.
