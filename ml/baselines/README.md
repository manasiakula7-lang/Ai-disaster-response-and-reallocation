# Step 3 baselines

```
python -m ml.baselines.evaluate
```

| Policy | Idea |
|---|---|
| Local-first | each centre serves its own district, then the nearest ones (status quo) |
| Greedy by severity | most severe districts first, each filled from the nearest centres |
| LP: max coverage | OR-Tools (GLOP) linear program each day: maximise total coverage, small travel-time penalty |
| LP: fairness-aware | same LP, plus per-district coverage weighted by (1 + vulnerability) × (0.5 + severity) and a max-min term |

## Results (7-day scenario)

| Policy | Fulfilment | Avg district coverage, vuln.-weighted | Worst district | Gini | Avg delivery (h) | Neglected district-days |
|---|---|---|---|---|---|---|
| Local-first | 63.0% | 75.8% | 38.3% | 0.123 | 2.2 | 2 |
| Greedy by severity | 64.4% | 51.5% | 12.0% | 0.265 | 6.4 | 0 |
| LP: max coverage | 67.8% | 68.5% | 50.9% | 0.062 | 2.3 | 2 |
| LP: fairness-aware | 67.8% | 73.0% | 48.1% | 0.080 | 3.8 | 2 |

Daily coverage (mean over resources):

| Policy | D1 | D2 | D3 | D4 | D5 | D6 | D7 |
|---|---|---|---|---|---|---|---|
| Local-first | 1.00 | 0.74 | 0.51 | 0.51 | 0.71 | 0.59 | 0.58 |
| Greedy by severity | 1.00 | 0.82 | 0.57 | 0.53 | 0.64 | 0.49 | 0.56 |
| LP: max coverage | 1.00 | 0.89 | 0.75 | 0.68 | 0.50 | 0.27 | 0.25 |
| LP: fairness-aware | 1.00 | 0.87 | 0.69 | 0.73 | 0.55 | 0.26 | 0.25 |

Takeaways:
- The LPs deliver the most in total and are the most even across districts (lowest Gini), but they plan one day at a time. They use up stock by day 5, and coverage collapses to 25% on days 6-7.
- Greedy by severity pours everything into the top districts. It covers the worst-hit areas but leaves one district at 12% and has the longest delivery times.
- Local-first is fast and does well on vulnerability-weighted coverage, because stock was placed by population. It reacts badly to road closures.
- **What the RL agents (Step 4) have to beat:** 67.8% fulfilment and a 0.062 Gini, while not running out of stock before the week ends.
