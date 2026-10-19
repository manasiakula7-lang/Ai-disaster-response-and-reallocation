"""Export what the trained GAT "sees" for the dashboard's network view.

For every day it writes each district's 16-number GAT embedding (the hidden
layer just before the demand head) and the first-layer attention on every
road link, averaged over the 4 heads. Dates are the day the severity score is
for (the snapshot's target day), matching district_severity_daily.csv.

Usage: python -m ml.gnn.export_embeddings
Output: data/processed/gat_embeddings.csv, data/processed/gat_attention_daily.csv
"""
import csv

import torch
from torch import nn

from ml.gnn.dataset import PROCESSED, build_snapshots
from ml.gnn.models import GAT

MODELS = PROCESSED.parents[1] / "ml" / "gnn" / "models"


def embed(gat, g):
    """GAT forward pass up to (and including) the skip connection; returns hidden h and layer-1 attention."""
    h, (ei, a1) = gat.g1(g.x, g.edge_index, g.edge_attr, return_attention_weights=True)
    h = nn.functional.elu(h)
    h = gat.g2(h, g.edge_index, g.edge_attr)
    return nn.functional.elu(h + gat.skip(g.x)), ei, a1.mean(1)


def main():
    names, _, snaps = build_snapshots()
    gat = GAT(snaps[0].x.shape[1])
    gat.load_state_dict(torch.load(MODELS / "gat.pt"))
    gat.eval()
    emb_rows, att_rows = [], []
    with torch.no_grad():
        for g in snaps:
            h, ei, a = embed(gat, g)
            for i, n in enumerate(names):
                emb_rows.append({"date": g.target_day, "district": n,
                                 **{f"e{k}": round(float(h[i, k]), 4) for k in range(h.shape[1])}})
            for k in range(ei.shape[1]):
                s, t = int(ei[0, k]), int(ei[1, k])
                if s != t:
                    att_rows.append({"date": g.target_day, "source": names[s], "target": names[t],
                                     "attention": round(float(a[k]), 4)})
    for path, data in [(PROCESSED / "gat_embeddings.csv", emb_rows),
                       (PROCESSED / "gat_attention_daily.csv", att_rows)]:
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader(); w.writerows(data)
        print(f"wrote {path} ({len(data)} rows)")


if __name__ == "__main__":
    main()
