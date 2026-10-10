# AI-Driven Disaster Response and Resource Allocation

E1CSA313 Design Project-1. Prototype scope: Kerala, 2018 floods (14 districts).

Pipeline: crisis-report NLP (HumAID) → Graph Attention Network on the district/road graph → multi-agent PPO allocation across relief centres → federated training (Flower) → fairness (vulnerability, Gini) → dynamic reallocation → FastAPI + PostGIS + React/Leaflet dashboard.

See [docs/build-plan.md](docs/build-plan.md) for the step-by-step plan.

## Layout

```
data/raw/         original downloads (large files git-ignored)
data/processed/   cleaned, model-ready CSVs
scripts/          data collection and preprocessing
ml/               nlp, gnn, marl, fl, fairness
backend/          FastAPI service
frontend/         React + Leaflet dashboard
notebooks/        exploration
docs/             plan and design notes
```
