# Step 3: baseline allocation results (7-day Kerala scenario)

| Policy | Fulfilment | Avg district coverage, vulnerability-weighted | Worst district | Gini (lower = fairer) | Avg delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| Local-first (nearest centre) | 63.0% | 75.8% | 38.3% | 0.123 | 2.156 | 2 |
| Greedy by severity | 64.4% | 51.5% | 12.0% | 0.265 | 6.407 | 0 |
| LP: max coverage (OR-Tools) | 67.8% | 68.5% | 50.9% | 0.062 | 2.322 | 2 |
| LP: fairness-aware (OR-Tools) | 67.8% | 73.0% | 48.1% | 0.080 | 3.815 | 2 |

## Fulfilment by resource

| Policy | Food | Water | Medicine | Rescue teams |
|---|---|---|---|---|
| Local-first (nearest centre) | 65.0% | 60.9% | 49.5% | 76.5% |
| Greedy by severity | 61.4% | 61.6% | 58.0% | 76.5% |
| LP: max coverage (OR-Tools) | 65.9% | 58.5% | 70.3% | 76.5% |
| LP: fairness-aware (OR-Tools) | 65.9% | 58.4% | 70.3% | 76.5% |
