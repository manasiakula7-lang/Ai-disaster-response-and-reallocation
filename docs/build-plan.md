# AI-Driven Disaster Response & Resource Allocation: Build Plan

Source: `methodology.pptx` (E1CSA313 Design Project-1; team Priya Kumari, Afrah Saleem, B Sreyah, Manasi Akula; mentor Dr. Mousumi Karmakar). Drafted 2026-10-10.

## 1. What the deck proposes

**Goal:** timely, fair and effective allocation of limited relief resources (food, water, medicine, rescue teams) across relief centres during a disaster, with an explainable decision-support dashboard.

**Pipeline (slide 12, "Proposed Methodology"):**

1. **Data collection**: HumAID crisis tweets, Census of India / NFHS-5 vulnerability, historical flood & weather, OpenStreetMap roads, simulated relief-centre stock/capacity.
2. **Preprocessing & features**: NLP/LLM extraction of location, need, quantity and urgency from text; cleaning and integration; spatial, demographic and vulnerability features.
3. **Disaster graph + GAT**: areas and relief centres as nodes, roads as weighted edges (distance, travel time, open/blocked); a Graph Attention Network learns which regions and routes matter now.
4. **MARL with PPO**: each relief centre is an agent; cooperative policy for allocating resources.
5. **Federated learning (Flower, FedAvg)**: centres train locally, share only model updates.
6. **Fairness & vulnerability**: vulnerability-weighted reward, Gini coefficient, no repeated neglect of vulnerable areas.
7. **Dynamic reallocation loop**: new report or road closure → update demand/stock/roads → agents recompute → new routes and deployment plan.
8. **Output**: React + Leaflet GIS map, Recharts dashboards (allocation, alerts, Gini, model metrics), what-if analysis.

**Novelty claimed:** real-time demand detection + dynamic reallocation + fairness + multi-centre cooperation + privacy-preserving learning in one integrated system.

## 2. Requirements

**Hardware:** Intel i5 / Ryzen 5 laptop, 8 GB RAM (16 preferred), 256 GB SSD, internet. NVIDIA GPU (4 GB+) optional; CPU is enough for the prototype scale.

**Software:** Python (ML, backend), JavaScript (frontend), SQL. FastAPI, ReactJS, PyTorch + PyTorch Geometric, Pandas/NumPy/GeoPandas, Flower, Leaflet.js, Recharts/Chart.js, Google OR-Tools, PostgreSQL + PostGIS, QGIS, Postman, GitHub. GCP free tier optional for deployment.

## 3. Where the project stands (slides 18-19)

Phase 1 is **already done** for **Kerala, 2018 floods**:

| Output | Content |
|---|---|
| `kerala_population_2018.csv` | rural + urban population per district |
| `kerala_vulnerability.csv` | NFHS-5, min-max/inverse normalised Vulnerability Index |
| `kerala_flood_exposure.csv` | KSDMA rasters, zonal stats for 6 flood scenarios |
| District boundaries | `.shp`, neighbours via `touches()` |
| HumAID Kerala Floods 2018 | downloaded and labelled, ready for NLP |
| `district_features.csv`, `graph_nodes.csv`, `graph_edges.csv` | 14 nodes, 21 adjacency edges, 10 features, 0 missing |
| `validate_phase1.py` | sanity checks |

**Open item:** OSM road network (`.osm.pbf`) not processed because `pyrosm` failed to install.

## 4. Step-by-step build plan (from Phase 2 on)

Each step ends in something runnable and demo-able, so the project is presentable at any point.

### Step 0: Repo and environment
- One GitHub repo, layout: `data/` (raw + processed, large files git-ignored), `ml/` (nlp, gnn, marl, fl, fairness), `backend/` (FastAPI), `frontend/` (React), `notebooks/`, `docs/`.
- Move the existing Phase 1 scripts and CSVs in; pin a `requirements.txt` (CPU PyTorch + PyG).
- **Fix the roads gap:** use `osmnx` (or `pyrosm` via conda-forge) on the Kerala `.pbf`/bbox, then aggregate to district-to-district edges with real road distance and travel time. Keep the 21 adjacency edges as fallback.
- Add relief-centre simulation: ~1-3 centres per district with stock of food, water, medicine, rescue teams.

### Step 1: NLP demand detection (Phase 2)
- Baseline: fine-tune DistilBERT (or TF-IDF + logistic regression first) on HumAID labels for need type and urgency.
- Location: match district/town names with a Kerala gazetteer (fuzzy + spaCy NER).
- Output per time window: `demand[district][resource]` with an urgency score.
- Optional: an LLM extractor for quantity, compared against the baseline on a hand-labelled sample.
- **Metric:** macro-F1 on HumAID test split; location-match accuracy on ~100 manual samples.

### Step 2: Severity model with GAT (Phase 3)
- PyG graph: 14 district nodes (10 features + NLP demand), edges weighted by travel time and open/blocked.
- Target: severity class or score (derive from flood exposure + report volume; document the labelling choice, since ground truth is thin).
- Compare against MLP/GCN baselines so the GAT result means something; export attention weights for explainability.

