"""Shared-parameter multi-agent PPO (MAPPO-style) for the relief centres.

All 19 centres use the same actor network (parameter sharing) but each feeds
in its own observation, so they act differently. Execution is decentralised:
each centre only needs its own stock plus the shared demand picture.

Actor (per centre, per day)
  encoder  [global + own features] -> 64-d embedding -> mean of 9 Gaussians
  release  3 of them -> sigmoid = fraction of stock to use today
           (food, water, medicine)
  knobs    6 of them weight the allocation rule
             score(district, resource) = sum_k knob_k * feature_k
           features: need share (log), travel time, closeness rank, severity,
           vulnerability, how few centres can reach the district.
           Softmax of the scores over reachable districts = shares.
  Untrained agents start at "by need, nearest first, release half".

Training: PPO with clipped ratio per agent and a shared team reward
(Schulman et al., 2017; MAPPO set-up of Yu et al., 2022). Each flood week is
played 4 times; the advantage of a day's action is the return from that day
on minus the mean of the 4 plays (a group baseline, as in GRPO, Shao et al.,
2024). A centralised critic is also implemented (baseline="critic"); on this
problem it learned more slowly, see README.
"""
import random
import time

import numpy as np
import torch
from torch import nn

from ml.marl.multi_agent import A_DIM, G_DIM, NC, MultiAgentRelief

HID = 64


def mlp(*sizes):
    layers = []
    for i in range(len(sizes) - 1):
        layers += [nn.Linear(sizes[i], sizes[i + 1]), nn.Tanh()]
    return nn.Sequential(*layers[:-1])


# Each centre's allocation rule: score(district, resource) = knobs . features,
# then a softmax over reachable districts. Features (per centre, district, resource):
KNOBS = ["need share (log)", "travel time", "closeness rank", "severity", "vulnerability",
         "few centres can reach it"]
PRIOR = [1.0, 0.5, 2.0, 0.0, 0.0, 0.0]   # untrained agents: by need, nearest first


def knob_features(dr, p):
    """B x D x R x DR and B x C x D x R x P -> B x C x D x R x len(KNOBS)."""
    C = p.shape[1]
    d = dr[:, None].expand(-1, C, -1, -1, -1)
    return torch.stack([torch.log(d[..., 0] + 1e-3), -p[..., 1], -p[..., 3],
                        d[..., 2], d[..., 3], 1 - p[..., 4]], -1)


class Actor(nn.Module):
    """Per centre: 3 release fractions + len(KNOBS) allocation knobs (Gaussian)."""
    def __init__(self):
        super().__init__()
        self.enc = nn.Sequential(mlp(G_DIM + A_DIM, HID, HID), nn.Tanh())
        self.head = nn.Linear(HID, NC + len(KNOBS))
        nn.init.zeros_(self.head.weight)
        with torch.no_grad():
            self.head.bias.copy_(torch.tensor([0.0] * NC + PRIOR))
        self.log_std = nn.Parameter(torch.tensor([np.log(0.5)] * NC + [np.log(0.3)] * len(KNOBS),
                                                 dtype=torch.float32))

    def forward(self, g, a):
        B, C = a.shape[:2]
        return self.head(self.enc(torch.cat([g[:, None].expand(B, C, -1), a], -1)))  # B x C x K

    def dist(self, g, a):
        return torch.distributions.Normal(self(g, a), self.log_std.exp())


def decode(u, dr, p, mask):
    """Action vector -> release fractions (B x C x NC) and shares (B x C x D x R)."""
    release = torch.sigmoid(u[..., :NC])
    score = (knob_features(dr, p) * u[..., None, None, NC:]).sum(-1)
    score = score.masked_fill(~mask, -1e9)
    return release, torch.softmax(score, dim=-2) * mask


def batch(feats, keys=("g", "a", "dr", "p", "mask", "critic")):
    return {k: torch.as_tensor(np.stack([f[k] for f in feats])) for k in keys}


