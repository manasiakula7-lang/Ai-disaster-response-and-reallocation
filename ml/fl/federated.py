"""Step 5: federated training of the relief-centre agents with Flower (FedAvg).

In Step 4 all 19 centres pooled their experience into one training batch. Here
each centre keeps its experience to itself:

  1. The server sends the current global actor to every centre.
  2. Each centre (a Flower ClientApp) plays a few flood weeks in the shared
     simulator. It acts with its own local copy of the actor; the other
     centres follow the published global actor. It then runs PPO on **only its
     own decisions** and returns its updated weights, never its data.
  3. The server averages the weights (FedAvg, McMahan et al., 2017), weighted
     by how many decisions each centre trained on.

Reward, network and PPO loss are the same as Step 4 (alpha=0.5, beta=1).

For comparison:
  centralised  the Step 4 model (ml/marl/models/ppo_fair.pt), all data pooled
  independent  each centre trains its own model and never shares anything

Usage: python -m ml.fl.federated            (~40 min on 4 CPU cores)
Outputs: ml/fl/models/*.pt, ml/fl/results/fl_report.md, fl_metrics.csv,
         rounds.csv
"""
import argparse
import copy
import csv
import random
import time

import numpy as np
import torch
from torch import nn

from ml.env.metrics import episode_metrics
from ml.env.relief_env import ROOT
from ml.marl.mappo import Actor, batch, decode
from ml.marl.multi_agent import MultiAgentRelief
from ml.marl.scenarios import ScenarioEnv
from ml.marl.train import COLS, TEST_SEEDS, table

HERE = ROOT / "ml" / "fl"
MODELS, RESULTS = HERE / "models", HERE / "results"
ALPHA, BETA = 0.5, 1.0
N_CENTRES = 19
ROUNDS = 300
LOCAL = dict(weeks=2, repeats=4, epochs=4, opt="sgd", lr=0.2, clip=0.2, ent=1e-3)
TRAIN_SEEDS = (0, 900)


# ------------------------------------------------------------------ helpers
def others_from(actors):
    """Deterministic actions of every centre from a list of actors (or one)."""
    if isinstance(actors, nn.Module):
        return lambda t: actors.dist(t["g"], t["a"]).mean
    def f(t):
        means = {}
        for m in set(actors):
            means[id(m)] = m.dist(t["g"], t["a"]).mean
        return torch.stack([means[id(m)][:, i] for i, m in enumerate(actors)], 1)
    return f


def local_update(local, others, ma, own, rng, cfg=LOCAL):
    """PPO on centre `own`'s decisions only. Returns (examples, mean return)."""
    steps, returns = [], []
    for _ in range(cfg["weeks"]):
        week, group = rng.randrange(*TRAIN_SEEDS), []
        for _ in range(cfg["repeats"]):
            f, done, ep = ma.reset(week), False, []
            while not done:
                t = batch([f])
                with torch.no_grad():
                    u = others(t).clone()
                    dist = local.dist(t["g"], t["a"][:, own:own + 1])
                    mine = dist.sample()
                    u[:, own] = mine[:, 0]
                    release, w = decode(u, t["dr"], t["p"], t["mask"])
                nf, r, done, _ = ma.step(release[0].numpy(), w[0].numpy())
                ep.append(dict(g=t["g"][0], a=t["a"][0, own:own + 1], u=mine[0],
                               logp=dist.log_prob(mine).sum(-1)[0, 0], r=r))
                f = nf
            g = 0.0
            for k in reversed(range(len(ep))):
                g += ep[k]["r"]; ep[k]["ret"] = g
            group.append(ep); returns.append(ep[0]["ret"])
        for k in range(len(group[0])):
            mean_k = np.mean([e[k]["ret"] for e in group])
            for e in group:
                e[k]["adv"] = e[k]["ret"] - mean_k
        steps += [s for e in group for s in e]

    G = torch.stack([s["g"] for s in steps]); A = torch.stack([s["a"] for s in steps])
    U = torch.stack([s["u"] for s in steps]); old = torch.stack([s["logp"] for s in steps])
    adv = torch.tensor([s["adv"] for s in steps], dtype=torch.float32)
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)
    # plain SGD, as in FedAvg: a fresh Adam each round takes full-size steps on
    # noisy gradients and made the averaged model drift
    opt = (torch.optim.SGD if cfg["opt"] == "sgd" else torch.optim.Adam)(local.parameters(), lr=cfg["lr"])
    for _ in range(cfg["epochs"]):
        for idx in torch.randperm(len(steps)).split(16):
            dist = local.dist(G[idx], A[idx])
            ratio = (dist.log_prob(U[idx]).sum(-1) - old[idx][:, None]).clamp(-20, 20).exp()
            a_ = adv[idx][:, None]
            loss = -torch.min(ratio * a_, ratio.clamp(1 - cfg["clip"], 1 + cfg["clip"]) * a_).mean() \
                - cfg["ent"] * dist.entropy().mean()
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(local.parameters(), 0.5)
            opt.step()
    return len(steps), float(np.mean(returns))


