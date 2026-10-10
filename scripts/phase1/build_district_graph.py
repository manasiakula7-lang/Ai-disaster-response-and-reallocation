import geopandas as gpd
import pandas as pd
from pathlib import Path

BOUNDARY_FILE = Path(
    "data/raw/boundaries/KERALA_DISTRICT_BDY.shp"
)

FEATURE_FILE = Path(
    "data/processed/district_features.csv"
)

NODE_OUTPUT = Path(
    "data/processed/graph_nodes.csv"
)

EDGE_OUTPUT = Path(
    "data/processed/graph_edges.csv"
)


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

districts = gpd.read_file(BOUNDARY_FILE)

districts["DISTRICT"] = (
    districts["DISTRICT"]
    .astype(str)
    .str.strip()
)

features = pd.read_csv(FEATURE_FILE)

features["district"] = (
    features["district"]
    .astype(str)
    .str.strip()
)


# --------------------------------------------------
# VALIDATE DISTRICTS
# --------------------------------------------------

boundary_names = set(districts["DISTRICT"])
feature_names = set(features["district"])

if boundary_names != feature_names:

    print("Only in boundaries:")
    print(boundary_names - feature_names)

    print("Only in features:")
    print(feature_names - boundary_names)

    raise ValueError("District mismatch.")


# --------------------------------------------------
# CREATE GRAPH NODES
# --------------------------------------------------

nodes = (
    features
    .sort_values("district")
    .reset_index(drop=True)
)

nodes.insert(
    0,
    "node_id",
    range(len(nodes))
)

nodes.to_csv(
    NODE_OUTPUT,
    index=False
)

print("\nGRAPH NODES CREATED")
print("Nodes:", len(nodes))


# --------------------------------------------------
# CREATE DISTRICT ADJACENCY EDGES
# --------------------------------------------------

edges = []

districts = districts.sort_values(
    "DISTRICT"
).reset_index(drop=True)

for i in range(len(districts)):

    for j in range(i + 1, len(districts)):

        district_a = districts.iloc[i]
        district_b = districts.iloc[j]

        geometry_a = district_a.geometry
        geometry_b = district_b.geometry

        # Districts are neighbours if their
        # polygons touch each other.
        if geometry_a.touches(geometry_b):

            edges.append({
                "source": district_a["DISTRICT"],
                "target": district_b["DISTRICT"]
            })


edges_df = pd.DataFrame(edges)


# --------------------------------------------------
# VALIDATE GRAPH
# --------------------------------------------------

if edges_df.empty:
    raise ValueError(
        "No district adjacency edges detected."
    )

graph_districts = set(
    edges_df["source"]
).union(
    set(edges_df["target"])
)

missing_nodes = (
    set(nodes["district"])
    - graph_districts
)

if missing_nodes:

    raise ValueError(
        f"Disconnected districts detected: "
        f"{missing_nodes}"
    )


# --------------------------------------------------
# ADD NODE IDs TO EDGES
# --------------------------------------------------

node_lookup = dict(
    zip(
        nodes["district"],
        nodes["node_id"]
    )
)

edges_df.insert(
    0,
    "source_id",
    edges_df["source"].map(node_lookup)
)

edges_df.insert(
    1,
    "target_id",
    edges_df["target"].map(node_lookup)
)


# --------------------------------------------------
# SAVE
# --------------------------------------------------

edges_df = edges_df.sort_values(
    ["source_id", "target_id"]
).reset_index(drop=True)

edges_df.to_csv(
    EDGE_OUTPUT,
    index=False
)


# --------------------------------------------------
# DISPLAY
# --------------------------------------------------

print("\n--- GRAPH NODES ---\n")

print(
    nodes[
        [
            "node_id",
            "district",
            "population_2018",
            "vulnerability_score"
        ]
    ].to_string(index=False)
)

print("\n--- GRAPH EDGES ---\n")

print(
    edges_df.to_string(index=False)
)

print("\n--- GRAPH SUMMARY ---")

print("Nodes:", len(nodes))
print("Edges:", len(edges_df))
print(
    "Districts represented in edges:",
    len(graph_districts)
)

print("\nSaved:")
print(NODE_OUTPUT)
print(EDGE_OUTPUT)