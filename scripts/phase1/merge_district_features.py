import pandas as pd
from pathlib import Path

POPULATION_FILE = Path(
    "data/processed/kerala_population_2018.csv"
)

VULNERABILITY_FILE = Path(
    "data/processed/kerala_vulnerability.csv"
)

OUTPUT_FILE = Path(
    "data/processed/district_features.csv"
)

# Load datasets
population = pd.read_csv(POPULATION_FILE)
vulnerability = pd.read_csv(VULNERABILITY_FILE)
# Standardize district names
population["district"] = population["district"].astype(str).str.strip()
vulnerability["district"] = vulnerability["district"].astype(str).str.strip()
print("Population districts:", len(population))
print("Vulnerability districts:", len(vulnerability))

# --------------------------------------------------
# Validate district names BEFORE merging
# --------------------------------------------------

population_districts = set(population["district"])
vulnerability_districts = set(vulnerability["district"])

only_population = population_districts - vulnerability_districts
only_vulnerability = vulnerability_districts - population_districts

if only_population or only_vulnerability:

    print("\nDistrict mismatch detected.")

    print("Only in population:")
    print(only_population)

    print("Only in vulnerability:")
    print(only_vulnerability)

    raise ValueError("District names do not match.")

print("District names match perfectly.")

# --------------------------------------------------
# Keep required vulnerability features
# --------------------------------------------------

vulnerability = vulnerability[
    [
        "district",
        "vulnerability_score"
    ]
]

# --------------------------------------------------
# Merge
# --------------------------------------------------

merged = population.merge(
    vulnerability,
    on="district",
    how="inner",
    validate="one_to_one"
)

# --------------------------------------------------
# Final validation
# --------------------------------------------------

if len(merged) != 14:
    raise ValueError(
        f"Expected 14 districts after merge, found {len(merged)}"
    )

if merged.isna().any().any():
    raise ValueError("Missing values detected after merge.")

# Sort alphabetically for consistency
merged = merged.sort_values("district").reset_index(drop=True)

merged.to_csv(OUTPUT_FILE, index=False)

print("\nMERGE SUCCESSFUL\n")

print(
    merged[
        [
            "district",
            "population_2018",
            "vulnerability_score"
        ]
    ].to_string(index=False)
)

print("\nRows:", len(merged))
print("Missing values:", merged.isna().sum().sum())
print("Saved:", OUTPUT_FILE)