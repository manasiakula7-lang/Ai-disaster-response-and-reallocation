# Step 2 results: GAT demand and severity model

Task: predict each district's next-day urgency-weighted demand (log1p) from today's graph.
Temporal: train targets 2018-08-18..2018-08-31, val ..2018-09-05, test 2018-09-06..2018-09-12. Spatial: targets of Kottayam, Malappuram, Wayanad, Kollam hidden in training, evaluated on them.
Neural models: mean ± std over 5 seeds. Lower is better.

| Split | Model | MAE | RMSE |
|---|---|---|---|
| temporal | Persistence (tomorrow = today) | 0.040 | 0.086 |
| temporal | MLP (no graph) | 0.053 ± 0.007 | 0.075 ± 0.008 |
| temporal | GCN | 0.055 ± 0.010 | 0.074 ± 0.008 |
| temporal | GAT | 0.053 ± 0.003 | 0.077 ± 0.004 |
| spatial | Persistence (tomorrow = today) | 0.099 | 0.195 |
| spatial | MLP (no graph) | 0.094 ± 0.005 | 0.159 ± 0.005 |
| spatial | GCN | 0.202 ± 0.004 | 0.360 ± 0.017 |
| spatial | GAT | 0.108 ± 0.005 | 0.170 ± 0.004 |

## Severity on 19 Aug 2018 (peak)

| District | Severity | Class |
|---|---|---|
| Alappuzha | 0.601 | high |
| Ernakulam | 0.494 | medium |
| Thrissur | 0.367 | medium |
| Thiruvananthapuram | 0.318 | medium |
| Pathanamthitta | 0.297 | low |
| Kottayam | 0.240 | low |
| Wayanad | 0.225 | low |
| Idukki | 0.203 | low |
| Malappuram | 0.178 | low |
| Kasaragod | 0.171 | low |
| Kozhikode | 0.157 | low |
| Palakkad | 0.151 | low |
| Kannur | 0.151 | low |
| Kollam | 0.119 | low |

## Strongest learned attention (layer 1, training days)

| Edge | Attention |
|---|---|
| Kollam → Thiruvananthapuram | 0.523 |
| Kannur → Kasaragod | 0.517 |
| Malappuram → Palakkad | 0.356 |
| Ernakulam → Idukki | 0.313 |
| Thiruvananthapuram → Kollam | 0.313 |
| Kozhikode → Kannur | 0.310 |
| Kozhikode → Wayanad | 0.296 |
| Thrissur → Palakkad | 0.294 |
