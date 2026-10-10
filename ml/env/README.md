# Relief allocation simulator (Step 3)

`ReliefEnv` runs the 7-day Kerala flood scenario one day at a time. Each day a policy sends `{(centre_id, district, resource): amount}`; the env enforces the rules below, scores the day and applies the next day's road events.

| Rule | Value |
|---|---|
| Resources | food kits, water (L), medicine kits are used up when delivered; rescue teams are reassigned daily |
| Stock | 19 centres, no resupply: total stock is ~70% of 7-day demand (`data/simulated`) |
| Transport | each centre has `vehicles × 2` truckloads per day; 1 truck = 1,000 food kits, 25,000 L water or 500 medicine kits |
| Roads | shortest open path on the district graph; blocked roads remove edges, slowed roads double travel time; +1 h local delivery |
| Unmet demand | not carried over (each day's need stands alone) |
| Severity | GAT output from Step 2, scenario day 1 = 18 Aug 2018 |

`metrics.py` scores a whole episode: fulfilment (mean over resources of covered/demand), vulnerability-weighted average district coverage, worst district, Gini across districts, average delivery time, and neglected district-days (severity ≥ 0.3 but < 25% covered).
