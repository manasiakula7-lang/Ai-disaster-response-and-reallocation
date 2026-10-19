"""Step 4: train multi-agent PPO with three fairness settings and compare them
against the Step 3 baselines.

Usage: python -m ml.marl.train            (trains 3 models in parallel, ~15 min on 4 CPU cores)
       python -m ml.marl.train --eval     (only re-evaluates saved models)

Training uses randomised flood weeks (seeds 0-899, see scenarios.py).
Evaluation uses the official scenario plus 50 unseen weeks (seeds 1000-1049).

Outputs: ml/marl/models/ppo_*.pt, ml/marl/results/marl_report.md,
         marl_metrics.csv, test_scenarios.csv, per_district.csv, learning_curves.csv
"""
import argparse
import csv
from multiprocessing import Pool

import numpy as np
import torch

from ml.baselines.policies import ALL
from ml.env.metrics import episode_metrics
from ml.env.relief_env import ROOT
from ml.marl.mappo import Actor, run_episode, train
from ml.marl.multi_agent import MultiAgentRelief
from ml.marl.references import LPRationed, hindsight_optimum
from ml.marl.scenarios import ScenarioEnv

HERE = ROOT / "ml" / "marl"
MODELS, RESULTS = HERE / "models", HERE / "results"
CONFIGS = {  # tag: (label, alpha, beta)
    "plain": ("MAPPO, no fairness term (α=0, β=0)", 0.0, 0.0),
    "fair": ("MAPPO + fairness (α=0.5, β=1)", 0.5, 1.0),
    "strong": ("MAPPO + strong fairness (α=1, β=3)", 1.0, 3.0),
}
TEST_SEEDS = range(1000, 1050)
ITERS = 600
COLS = [("fulfilment", "Fulfilment", "%"),
        ("vuln_weighted_fulfilment", "Avg district coverage, vulnerability-weighted", "%"),
        ("worst_district_fulfilment", "Worst district", "%"), ("gini", "Gini (lower = fairer)", "f"),
        ("avg_delay_hr", "Avg delivery time (h)", "f"), ("neglect_district_days", "Neglected district-days", "d")]


def _train(tag):
    torch.set_num_threads(1)
    _, a, b = CONFIGS[tag]
    actor, hist = train(ScenarioEnv(), a, b, iters=ITERS, seed=0, log_every=100)
    MODELS.mkdir(parents=True, exist_ok=True)
    torch.save(actor.state_dict(), MODELS / f"ppo_{tag}.pt")
    return tag, hist


def load(tag):
    actor = Actor()
    actor.load_state_dict(torch.load(MODELS / f"ppo_{tag}.pt"))
    return actor.eval()


def policies(env):
    """name -> function(seed) that plays one week and returns episode metrics."""
    out = {}
    for cls in ALL + [LPRationed]:
        def play(seed, p=cls()):
            obs, done = env.reset(seed), False
            while not done:
                obs, _, done, _ = env.step(p(obs))
            return episode_metrics(env)
        out[cls.name] = play
    for tag, (label, a, b) in CONFIGS.items():
        actor, ma = load(tag), MultiAgentRelief(env, a, b)
        out[label] = lambda seed, actor=actor, ma=ma: episode_metrics(run_episode(actor, ma, seed))
    out["Hindsight optimum (knows the whole week; upper bound)"] = \
        lambda seed: episode_metrics(hindsight_optimum(env, seed))
    return out


def fmt(v, kind):
    return f"{v:.1%}" if kind == "%" else f"{v:.3f}" if kind == "f" else (
        f"{v:.1f}" if isinstance(v, float) and v != int(v) else str(int(v)))


def table(results):
    head = "| Policy | " + " | ".join(c for _, c, _ in COLS) + " |\n|---|" + "---|" * len(COLS) + "\n"
    return head + "\n".join(f"| {n} | " + " | ".join(fmt(m[k], t) for k, _, t in COLS) + " |"
                            for n, m in results.items())


def evaluate():
    env = ScenarioEnv()
    pols = policies(env)
    official, test = {}, {}
    for name, play in pols.items():
        official[name] = play(None)
        runs = [play(s) for s in TEST_SEEDS]
        test[name] = {k: float(np.mean([r[k] for r in runs])) for k, _, _ in COLS}
        test[name]["fulfilment_sd"] = float(np.std([r["fulfilment"] for r in runs]))
        print(f"{name:<55} official {official[name]['fulfilment']:.3f} / gini {official[name]['gini']:.3f}"
              f"   test {test[name]['fulfilment']:.3f} / gini {test[name]['gini']:.3f}", flush=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    keys = [k for k in next(iter(official.values())) if k != "per_district"]
    with open(RESULTS / "marl_metrics.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["policy"] + keys)
        for n, m in official.items():
            w.writerow([n] + [round(m[k], 4) for k in keys])
    with open(RESULTS / "test_scenarios.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["policy"] + [k for k, _, _ in COLS] + ["fulfilment_sd"])
        for n, m in test.items():
            w.writerow([n] + [round(m[k], 4) for k, _, _ in COLS] + [round(m["fulfilment_sd"], 4)])
    with open(RESULTS / "per_district.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["policy"] + env.districts)
        for n, m in official.items():
            w.writerow([n] + [round(m["per_district"].get(d, 1.0), 3) for d in env.districts])
    return official, test


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true")
    args = ap.parse_args()
    if not args.eval:
        with Pool(len(CONFIGS)) as pool:
            hists = dict(pool.map(_train, CONFIGS))
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(RESULTS / "learning_curves.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["iteration"] + list(hists))
            for i in range(ITERS):
                w.writerow([i + 1] + [round(hists[t][i], 4) for t in hists])
    official, test = evaluate()
    (RESULTS / "marl_report.md").write_text(
        "# Step 4: multi-agent PPO vs baselines\n\n"
        "## Official scenario (the Step 3 week)\n\n" + table(official) +
        f"\n\n## Average over {len(TEST_SEEDS)} unseen flood weeks (seeds "
        f"{TEST_SEEDS.start}-{TEST_SEEDS.stop - 1})\n\n" + table(test) + "\n")


if __name__ == "__main__":
    main()
