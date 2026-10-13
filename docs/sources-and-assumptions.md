# Where the formulas come from

The formulas in the code fall into three groups:

1. **Standard methods**: textbook techniques with a published source.
2. **Based on a real-world standard**: the number comes from a humanitarian or transport guideline.
3. **Our own modelling assumptions**: reasonable values chosen to build the simulation, *not* taken from a source. The report must state these as assumptions, and ideally test how much the results change when they change (sensitivity analysis).

---

## 1. Standard methods (cite these)

| Used in | Formula | Source |
|---|---|---|
| `simulate_relief_data.py` | Haversine distance between two lat/long points | Standard great-circle formula (spherical trigonometry) |
| `train_classifier.py` | TF-IDF word weighting | Salton & Buckley (1988), *Term-weighting approaches in automatic text retrieval*, Information Processing & Management |
| `train_classifier.py` | Logistic regression / softmax, class-balanced weights | Standard ML; scikit-learn implementation (Pedregosa et al., 2011, JMLR) |
| `train_classifier.py` | Precision, recall, F1, macro-F1 | Standard evaluation metrics; macro-F1 is also what the HumAID paper reports (Alam et al., 2021, ICWSM) |
| `extract_reports.py` | Tweet time from tweet ID: `(id >> 22) + 1288834974657` ms | Twitter's "Snowflake" ID format (Twitter Engineering, 2010) |
| `models.py` | GCN layer | Kipf & Welling (2017), *Semi-Supervised Classification with Graph Convolutional Networks*, ICLR |
| `models.py` | GAT attention (score → softmax → weighted sum, multi-head) | Veličković et al. (2018), *Graph Attention Networks*, ICLR. Edge features via PyTorch Geometric (Fey & Lenssen, 2019) |
| `models.py` | ELU activation | Clevert et al. (2016), ICLR |
| `train.py` | Adam optimiser; MSE / MAE / RMSE | Kingma & Ba (2015), ICLR; standard error measures |
| `train.py` | Persistence baseline ("tomorrow = today") | Standard naïve forecasting baseline |
| `relief_env.py` | Shortest route | Dijkstra (1959), via `networkx` |
| `metrics.py` | Gini coefficient for fairness | Standard inequality measure; used for relief fairness by Long, Sun & Xu (2024), deck reference [11] |
| `policies.py` | Linear programming (OR-Tools GLOP) | Standard optimisation; Google OR-Tools |
| `policies.py` | Max-min fairness term (raise the worst-off district) | Standard max-min / Rawlsian fairness formulation |
| `policies.py` | Weighted efficiency + equity objective | Same idea as the efficiency-equity (α:β) weighting in Mogaka (2026), deck reference [4] |

## 2. Based on real-world standards

| Value | Used for | Basis |
|---|---|---|
| **15 L of water per person per day** | water demand | Sphere Handbook (2018) minimum for drinking, cooking and hygiene in emergencies |
| **1 food kit per household of 4** | food demand | Typical relief kits are packed per family; Kerala's average household is about 4 people (Census 2011) |
| **Road distance ≈ straight line × 1.35** | road length | "Circuity" or detour factors for road travel are typically 1.2-1.4 (Ballou, Rahardja & Sakai, 2002, *Transportation Research Part A*) |
| Flood peak on day 3 | severity curve shape | Shaped to match the 2018 timeline: heaviest rain and rescues on 15-18 Aug. HumAID tweets peak on 18 Aug |

## 3. Our own assumptions (state these in the report)

| Assumption | Value | Where | Why this value |
|---|---|---|---|
| Share of people in flooded area who are displaced at peak | 15% | simulator | Plausible order of magnitude (about 1.4 million people were in relief camps in Kerala at the 2018 peak, roughly 4% of the state); tuned so demand is large but not absurd |
| Vulnerability raises displacement | × (1 + vulnerability) | simulator | Vulnerable groups are hit harder, but the exact multiplier is ours |
| Medicine | 1 kit per 50 people per day | simulator | Rough stand-in, not from a standard |
| Rescue teams | 1 per 20,000 displaced, on bad days | simulator | Chosen to make teams scarce |
| Total stock | 70% of the week's demand | simulator | Deliberate scarcity so allocation matters |
| Stock placed by population | – | simulator | Makes supply start in the wrong places |
| Average speed | 35 km/h | simulator | Typical mixed Kerala road speed; to be replaced by OSM data |
| Truck sizes | 1,000 food kits / 25,000 L / 500 medicine kits | simulator | Rough medium-truck and tanker capacities |
| Trips per vehicle per day | 2 | simulator | Assumption |
| Road closure chance | 45% × flood level × day severity; reopen 35%/day | simulator | Assumption: closures follow flooding |
| Urgency base per tweet category | 0.6 / 0.5 / 0.5 / 0.35 / 0.2 / 0.15 / 0.1 / 0 | `needs.py` | Our ranking of how actionable each category is |
| Urgency bonuses | +0.1 per cue word (max 0.3), +0.1 for a phone number | `needs.py` | Our rule; it was *checked* against HumAID labels (AUROC 0.905 for spotting real urgent requests) |
| Keyword lists and place-name list | – | `needs.py`, `gazetteer.py` | Hand-built from flood reporting |
| Severity weights | 0.5 need + 0.3 flood + 0.2 vulnerability | `train.py` | Our weighting; severity classes at 0.5 / 0.3 |
| Fair-LP weight | (1 + vulnerability) × (0.5 + severity) | `policies.py` | Our weighting |
| "Neglected" threshold | severity ≥ 0.3 and coverage < 25% | `metrics.py` | Our definition |

### What to do about group 3

- **In the report:** list them in an "Assumptions" table like this one. Examiners accept assumptions in a simulation, provided they're stated clearly.
- **Sensitivity analysis (recommended):** re-run Step 3 with, say, displacement at 10% / 15% / 20% and stock at 60% / 70% / 80%. Then show that the *ranking* of the strategies stays the same.
- **Replace with real data where possible:** real 2018 relief-camp numbers per district (Kerala PDNA) would replace the 15% displacement guess and the severity weights.
