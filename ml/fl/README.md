# Step 5: federated learning with Flower

In Step 4 all 19 relief centres pooled their experience into one training batch. In a real deployment, centres (run by different districts or agencies) may not be allowed to share their raw records. Federated learning lets them train one shared model without that: **only model weights travel, never the data.**

```
pip install "flwr[simulation]"      # Flower 1.40 + Ray, for the simulation runtime
python -m ml.fl.federated           # ~40 min on 4 CPU cores
python -m ml.fl.federated --only compare   # re-evaluate saved models only
```

## How it works (`federated.py`)

Each centre is a Flower **ClientApp**. The server is a Flower **ServerApp** running the built-in **FedAvg** strategy (McMahan et al., 2017). Flower's simulation runtime runs the 19 clients on one machine.

Each round:
1. The server sends the current global model to all 19 centres.
2. Each centre plays 2 random flood weeks, 4 times each, in the simulator. It acts with its own copy of the model; the other centres follow the global model.
3. The centre runs PPO on **only its own decisions** (56 per round) and sends back its updated weights.
4. The server averages the 19 sets of weights, weighted by number of decisions. That average is the new global model.

300 rounds. Same network, reward (α=0.5, β=1) and PPO loss as Step 4. Locally the centres use plain SGD (lr 0.2), as in the original FedAvg. An earlier run with a fresh Adam optimiser each round made the averaged model drift.

**Comparison models:**

| Model | Who sees what |
|---|---|
| Centralised (Step 4, `ml/marl/models/ppo_fair.pt`) | All centres' data in one place, one shared model |
| Federated (`models/fedavg.pt`) | Each centre keeps its data; one shared model built from averaged weights |
| Independent (`models/independent.pt`) | Each centre trains its own model and shares nothing |

## Results

Average over 50 unseen flood weeks (same test weeks as Step 4):

| Model | Fulfilment | Vulnerability-weighted coverage | Worst district | Gini | Delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| Untrained starting policy | 66.4% | 72.4% | 62.4% | 0.059 | 5.9 | 0.1 |
| Centralised (Step 4) | 66.8% | 79.1% | **74.5%** | **0.019** | 5.7 | 0.5 |
| **Federated (Flower FedAvg)** | 65.8% | 77.8% | 71.8% | 0.025 | 6.4 | 0.2 |
| Independent (no sharing) | **68.2%** | **79.9%** | 71.7% | 0.027 | 5.3 | 0.0 |

The official-week numbers are in `results/fl_report.md`. The federated model's progress every 10 rounds is in `results/rounds.csv`.

### What this shows

1. **Federated learning works here.** Without any centre sharing its data, the federated model gets most of the way to the centralised one. The worst district gets 71.8% of its need (vs 62.4% untrained) and Gini falls from 0.059 to 0.025.
2. **The privacy cost is small:** 1 point of fulfilment, 2.7 points on the worst district and +0.006 Gini compared with pooling all the data.
3. **Independent centres did surprisingly well**, slightly ahead on total fulfilment. Each centre gets a model fitted to its own location and stock, and the centres are very different (Ernakulam vs Wayanad). A single averaged model can't specialise like that. This points to **personalised federated learning** (fine-tune the global model locally for a few steps) as a natural extension.
4. **The comparison flatters "independent" a little.** In our simulation each independent centre can replay the other centres' behaviour exactly while it trains. A real isolated centre would have to guess what the others will do.
5. **Cost:** federated and independent each simulated 45,600 weeks (19 centres × 8 per round × 300 rounds), against 19,200 for centralised. Learning only from your own decisions is less sample-efficient.

### Limits

- Simulation on one machine; no network delays, dropped clients or secure aggregation.
- Weights could still leak some information. Adding differential privacy (Flower has `DifferentialPrivacyClientSideFixedClipping`) would be the next step for a real deployment.
- One training seed per setting.
