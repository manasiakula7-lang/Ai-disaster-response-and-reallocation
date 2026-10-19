# Step 4: multi-agent PPO with a fairness reward

Each of the 19 relief centres is an agent. Every day each centre decides how much of its stock to use and how to split it across the districts it can reach. All centres share one neural network (parameter sharing) and one team reward, trained with PPO.

```
python -m ml.marl.train          # trains 3 models in parallel (~15 min on 4 CPU cores), then evaluates
python -m ml.marl.train --eval   # re-evaluates the saved models only
```

## Files

| File | What it does |
|---|---|
| `scenarios.py` | `ScenarioEnv`: the Step 3 simulator plus randomised flood weeks (peak day 2-4, different peak height and recession, ±15% demand noise, stock 60-80% of demand). Gives every policy a forecast of the rest of the week's demand with ±15% error. `seed=None` is the official Step 3 week. |
| `multi_agent.py` | `MultiAgentRelief`: turns the simulator into 19 agents. Builds each centre's observation, turns actions into shipments, computes the reward. |
| `mappo.py` | The actor network, PPO training loop and `run_episode`. |
| `references.py` | Two non-learned reference points: an LP with a hand-written rationing rule, and the hindsight optimum (an upper bound). |
| `train.py` | Trains the three fairness settings and writes the comparison. |
| `models/ppo_*.pt` | Trained actors. |
| `results/` | `marl_report.md` (tables below), `marl_metrics.csv`, `test_scenarios.csv`, `per_district.csv`, `learning_curves.csv`. |

## How an agent decides

Each day a centre sees: the day and days left; total stock compared with today's demand and with the forecast for the rest of the week; trucks compared with what's needed; its own stock and trucks; and for every district the demand, GAT severity (Step 2), vulnerability, travel time from this centre and whether the road is open.

From that, the network outputs 9 numbers:

- **3 release fractions** (food, water, medicine): how much of its stock to use today. This is how the agents learn to **ration** stock across the week, which the Step 3 optimisers don't do.
- **6 allocation knobs**: weights in the rule
  `score(district) = k1·log(need share) − k2·travel time − k3·closeness rank + k4·severity + k5·vulnerability + k6·(few centres can reach it)`.
  A softmax over reachable districts turns the scores into shares of today's release. The network can set different knobs for each centre and each day.

Rescue teams are not used up, so they are always fully deployed.

**Dispatch:** shipments leave nearest-first, and no district receives more than it still needs that day (a shared "needs board"). Anything not needed stays in stock. If a centre's plan needs more truckloads than it has, the plan is scaled down.

## Reward

Every agent gets the same reward each day:

```
reward = coverage + α · vulnerability-weighted coverage − β · Gini − 0.05 · delivery hours / 10
```

`coverage` is the simulator's daily score. The other terms use each district's coverage ratio that day. α and β set the efficiency-equity trade-off; we trained three settings: (0, 0), (0.5, 1) and (1, 3).

## Training

- PPO with clipped ratio (Schulman et al., 2017), one ratio per agent, shared parameters and team reward as in MAPPO (Yu et al., 2022).
- 600 iterations. Each iteration plays 8 random flood weeks, each 4 times, so 32 weeks (≈ 19,000 weeks in total). Training weeks use seeds 0-899.
- **Baseline for the advantage:** the mean return of the 4 plays of the same week (a group baseline, as in GRPO, Shao et al., 2024). We also implemented a centralised critic (`baseline="critic"`). In a 150-iteration test it learned more slowly (return 6.81 vs 7.46).
- **Starting point:** untrained agents follow "release half, send by need, nearest first" (63.7% fulfilment on the official week). PPO improves from there.
- **What didn't work first:** letting the network output a separate random score for every district (59 numbers per centre) learned too slowly (57% fulfilment after 300 iterations). Cutting the action to 9 numbers per centre fixed it.

## Results

Two evaluations: the official Step 3 week, and the average over **50 unseen flood weeks** (seeds 1000-1049, never used in training).

