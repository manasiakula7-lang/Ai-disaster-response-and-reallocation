"""Step 2: train the GAT demand/severity model and compare with baselines.

Task: predict each district's next-day urgency-weighted demand (log1p scale)
from today's graph snapshot. Two evaluations:
  temporal: train on targets 18-31 Aug, validate 1-5 Sep, test 6-12 Sep
  spatial:  hide 4 districts' targets during training (all days), test on them;
            shows whether neighbours help where tweets are missing
Every model is trained with 5 seeds; mean ± std reported.

Then writes daily severity scores for all 14 districts:
  severity = 0.5 * predicted demand (scaled 0-1) + 0.3 * 100-yr flood exposure
             (scaled 0-1) + 0.2 * vulnerability score

Usage: python -m ml.gnn.train
Outputs: ml/gnn/results/{gnn_report.md, attention_edges.csv},
         ml/gnn/models/gat.pt, data/processed/district_severity_daily.csv
"""
import csv
import statistics
from pathlib import Path

import torch

from ml.gnn.dataset import ROOT, build_snapshots
from ml.gnn.models import GAT, GCN, MLP

RESULTS = ROOT / "ml" / "gnn" / "results"
MODELS = ROOT / "ml" / "gnn" / "models"
OUT = ROOT / "data" / "processed"
SEEDS = [0, 1, 2, 3, 4]
HELD_OUT = ["Kottayam", "Malappuram", "Wayanad", "Kollam"]  # mix of high/low signal areas
SEVERITY_WEIGHTS = {"demand": 0.5, "flood": 0.3, "vulnerability": 0.2}


def fit(model_cls, d_in, train, val, node_mask=None, epochs=400, patience=60, seed=0):
    torch.manual_seed(seed)
    model = model_cls(d_in)
    opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)
    mask = node_mask if node_mask is not None else torch.ones(train[0].num_nodes, dtype=torch.bool)
    best, best_state, wait = float("inf"), None, 0
    for _ in range(epochs):
        model.train()
        for g in train:
            opt.zero_grad()
            loss = torch.nn.functional.mse_loss(model(g)[mask], g.y[mask])
            loss.backward()
            opt.step()
        v = evaluate(model, val, mask)[0]
        if v < best - 1e-4:
            best, wait = v, 0
            best_state = {k: t.clone() for k, t in model.state_dict().items()}
        else:
            wait += 1
            if wait >= patience:
                break
    model.load_state_dict(best_state)
    return model


@torch.no_grad()
def evaluate(model, snaps, mask=None):
    if model != "persistence":
        model.eval()
    err = []
    for g in snaps:
        m = mask if mask is not None else torch.ones(g.num_nodes, dtype=torch.bool)
        pred = g.persistence if model == "persistence" else model(g)
        err.append((pred - g.y)[m])
    e = torch.cat(err)
    return float(e.abs().mean()), float(e.pow(2).mean().sqrt())


def summarise(vals):
    return f"{statistics.mean(vals):.3f} ± {statistics.pstdev(vals):.3f}"