### Step 3: Allocation environment + baselines (Phase 4a)
- A gym-style simulator: centres hold stock, districts emit demand over time steps, roads can close, delivery time follows travel time.
- Baselines first: greedy (nearest/most-severe) and an **OR-Tools** optimiser. These give the numbers the RL has to beat.
- Metrics: demand fulfilment %, average delivery delay, unmet demand in vulnerable districts, Gini of fulfilment.

### Step 4: MARL with PPO + fairness (Phase 4b)
- One agent per relief centre, shared-parameter PPO (e.g., MAPPO via a small custom loop or `torchrl`/`rllib`), GAT embeddings as part of the observation.
- Reward = fulfilment − delay penalty + α·vulnerability-weighted fulfilment − β·Gini; sweep α:β to show the efficiency-equity trade-off.
- **Metric:** beat greedy on fairness without large efficiency loss; report vs. OR-Tools.
- **Done (2026-10-19):** `ml/marl/`. MAPPO cuts Gini from 0.060 (best LP) to 0.017-0.019 and lifts the worst district from 56% to 70-75% of need, for about 3.5 points less total fulfilment. Total fulfilment is capped near 68-71% by stock (hindsight optimum). See `ml/marl/README.md`.

### Step 5: Federated training with Flower (Phase 5)
- Each centre trains its local model on its own slice of data; FedAvg over Flower in simulation mode on one laptop.
- Compare centralised vs federated performance; that gap is the privacy cost to report.
- Keep this scoped: it is a demonstration, not a production deployment.
- **Done (2026-10-19):** `ml/fl/`. Flower 1.40 FedAvg over 19 simulated centres, each training only on its own decisions. Federated model: 65.8% fulfilment, worst district 71.8%, Gini 0.025 vs centralised 66.8% / 74.5% / 0.019 (50 unseen weeks). Independent per-centre models did 68.2% / 71.7% / 0.027, which points to personalised FL. See `ml/fl/README.md`.

### Step 6: Dynamic reallocation loop (Phase 6)
- Event stream replays HumAID tweets in time order plus scripted road closures.
- On each event: update demand/stock/edges → re-run policy → emit new plan + alerts.
- Scenario script: "Kerala Aug 2018, day 1-7" as the main demo.
- **Done (2026-10-19):** `ml/realloc/`. 449 real tweets + 33 road events replayed in time order, 4 dispatch waves a day. Replanning lifts MAPPO from 60.5% to 62.7% fulfilment (worst district 63% to 67%) vs a fixed morning plan; almost all of the gain comes from the tweets. Writes `event_log.csv` and `plans.csv` for the dashboard. See `ml/realloc/README.md`.

### Step 7: Backend + database (Phase 7)
- PostgreSQL + PostGIS: districts (geometry), centres, roads, stock, demand, allocations, event log.
- FastAPI endpoints: `/districts`, `/centres`, `/demand`, `/allocations`, `/simulate/step`, `/whatif`, `/metrics`. Test with Postman.
- **Done (2026-10-19):** `backend/`. PostGIS schema (10 tables), loader for all Step 0-6 outputs, 20 endpoints incl. spatial queries, live simulation sessions with road closures, and what-if; 12 passing tests; `docker-compose.yml` for the database. See `backend/README.md`.

### Step 8: Dashboard (Phase 8)
- React + Leaflet: district choropleth by severity, centre markers, allocation routes, blocked roads.
- Recharts: fulfilment per resource, alerts, Gini over time, model metrics.
- What-if panel: close a road / add a centre / change stock and rerun.

### Step 9: Evaluation, write-up, demo
- One results table: greedy vs OR-Tools vs MARL vs MARL+fairness vs federated; fulfilment, delay, Gini, vulnerable-area coverage.
- Ablations (no GAT, no NLP, no fairness term). Fills deck slides 23-27 (Modules, Experimentation, Results, Conclusion, Code).
- Optional GCP deployment.

## 5. Suggested split for four people

| Track | Steps |
|---|---|
| Data + NLP | 0 (roads), 1 |
| Graph + severity | 2 |
| RL + fairness + FL | 3, 4, 5 |
| Backend + dashboard | 7, 8 (can start in parallel with mock data) |

Step 6 and 9 are joint.

## 6. Risks to decide on early

- **Scope:** GAT + MARL + FL + LLM + full-stack is a lot. Recommended minimum viable path: Steps 0-4 and 6-8 with a simple Flower demo; LLM extraction optional.
- **Ground-truth severity labels** are not in the data; the labelling rule must be stated.
- **Scale:** 14 districts is small for a GAT; consider taluk-level nodes (~78 in Kerala) if boundaries are available.
- **Simulated relief data:** results are only as credible as the simulator; document assumptions.

## 7. Open data items (as of 2026-10-10)

| Item | Needed by | Status |
|---|---|---|
| Real 2018 impact per district (relief-camp population, deaths, houses damaged; e.g. Kerala PDNA 2018) | Step 2 results (GAT validation) | Not collected; using severity derived from flood exposure until then |
| IMD daily district rainfall, Aug 2018 | Optional, any time | Not collected |
| Real OSM road distances | Before final demo | Deferred; straight-line × 1.35 estimate in `data/simulated/road_edges.csv`. Plan: offline reader for the local `.osm.pbf` |
