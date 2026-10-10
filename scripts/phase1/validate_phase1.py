import pandas as pd
from pathlib import Path

FEATURE_FILE = Path("data/processed/district_features.csv")
NODE_FILE = Path("data/processed/graph_nodes.csv")
EDGE_FILE = Path("data/processed/graph_edges.csv")
FLOOD_FILE = Path("data/processed/kerala_flood_exposure.csv")
VULNERABILITY_FILE = Path("data/processed/kerala_vulnerability.csv")


print("=" * 60)
print("PHASE 1 FINAL VALIDATION")
print("=" * 60)

# --------------------------------------------------
# Load
# --------------------------------------------------

features = pd.read_csv(FEATURE_FILE)
nodes = pd.read_csv(NODE_FILE)
edges = pd.read_csv(EDGE_FILE)
flood = pd.read_csv(FLOOD_FILE)
vulnerability = pd.read_csv(VULNERABILITY_FILE)


# --------------------------------------------------
# 1. District validation
# --------------------------------------------------

print("\n[1] DISTRICT VALIDATION")

if len(features) != 14:
    raise ValueError("district_features.csv does not contain 14 districts.")

if len(nodes) != 14:
    raise ValueError("graph_nodes.csv does not contain 14 nodes.")

if features["district"].duplicated().any():
    raise ValueError("Duplicate districts found.")

if nodes["district"].duplicated().any():
    raise ValueError("Duplicate graph nodes found.")

print("PASS - 14 unique Kerala districts")


# --------------------------------------------------
# 2. Missing values
# --------------------------------------------------

print("\n[2] MISSING VALUE CHECK")

if features.isna().any().any():
    raise ValueError("Missing values in district features.")

if nodes.isna().any().any():
    raise ValueError("Missing values in graph nodes.")

if edges.isna().any().any():
    raise ValueError("Missing values in graph edges.")

print("PASS - no missing values")


# --------------------------------------------------
# 3. Node ID validation
# --------------------------------------------------

print("\n[3] NODE ID CHECK")

expected_ids = set(range(14))
actual_ids = set(nodes["node_id"])

if actual_ids != expected_ids:
    raise ValueError("Node IDs are incorrect.")

print("PASS - node IDs 0 to 13")


# --------------------------------------------------
# 4. Edge validation
# --------------------------------------------------

print("\n[4] GRAPH EDGE CHECK")

valid_ids = set(nodes["node_id"])

if not set(edges["source_id"]).issubset(valid_ids):
    raise ValueError("Invalid source node ID.")

if not set(edges["target_id"]).issubset(valid_ids):
    raise ValueError("Invalid target node ID.")

if (edges["source_id"] == edges["target_id"]).any():
    raise ValueError("Self-loop detected.")

duplicate_edges = edges.duplicated(
    subset=["source_id", "target_id"]
).sum()

if duplicate_edges > 0:
    raise ValueError("Duplicate graph edges detected.")

represented = (
    set(edges["source_id"])
    | set(edges["target_id"])
)

if represented != valid_ids:
    raise ValueError("Some nodes are disconnected.")

print("PASS - graph edges valid")
print("Edges:", len(edges))


# --------------------------------------------------
# 5. Flood features
# --------------------------------------------------

print("\n[5] FLOOD FEATURE CHECK")

flood_columns = [
    "flood_exposure_10yr",
    "flood_exposure_25yr",
    "flood_exposure_50yr",
    "flood_exposure_100yr",
    "flood_exposure_200yr",
    "flood_exposure_500yr"
]

for column in flood_columns:

    if column not in features.columns:
        raise ValueError(f"Missing feature: {column}")

    if not features[column].between(0, 1).all():
        raise ValueError(f"Invalid values in {column}")

print("PASS - six flood exposure features valid")


# --------------------------------------------------
# 6. Vulnerability
# --------------------------------------------------

print("\n[6] VULNERABILITY CHECK")

if "vulnerability_score" not in features.columns:
    raise ValueError("Vulnerability score missing.")

if not features["vulnerability_score"].between(0, 1).all():
    raise ValueError("Invalid vulnerability scores.")

print("PASS - vulnerability scores valid")


# --------------------------------------------------
# 7. Population
# --------------------------------------------------

print("\n[7] POPULATION CHECK")

if (features["population_2018"] <= 0).any():
    raise ValueError("Invalid population value.")

print("PASS - population values valid")


# --------------------------------------------------
# 8. Dataset agreement
# --------------------------------------------------

print("\n[8] DATASET AGREEMENT")

sets = [
    set(features["district"]),
    set(nodes["district"]),
    set(flood["district"]),
    set(vulnerability["district"].astype(str).str.strip())
]

if not all(s == sets[0] for s in sets):
    raise ValueError("District mismatch between processed datasets.")

print("PASS - district names agree across datasets")


# --------------------------------------------------
# FINAL
# --------------------------------------------------

print("\n" + "=" * 60)

print("ALL PHASE 1 VALIDATION CHECKS PASSED")

print("=" * 60)

print("\nFinal dataset summary:")
print("Districts:", len(nodes))
print("Graph edges:", len(edges))
print("Node feature columns:", len(nodes.columns) - 2)
print("Missing values: 0")

print("\nPHASE 1 DATA FOUNDATION READY")