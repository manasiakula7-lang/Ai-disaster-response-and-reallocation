# Step 6: dynamic reallocation loop

The deck's loop is: *new report or road closure → update demand / stock / roads → agents recompute → new plan and alerts.* This step builds that loop and measures what it's worth.

```
python -m ml.realloc.loop        # ~5 min
```

## How it works (`loop.py`)

The 7-day flood week (18-24 Aug 2018) is replayed in time order with two kinds of events:

| Event | Source | Effect |
|---|---|---|
| **Reports** | The **real HumAID tweets** from 18-24 Aug that Step 1 marked actionable and placed in a district: 449 tweets, at their real posting time (IST) | Moves the estimate of that district's need for the mentioned resources halfway to the true value ("shelter" counts as food + water) |
| **Road events** | The simulator's 33 closures, slowdowns and reopenings, each at a random time of day | Updates the road map and travel times (shortest paths recomputed) |

Trucks leave in **4 dispatch waves a day** (06:00, 12:00, 18:00, 24:00), each with a quarter of every centre's daily trips. Before each wave the loop applies the new events, re-runs the policy on the remaining need, stock and roads, sends the wave and raises alerts.

At the start of each day the planner only has a **forecast** of demand with ±35% error, plus yesterday's road map. That's what makes updating worthwhile.

**Information modes:**

| Mode | What the planner knows |
|---|---|
| static | Morning forecast and yesterday's roads, all day (a fixed morning plan) |
| roads | Static + road events as they happen |
| reports | Static + tweets as they arrive |
| dynamic | Both: the full loop |
| perfect | True demand and today's roads from 00:00 (upper reference) |

**Policies in the loop:** the Step 4 fair MAPPO agents, and the fairness LP with the rationing rule. Each morning the policy sets the day's stock budget; each wave it decides where to send it.

## Results (average over 50 unseen flood weeks)

| Policy, mode | Fulfilment | Vulnerability-weighted coverage | Worst district | Gini | Delivery time (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| MAPPO, static | 60.5% | 69.7% | 63.2% | 0.026 | 6.2 | 0.9 |
| MAPPO, roads | 60.7% | 70.1% | 64.0% | 0.026 | 6.1 | 0.9 |
| MAPPO, reports | 62.5% | 72.1% | 65.7% | 0.023 | 6.2 | 0.8 |
| **MAPPO, dynamic** | **62.7%** | **72.6%** | **66.7%** | **0.023** | 6.0 | 0.8 |
| MAPPO, perfect | 66.9% | 79.3% | 74.8% | 0.019 | 6.0 | 0.6 |
| LP, static | 63.0% | 75.4% | 45.2% | 0.101 | 5.1 | 1.5 |
| **LP, dynamic** | **64.5%** | 77.4% | 45.0% | 0.104 | 4.9 | 1.6 |
| LP, perfect | 70.4% | 86.4% | 43.1% | 0.105 | 4.6 | 2.0 |

The official week and the roads/reports rows for the LP are in `results/realloc_report.md`.

### What this shows

1. **Replanning helps.** For the MAPPO agents, the loop raises fulfilment from 60.5% to 62.7% and the worst district from 63% to 67%. For the LP, fulfilment rises from 63.0% to 64.5%.
2. **Almost all of the gain comes from the tweets.** Road updates add only 0.2 points, because the simulator has few road events (33 in a week), most of which persist from the day before, so yesterday's map is mostly right.
3. **There's a lot of room left.** Perfect information would add another 4-6 points. The tweets close about a third of that gap for MAPPO and a fifth for the LP. Only 14% of tweets name a district (Step 1), and they cluster in Ernakulam and Alappuzha. Districts nobody tweets about stay at the forecast.
4. **The policies keep their character inside the loop.** The LP meets more demand in total; MAPPO is much fairer (worst district 67% vs 45%, Gini 0.023 vs 0.104). Note the LP's worst district gets *worse* with perfect information (43%): it uses better information to maximise the total, not to help the worst-off.
5. Numbers are lower than in Step 4 because the planner now works from a ±35% forecast and 4 smaller waves instead of knowing each day's demand.

## Outputs for the dashboard (Step 8)

From the official week, MAPPO, dynamic mode:

- `results/event_log.csv`: every event in time order: day, time, type (`report`, `road_blocked`, `road_slowed`, `road_open`, `dispatch`, `alert`), district, detail, tweet id. 449 reports, 33 road events, 28 dispatches, 14 alerts. Alerts are raised for a reported need ≥30% above the estimate, a district cut off from every centre, or a severely hit district under 25% covered at day end.
- `results/plans.csv`: every shipment: day, wave, centre, district, resource, amount.

## Limits

- The simulator's roads are a day-level state: a closure at 15:00 also blocks a 06:00 shipment. The same rule applies to every mode.
- The way a report updates the estimate (halfway to the true value) is our assumption. Real reports would need quantities extracted from the text (the optional LLM step in the plan).
- Tweet times are real, but the demand they reveal is the simulator's.
