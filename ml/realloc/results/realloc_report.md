# Step 6: dynamic reallocation loop

## Official scenario

| Policy | Fulfilment | Avg district coverage, vulnerability-weighted | Worst district | Gini (lower = fairer) | Avg delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| MAPPO (fair), static | 56.2% | 65.6% | 54.0% | 0.034 | 6.264 | 1 |
| MAPPO (fair), roads | 56.5% | 66.1% | 53.7% | 0.035 | 6.067 | 1 |
| MAPPO (fair), reports | 58.0% | 67.4% | 58.3% | 0.028 | 6.250 | 1 |
| MAPPO (fair), dynamic | 58.3% | 67.8% | 58.0% | 0.029 | 6.084 | 1 |
| MAPPO (fair), perfect | 62.4% | 74.2% | 68.9% | 0.025 | 6.047 | 0 |
| LP fair + rationing, static | 60.6% | 75.9% | 41.3% | 0.123 | 4.822 | 2 |
| LP fair + rationing, roads | 60.6% | 75.9% | 41.0% | 0.124 | 4.813 | 2 |
| LP fair + rationing, reports | 61.9% | 77.8% | 42.2% | 0.121 | 4.806 | 2 |
| LP fair + rationing, dynamic | 62.0% | 78.0% | 41.5% | 0.122 | 4.929 | 2 |
| LP fair + rationing, perfect | 68.0% | 86.6% | 32.7% | 0.118 | 4.407 | 4 |

## Average over 50 unseen flood weeks

| Policy | Fulfilment | Avg district coverage, vulnerability-weighted | Worst district | Gini (lower = fairer) | Avg delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| MAPPO (fair), static | 60.5% | 69.7% | 63.2% | 0.026 | 6.232 | 0.9 |
| MAPPO (fair), roads | 60.7% | 70.1% | 64.0% | 0.026 | 6.075 | 0.9 |
| MAPPO (fair), reports | 62.5% | 72.1% | 65.7% | 0.023 | 6.163 | 0.8 |
| MAPPO (fair), dynamic | 62.7% | 72.6% | 66.7% | 0.023 | 6.011 | 0.8 |
| MAPPO (fair), perfect | 66.9% | 79.3% | 74.8% | 0.019 | 5.971 | 0.6 |
| LP fair + rationing, static | 63.0% | 75.4% | 45.2% | 0.101 | 5.089 | 1.5 |
| LP fair + rationing, roads | 63.0% | 75.4% | 45.1% | 0.103 | 5.075 | 1.6 |
| LP fair + rationing, reports | 64.5% | 77.3% | 45.2% | 0.102 | 4.863 | 1.5 |
| LP fair + rationing, dynamic | 64.5% | 77.4% | 45.0% | 0.104 | 4.870 | 1.6 |
| LP fair + rationing, perfect | 70.4% | 86.4% | 43.1% | 0.105 | 4.623 | 2.0 |

## Event log (official week, MAPPO, dynamic)

- alert: 14
- dispatch: 28
- report: 449
- road_blocked: 10
- road_open: 6
- road_slowed: 17
