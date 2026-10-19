# Step 5: federated vs centralised training (alpha=0.5, beta=1)

## Official scenario

| Policy | Fulfilment | Avg district coverage, vulnerability-weighted | Worst district | Gini (lower = fairer) | Avg delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| Untrained starting policy | 63.7% | 69.5% | 58.1% | 0.063 | 6.183 | 0 |
| Centralised MAPPO (Step 4, all data pooled) | 62.3% | 73.6% | 69.7% | 0.020 | 5.880 | 0 |
| Federated MAPPO (Flower FedAvg) | 62.2% | 73.1% | 69.5% | 0.019 | 6.695 | 0 |
| Independent centres (no sharing) | 64.7% | 76.4% | 69.6% | 0.025 | 5.306 | 0 |

## Average over 50 unseen flood weeks

| Policy | Fulfilment | Avg district coverage, vulnerability-weighted | Worst district | Gini (lower = fairer) | Avg delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| Untrained starting policy | 66.4% | 72.4% | 62.4% | 0.059 | 5.910 | 0.1 |
| Centralised MAPPO (Step 4, all data pooled) | 66.8% | 79.1% | 74.5% | 0.019 | 5.731 | 0.5 |
| Federated MAPPO (Flower FedAvg) | 65.8% | 77.8% | 71.8% | 0.025 | 6.359 | 0.2 |
| Independent centres (no sharing) | 68.2% | 79.9% | 71.7% | 0.027 | 5.329 | 0 |
