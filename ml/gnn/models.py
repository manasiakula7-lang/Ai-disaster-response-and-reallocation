import torch
from torch import nn
from torch_geometric.nn import GATConv, GCNConv


class MLP(nn.Module):
    """No graph: each district on its own."""
    def __init__(self, d_in, hidden=32, dropout=0.3):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d_in, hidden), nn.ELU(), nn.Dropout(dropout),
                                 nn.Linear(hidden, hidden), nn.ELU(), nn.Linear(hidden, 1))

    def forward(self, data):
        return self.net(data.x).squeeze(-1)


class GCN(nn.Module):
    def __init__(self, d_in, hidden=32, dropout=0.3):
        super().__init__()
        self.c1, self.c2 = GCNConv(d_in, hidden), GCNConv(hidden, hidden)
        self.out, self.dropout = nn.Linear(hidden, 1), dropout

    def forward(self, data):
        h = nn.functional.elu(self.c1(data.x, data.edge_index))
        h = nn.functional.dropout(h, self.dropout, self.training)
        h = nn.functional.elu(self.c2(h, data.edge_index))
        return self.out(h).squeeze(-1)


class GAT(nn.Module):
    """Two GAT layers with travel time as an edge feature; keeps attention weights."""
    def __init__(self, d_in, hidden=16, heads=4, dropout=0.3):
        super().__init__()
        self.g1 = GATConv(d_in, hidden, heads=heads, edge_dim=1, dropout=dropout)
        self.g2 = GATConv(hidden * heads, hidden, heads=1, edge_dim=1, dropout=dropout)
        self.skip = nn.Linear(d_in, hidden)
        self.out, self.dropout = nn.Linear(hidden, 1), dropout
        self.attention = None

    def forward(self, data):
        h, a1 = self.g1(data.x, data.edge_index, data.edge_attr, return_attention_weights=True)
        h = nn.functional.dropout(nn.functional.elu(h), self.dropout, self.training)
        h, a2 = self.g2(h, data.edge_index, data.edge_attr, return_attention_weights=True)
        self.attention = (a1, a2)
        h = nn.functional.elu(h + self.skip(data.x))
        return self.out(h).squeeze(-1)