### Official scenario

| Policy | Fulfilment | Vulnerability-weighted coverage | Worst district | Gini | Delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| Local-first | 63.0% | 75.8% | 38.3% | 0.123 | 2.2 | 2 |
| Greedy by severity | 64.4% | 51.5% | 12.0% | 0.265 | 6.4 | 0 |
| LP: max coverage | 67.8% | 68.5% | 50.9% | 0.062 | 2.3 | 2 |
| LP: fairness-aware | 67.8% | 73.0% | 48.1% | 0.080 | 3.8 | 2 |
| LP fair + rationing rule | 67.7% | 80.3% | 55.3% | 0.101 | 3.2 | 0 |
| **MAPPO, no fairness (α=0, β=0)** | 63.6% | 76.6% | 66.5% | 0.048 | 4.2 | 0 |
| **MAPPO + fairness (α=0.5, β=1)** | 62.3% | 73.6% | 69.7% | 0.020 | 5.9 | 0 |
| **MAPPO + strong fairness (α=1, β=3)** | 62.1% | 73.2% | **70.1%** | **0.018** | 6.3 | 0 |
| Hindsight optimum (upper bound) | 68.4% | 86.9% | 36.9% | 0.111 | 1.4 | 4 |

### Average over 50 unseen flood weeks

| Policy | Fulfilment | Vulnerability-weighted coverage | Worst district | Gini | Delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| Local-first | 66.2% | 75.9% | 48.4% | 0.108 | 2.6 | 2.1 |
| Greedy by severity | 67.4% | 56.7% | 27.9% | 0.204 | 6.4 | 0.0 |
| LP: max coverage | 70.3% | 70.1% | 56.1% | 0.060 | 2.6 | 1.6 |
| LP: fairness-aware | 70.2% | 75.9% | 56.7% | 0.069 | 3.5 | 1.7 |
| LP fair + rationing rule | 70.1% | 81.4% | 61.1% | 0.088 | 3.2 | 0.2 |
| **MAPPO, no fairness** | 67.0% | 80.4% | 70.4% | 0.043 | 4.2 | 1.1 |
| **MAPPO + fairness** | 66.8% | 79.1% | 74.5% | 0.019 | 5.7 | 0.5 |
| **MAPPO + strong fairness** | 66.5% | 78.5% | **74.6%** | **0.017** | 6.1 | 0.4 |
| Hindsight optimum (upper bound) | 71.0% | 88.2% | 43.3% | 0.094 | 1.6 | 1.7 |

### What this shows

1. **Total fulfilment has almost no room to improve.** Even the hindsight optimum, which knows the whole week in advance, meets only 68.4% (official week). Stock is 70% of demand, so the Step 3 LP (67.8%) is already within 0.6 points of the ceiling. "Beat 67.8%" isn't a realistic target for any policy.
2. **Where MAPPO wins is fairness.** The worst-off district gets 70-75% of its need, against 56% for the best LP. Gini falls from 0.060 to 0.017-0.019. That's about 3.5× more even.
3. **The cost:** about 3.5 points of total fulfilment and longer deliveries (4-6 h against 2.6 h), because the agents send more stock to remote districts.
4. **The fairness term does what it should.** Going from α=β=0 to strong fairness lowers Gini (0.043 → 0.017) and raises the worst district (70.4% → 74.6%), with a small fulfilment loss (67.0% → 66.5%). This is the efficiency-equity trade-off from the deck.
5. **Rationing matters.** Adding a simple rationing rule to the LP removes almost all neglected district-days (1.7 → 0.2). The agents learned rationing on their own.
6. Results on unseen weeks match the official week, so the agents generalise rather than memorising one scenario.

### Limits

- Same simulator assumptions as Step 3 (see `docs/sources-and-assumptions.md`).
- One training seed per setting. Repeating with more seeds would give error bars.
- The water fulfilment of the agents (51-53%) is lower than the LP's (58%). Water is the most truck-heavy resource, and the agents don't plan trucks as tightly as the LP does.