@torch.no_grad()
def act(actor, f, deterministic=False):
    t = batch([f])
    dist = actor.dist(t["g"], t["a"])
    u = dist.mean if deterministic else dist.sample()
    release, w = decode(u, t["dr"], t["p"], t["mask"])
    return release[0].numpy(), w[0].numpy(), u[0], dist.log_prob(u).sum(-1)[0]


def run_episode(actor, ma, seed=None, deterministic=True):
    f, done = ma.reset(seed), False
    while not done:
        release, w, *_ = act(actor, f, deterministic)
        f, _, done, _ = ma.step(release, w)
    return ma.env


def train(env, alpha, beta, delta=0.05, iters=250, weeks=8, repeats=4, epochs=4, lr=1e-3,
          gamma=1.0, clip=0.2, ent=1e-3, seed=0, log_every=25, train_seeds=(0, 900),
          baseline="group"):
    """Each iteration plays `weeks` random flood weeks, each `repeats` times.

    Advantage of a day's action = return from that day to the end of the week
    minus a baseline:
      "critic" centralised critic V(state) (MAPPO)
      "group"  mean return of the other plays of the same week and day
      "both"   average of the two
    """
    torch.manual_seed(seed); np.random.seed(seed)
    rng = random.Random(seed)
    ma = MultiAgentRelief(env, alpha, beta, delta)
    actor = Actor()
    critic = mlp(len(ma.reset(None)["critic"]), 128, 128, 1)
    opt = torch.optim.Adam(actor.parameters(), lr=lr)
    copt = torch.optim.Adam(critic.parameters(), lr=1e-3)
    history, t0 = [], time.time()
    for it in range(iters):
        steps, ep_returns = [], []
        for _ in range(weeks):
            week_seed, group = rng.randrange(*train_seeds), []
            for _ in range(repeats):
                f, done, ep = ma.reset(week_seed), False, []
                while not done:
                    release, w, u, logp = act(actor, f)
                    nf, r, done, _ = ma.step(release, w)
                    ep.append(dict(f=f, u=u, logp=logp, r=r))
                    f = nf
                g = 0.0
                for k in reversed(range(len(ep))):
                    g = ep[k]["r"] + gamma * g
                    ep[k]["ret"] = g
                group.append(ep)
                ep_returns.append(ep[0]["ret"])
            for k in range(len(group[0])):
                mean_k = np.mean([ep[k]["ret"] for ep in group])
                for ep in group:
                    ep[k]["group"] = mean_k
            for ep in group:
                steps += ep

        b = batch([s["f"] for s in steps])
        u = torch.stack([s["u"] for s in steps])
        old = torch.stack([s["logp"] for s in steps])
        ret = torch.tensor([s["ret"] for s in steps], dtype=torch.float32)
        with torch.no_grad():
            v = critic(b["critic"]).squeeze(-1)
        grp = torch.tensor([s["group"] for s in steps], dtype=torch.float32)
        base = {"critic": v, "group": grp, "both": (v + grp) / 2}[baseline]
        adv = ret - base
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        n = len(steps)
        for _ in range(epochs):
            for idx in torch.randperm(n).split(64):
                dist = actor.dist(b["g"][idx], b["a"][idx])
                logp = dist.log_prob(u[idx]).sum(-1)                         # per agent
                ratio = (logp - old[idx]).clamp(-20, 20).exp()
                A = adv[idx][:, None]
                pi_loss = -torch.min(ratio * A, ratio.clamp(1 - clip, 1 + clip) * A).mean()
                loss = pi_loss - ent * dist.entropy().mean()
                opt.zero_grad(); loss.backward()
                nn.utils.clip_grad_norm_(actor.parameters(), 0.5)
                opt.step()
                v_loss = (critic(b["critic"][idx]).squeeze(-1) - ret[idx]).pow(2).mean()
                copt.zero_grad(); v_loss.backward(); copt.step()
        history.append(float(np.mean(ep_returns)))
        if log_every and (it + 1) % log_every == 0:
            print(f"  iter {it + 1:4d}  mean return {np.mean(history[-log_every:]):.3f}"
                  f"  ({time.time() - t0:.0f}s)", flush=True)
    return actor, history