@torch.no_grad()
def play(actors, ma, seed=None):
    """One deterministic week where centre i uses actors[i] (or one shared actor)."""
    others = others_from(actors)
    f, done = ma.reset(seed), False
    while not done:
        t = batch([f])
        release, w = decode(others(t), t["dr"], t["p"], t["mask"])
        f, _, done, _ = ma.step(release[0].numpy(), w[0].numpy())
    return episode_metrics(ma.env)


def quick_eval(actors):
    ma = MultiAgentRelief(ScenarioEnv(), ALPHA, BETA)
    m = play(actors, ma, None)
    return {"fulfilment": m["fulfilment"], "gini": m["gini"],
            "worst_district": m["worst_district_fulfilment"]}


# ------------------------------------------------------------------ Flower
def run_flower(rounds=ROUNDS):
    from flwr.app import ArrayRecord, ConfigRecord, Context, Message, MetricRecord, RecordDict
    from flwr.clientapp import ClientApp
    from flwr.serverapp import Grid, ServerApp
    from flwr.serverapp.strategy import FedAvg
    from flwr.simulation import run_simulation

    client = ClientApp()

    @client.train()
    def train(msg: Message, context: Context):
        torch.set_num_threads(1)
        own = int(context.node_config["partition-id"])        # centre index
        rnd = int(msg.content["config"]["server-round"])
        glob = Actor(); glob.load_state_dict(msg.content["arrays"].to_torch_state_dict())
        local = copy.deepcopy(glob)
        ma = MultiAgentRelief(ScenarioEnv(), ALPHA, BETA)
        cfg = {**LOCAL, "opt": msg.content["config"]["opt"], "lr": msg.content["config"]["lr"]}
        n, ret = local_update(local, others_from(glob), ma, own, random.Random(rnd * 100 + own), cfg)
        content = RecordDict({"arrays": ArrayRecord(local.state_dict()),
                              "metrics": MetricRecord({"num-examples": n, "train-return": ret})})
        return Message(content=content, reply_to=msg)

    server = ServerApp()
    history = []

    def evaluate(rnd, arrays):
        if rnd % 10 and rnd != rounds:
            return None
        actor = Actor(); actor.load_state_dict(arrays.to_torch_state_dict())
        m = quick_eval(actor)
        history.append({"round": rnd, **m})
        print(f"  round {rnd:4d}  official week: fulfilment {m['fulfilment']:.3f}  gini {m['gini']:.3f}"
              f"  worst {m['worst_district']:.3f}", flush=True)
        return MetricRecord(m)

    @server.main()
    def main(grid: Grid, context: Context):
        torch.manual_seed(0)
        strategy = FedAvg(fraction_train=1.0, fraction_evaluate=0.0,
                          min_train_nodes=N_CENTRES, min_available_nodes=N_CENTRES)
        result = strategy.start(grid=grid, initial_arrays=ArrayRecord(Actor().state_dict()),
                                num_rounds=rounds, train_config=ConfigRecord({"opt": LOCAL["opt"], "lr": LOCAL["lr"]}),
                                evaluate_fn=evaluate)
        MODELS.mkdir(parents=True, exist_ok=True)
        torch.save(result.arrays.to_torch_state_dict(), MODELS / "fedavg.pt")
        with open(RESULTS / "rounds.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(history[0]))
            w.writeheader(); w.writerows(history)

    RESULTS.mkdir(parents=True, exist_ok=True)
    run_simulation(server_app=server, client_app=client, num_supernodes=N_CENTRES,
                   backend_config={"client_resources": {"num_cpus": 1, "num_gpus": 0.0}})


# ------------------------------------------------------------- no sharing
def _independent_step(args):
    """One centre's local update while everyone else follows their last model."""
    states, i, rnd, cfg = args
    torch.set_num_threads(1)
    frozen = []
    for sd in states:
        m = Actor(); m.load_state_dict(sd); frozen.append(m)
    local = copy.deepcopy(frozen[i])
    ma = MultiAgentRelief(ScenarioEnv(), ALPHA, BETA)
    local_update(local, others_from(frozen), ma, i, random.Random(rnd * 100 + i), cfg)
    return local.state_dict()


def run_independent(rounds=ROUNDS):
    from multiprocessing import Pool
    torch.manual_seed(0)
    states = [Actor().state_dict()] * N_CENTRES                # same starting point
    t0 = time.time()
    with Pool(4) as pool:
        for rnd in range(1, rounds + 1):
            states = pool.map(_independent_step, [(states, i, rnd, LOCAL) for i in range(N_CENTRES)])
            if rnd % 10 == 0:
                actors = []
                for sd in states:
                    m = Actor(); m.load_state_dict(sd); actors.append(m)
                m = quick_eval(actors)
                print(f"  independent round {rnd:4d}  fulfilment {m['fulfilment']:.3f}  gini {m['gini']:.3f}"
                      f"  worst {m['worst_district']:.3f}  ({time.time() - t0:.0f}s)", flush=True)
    MODELS.mkdir(parents=True, exist_ok=True)
    torch.save(states, MODELS / "independent.pt")


# -------------------------------------------------------------- compare
def load_actor(path):
    a = Actor(); a.load_state_dict(torch.load(path)); return a.eval()


def compare():
    env = ScenarioEnv()
    ma = MultiAgentRelief(env, ALPHA, BETA)
    indep = []
    for sd in torch.load(MODELS / "independent.pt"):
        a = Actor(); a.load_state_dict(sd); indep.append(a.eval())
    torch.manual_seed(0)
    models = {
        "Untrained starting policy": Actor().eval(),
        "Centralised MAPPO (Step 4, all data pooled)": load_actor(ROOT / "ml/marl/models/ppo_fair.pt"),
        "Federated MAPPO (Flower FedAvg)": load_actor(MODELS / "fedavg.pt"),
        "Independent centres (no sharing)": indep,
    }
    official, test = {}, {}
    for name, m in models.items():
        official[name] = play(m, ma, None)
        runs = [play(m, ma, s) for s in TEST_SEEDS]
        test[name] = {k: float(np.mean([r[k] for r in runs])) for k, _, _ in COLS}
        print(f"{name:<45} official {official[name]['fulfilment']:.3f} / gini {official[name]['gini']:.3f}"
              f"   test {test[name]['fulfilment']:.3f} / gini {test[name]['gini']:.3f}", flush=True)
    keys = [k for k in next(iter(official.values())) if k != "per_district"]
    with open(RESULTS / "fl_metrics.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["model", "evaluation"] + keys)
        for n in models:
            w.writerow([n, "official"] + [round(official[n][k], 4) for k in keys])
            w.writerow([n, f"mean of {len(TEST_SEEDS)} unseen weeks"] +
                       [round(test[n].get(k, float("nan")), 4) for k in keys])
    (RESULTS / "fl_report.md").write_text(
        "# Step 5: federated vs centralised training (alpha=0.5, beta=1)\n\n"
        "## Official scenario\n\n" + table(official) +
        f"\n\n## Average over {len(TEST_SEEDS)} unseen flood weeks\n\n" + table(test) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["flower", "independent", "compare"])
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    ap.add_argument("--opt", default=LOCAL["opt"]); ap.add_argument("--lr", type=float, default=LOCAL["lr"])
    args = ap.parse_args()
    LOCAL.update(opt=args.opt, lr=args.lr)
    if args.only in (None, "flower"):
        run_flower(args.rounds)
    if args.only in (None, "independent"):
        run_independent(args.rounds)
    if args.only in (None, "compare"):
        compare()


if __name__ == "__main__":
    main()