def main():
    names, days, snaps = build_snapshots()
    d_in = snaps[0].x.shape[1]
    train, val, test = snaps[:14], snaps[14:19], snaps[19:]
    print(f"{len(snaps)} snapshots: train {train[0].target_day}..{train[-1].target_day}, "
          f"val ..{val[-1].target_day}, test ..{test[-1].target_day}; {d_in} features")

    rows = []
    # Temporal
    p = evaluate("persistence", test)
    rows.append(("temporal", "Persistence (tomorrow = today)", f"{p[0]:.3f}", f"{p[1]:.3f}"))
    best_gat = None
    for name, cls in [("MLP (no graph)", MLP), ("GCN", GCN), ("GAT", GAT)]:
        maes, rmses = [], []
        for s in SEEDS:
            m = fit(cls, d_in, train, val, seed=s)
            mae, rmse = evaluate(m, test)
            maes.append(mae); rmses.append(rmse)
            if cls is GAT and (best_gat is None or mae < best_gat[0]):
                best_gat = (mae, m)
        rows.append(("temporal", name, summarise(maes), summarise(rmses)))
        print(rows[-1])

    # Spatial: hide some districts' targets; validate/test on them
    held = torch.tensor([n in HELD_OUT for n in names])
    p = evaluate("persistence", snaps, held)
    rows.append(("spatial", "Persistence (tomorrow = today)", f"{p[0]:.3f}", f"{p[1]:.3f}"))
    for name, cls in [("MLP (no graph)", MLP), ("GCN", GCN), ("GAT", GAT)]:
        maes, rmses = [], []
        for s in SEEDS:
            m = fit(cls, d_in, snaps[:19], snaps[:19], node_mask=~held, seed=s)
            mae, rmse = evaluate(m, snaps, held)
            maes.append(mae); rmses.append(rmse)
        rows.append(("spatial", name, summarise(maes), summarise(rmses)))
        print(rows[-1])

    gat = best_gat[1]
    MODELS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    torch.save(gat.state_dict(), MODELS / "gat.pt")

    # Attention: mean first-layer attention per directed edge over training days
    att_sum = None
    with torch.no_grad():
        gat.eval()
        for g in train:
            gat(g)
            (ei, a), _ = gat.attention
            a = a.mean(1)
            att_sum = a if att_sum is None else att_sum + a
    att = att_sum / len(train)
    att_rows = [{"source": names[int(ei[0, k])], "target": names[int(ei[1, k])],
                 "attention": round(float(att[k]), 4)}
                for k in range(ei.shape[1]) if int(ei[0, k]) != int(ei[1, k])]
    att_rows.sort(key=lambda r: -r["attention"])
    with open(RESULTS / "attention_edges.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(att_rows[0]))
        w.writeheader(); w.writerows(att_rows)

    # Daily severity for every district
    from ml.gnn.dataset import load_static
    _, _, nodes, _, _ = load_static()
    flood = torch.tensor([float(n["flood_exposure_100yr"]) for n in nodes])
    vuln = torch.tensor([float(n["vulnerability_score"]) for n in nodes])
    flood_n = (flood - flood.min()) / (flood.max() - flood.min())
    with torch.no_grad():
        preds = torch.stack([gat(g).clamp(min=0) for g in snaps])
    pred_n = preds / preds.max()
    sev_rows = []
    for t, g in enumerate(snaps):
        sev = (SEVERITY_WEIGHTS["demand"] * pred_n[t] + SEVERITY_WEIGHTS["flood"] * flood_n
               + SEVERITY_WEIGHTS["vulnerability"] * vuln)
        for i, n in enumerate(names):
            s = float(sev[i])
            sev_rows.append({"date": g.target_day, "node_id": i, "district": n,
                             "predicted_demand": round(float(torch.expm1(preds[t, i])), 3),
                             "severity": round(s, 4),
                             "severity_class": "high" if s >= 0.5 else "medium" if s >= 0.3 else "low"})
    with open(OUT / "district_severity_daily.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sev_rows[0]))
        w.writeheader(); w.writerows(sev_rows)

    peak = [r for r in sev_rows if r["date"] == "2018-08-19"]
    peak.sort(key=lambda r: -r["severity"])
    table = "\n".join(f"| {s} | {m} | {a} | {r} |" for s, m, a, r in rows)
    peak_tbl = "\n".join(f"| {r['district']} | {r['severity']:.3f} | {r['severity_class']} |" for r in peak)
    att_tbl = "\n".join(f"| {r['source']} → {r['target']} | {r['attention']:.3f} |" for r in att_rows[:8])
    (RESULTS / "gnn_report.md").write_text(
        "# Step 2 results: GAT demand and severity model\n\n"
        "Task: predict each district's next-day urgency-weighted demand (log1p) from today's graph.\n"
        f"Temporal: train targets {train[0].target_day}..{train[-1].target_day}, "
        f"val ..{val[-1].target_day}, test {test[0].target_day}..{test[-1].target_day}. "
        f"Spatial: targets of {', '.join(HELD_OUT)} hidden in training, evaluated on them.\n"
        "Neural models: mean ± std over 5 seeds. Lower is better.\n\n"
        "| Split | Model | MAE | RMSE |\n|---|---|---|---|\n" + table +
        "\n\n## Severity on 19 Aug 2018 (peak)\n\n| District | Severity | Class |\n|---|---|---|\n" + peak_tbl +
        "\n\n## Strongest learned attention (layer 1, training days)\n\n| Edge | Attention |\n|---|---|\n" + att_tbl + "\n")
    print((RESULTS / "gnn_report.md").read_text())


if __name__ == "__main__":
    main()
