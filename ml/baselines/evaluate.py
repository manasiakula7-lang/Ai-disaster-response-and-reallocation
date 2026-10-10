"""Run every baseline through the 7-day scenario and compare.

Usage: python -m ml.baselines.evaluate
Outputs: ml/baselines/results/baseline_report.md, baseline_metrics.csv,
         per_district.csv
"""
import csv
from pathlib import Path

from ml.baselines.policies import ALL
from ml.env.metrics import episode_metrics
from ml.env.relief_env import ROOT, ReliefEnv

RESULTS = ROOT / "ml" / "baselines" / "results"
COLS = [("fulfilment", "Fulfilment", "%"), ("vuln_weighted_fulfilment", "Avg district coverage, vulnerability-weighted", "%"),
        ("worst_district_fulfilment", "Worst district", "%"), ("gini", "Gini (lower = fairer)", "f"),
        ("avg_delay_hr", "Avg delivery time (h)", "f"), ("neglect_district_days", "Neglected district-days", "d")]


def run(policy, env):
    obs, done = env.reset(), False
    while not done:
        obs, _, done, _ = env.step(policy(obs))
    return episode_metrics(env)


def fmt(v, kind):
    return f"{v:.1%}" if kind == "%" else f"{v:.3f}" if kind == "f" else str(v)


def main():
    env = ReliefEnv()
    results = {}
    for cls in ALL:
        p = cls()
        results[p.name] = run(p, env)
        m = results[p.name]
        print(f"{p.name:<32} " + "  ".join(f"{c}={fmt(m[k], t)}" for k, c, t in COLS))

    RESULTS.mkdir(parents=True, exist_ok=True)
    keys = [k for k in next(iter(results.values())) if k != "per_district"]
    with open(RESULTS / "baseline_metrics.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["policy"] + keys)
        for n, m in results.items():
            w.writerow([n] + [round(m[k], 4) for k in keys])
    districts = env.districts
    with open(RESULTS / "per_district.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["policy"] + districts)
        for n, m in results.items():
            w.writerow([n] + [round(m["per_district"].get(d, 1.0), 3) for d in districts])

    head = "| Policy | " + " | ".join(c for _, c, _ in COLS) + " |\n|---|" + "---|" * len(COLS) + "\n"
    body = "\n".join(f"| {n} | " + " | ".join(fmt(m[k], t) for k, _, t in COLS) + " |"
                     for n, m in results.items())
    res = "\n".join(f"| {n} | " + " | ".join(f"{m['fulfil_' + r]:.1%}" for r in
                    ["food_kits", "water_litres", "medicine_kits", "rescue_teams"]) + " |"
                    for n, m in results.items())
    (RESULTS / "baseline_report.md").write_text(
        "# Step 3: baseline allocation results (7-day Kerala scenario)\n\n" + head + body +
        "\n\n## Fulfilment by resource\n\n| Policy | Food | Water | Medicine | Rescue teams |\n|---|---|---|---|---|\n"
        + res + "\n")


if __name__ == "__main__":
    main()
