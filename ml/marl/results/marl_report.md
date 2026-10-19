# Step 4: multi-agent PPO vs baselines

## Official scenario (the Step 3 week)

| Policy | Fulfilment | Avg district coverage, vulnerability-weighted | Worst district | Gini (lower = fairer) | Avg delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| Local-first (nearest centre) | 63.0% | 75.8% | 38.3% | 0.123 | 2.156 | 2 |
| Greedy by severity | 64.4% | 51.5% | 12.0% | 0.265 | 6.407 | 0 |
| LP: max coverage (OR-Tools) | 67.8% | 68.5% | 50.9% | 0.062 | 2.322 | 2 |
| LP: fairness-aware (OR-Tools) | 67.8% | 73.0% | 48.1% | 0.080 | 3.815 | 2 |
| LP fair + rationing rule | 67.7% | 80.3% | 55.3% | 0.101 | 3.166 | 0 |
| MAPPO, no fairness term (α=0, β=0) | 63.6% | 76.6% | 66.5% | 0.048 | 4.198 | 0 |
| MAPPO + fairness (α=0.5, β=1) | 62.3% | 73.6% | 69.7% | 0.020 | 5.880 | 0 |
| MAPPO + strong fairness (α=1, β=3) | 62.1% | 73.2% | 70.1% | 0.018 | 6.325 | 0 |
| Hindsight optimum (knows the whole week; upper bound) | 68.4% | 86.9% | 36.9% | 0.111 | 1.421 | 4 |

## Average over 50 unseen flood weeks (seeds 1000-1049)

| Policy | Fulfilment | Avg district coverage, vulnerability-weighted | Worst district | Gini (lower = fairer) | Avg delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| Local-first (nearest centre) | 66.2% | 75.9% | 48.4% | 0.108 | 2.636 | 2.1 |
| Greedy by severity | 67.4% | 56.7% | 27.9% | 0.204 | 6.386 | 0.0 |
| LP: max coverage (OR-Tools) | 70.3% | 70.1% | 56.1% | 0.060 | 2.635 | 1.6 |
| LP: fairness-aware (OR-Tools) | 70.2% | 75.9% | 56.7% | 0.069 | 3.495 | 1.7 |
| LP fair + rationing rule | 70.1% | 81.4% | 61.1% | 0.088 | 3.244 | 0.2 |
| MAPPO, no fairness term (α=0, β=0) | 67.0% | 80.4% | 70.4% | 0.043 | 4.194 | 1.1 |
| MAPPO + fairness (α=0.5, β=1) | 66.8% | 79.1% | 74.5% | 0.019 | 5.731 | 0.5 |
| MAPPO + strong fairness (α=1, β=3) | 66.5% | 78.5% | 74.6% | 0.017 | 6.118 | 0.4 |
| Hindsight optimum (knows the whole week; upper bound) | 71.0% | 88.2% | 43.3% | 0.094 | 1.551 | 1.7 |
