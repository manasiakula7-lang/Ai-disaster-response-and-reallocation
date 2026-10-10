# Step 2: GAT demand and severity model

```
python -m ml.gnn.train
```

| File | What it does |
|---|---|
| `dataset.py` | One graph per day, 17 Aug - 12 Sep 2018: 14 district nodes, 21 adjacency edges (both directions, travel time as edge feature), 19 node features (9 static: population, rural share, vulnerability, 6 flood exposures; 10 dynamic: NLP report counts, urgency and per-resource need for the day, 2-day trailing urgency, statewide urgency). Target: next-day urgency-weighted demand (log1p). |
| `models.py` | GAT (2 layers, 4 heads, edge features, skip connection; keeps attention weights), plus MLP and GCN baselines. |
| `train.py` | Temporal and spatial evaluation against baselines (5 seeds each), saves the best GAT, attention per edge, and daily severity scores. |

## Outputs

- `data/processed/district_severity_daily.csv`: per day and district: predicted demand, severity (0-1) and class (high ≥ 0.5, medium ≥ 0.3, low). Severity = 0.5 × predicted demand + 0.3 × 100-yr flood exposure + 0.2 × vulnerability (all scaled 0-1). This feeds the allocation model (Step 3).
- `results/gnn_report.md`: full results table, peak-day severity and attention.
- `results/attention_edges.csv`: average learned attention per directed edge.
- `models/gat.pt`: trained weights.

## Results

See `results/gnn_report.md`. In short: on this data the GAT does **not** beat simple baselines. Persistence ("tomorrow = today") has the lowest temporal MAE, and the MLP (no graph) is slightly better than the GAT when districts are hidden.

Why, and what would change it:
- **Too little data.** 14 nodes × 26 days, and only 14% of tweets are located, so most node-days are zero. The test period (6-12 Sep) is almost silent.
- **No real target.** The target is tweet volume, a noisy proxy for need. Real district impact figures (relief-camp population, deaths, houses damaged from the Kerala PDNA 2018) would give a meaningful target. This is the open data item in the plan.
- **Coarse graph.** Taluk-level nodes (~78) would give the attention layers more structure to learn from.

Severity ranks Alappuzha, Ernakulam and Thrissur highest on the peak day, which matches 2018 reports. It under-ranks Pathanamthitta and Idukki, which were badly hit by river flooding and landslides that the flood-exposure rasters and tweet volume don't capture well. Real impact data would fix this too.
