import pandas as pd
from pathlib import Path

# --------------------------------------------------
# Paths
# --------------------------------------------------

DISTRICT_FILE = Path(
    "data/processed/district_features.csv"
)

FLOOD_FILE = Path(
    "data/processed/kerala_flood_exposure.csv"
)

OUTPUT_FILE = Path(
    "data/processed/district_features.csv"
)


# --------------------------------------------------
# Load
# --------------------------------------------------

districts = pd.read_csv(DISTRICT_FILE)
flood = pd.read_csv(FLOOD_FILE)

print("District feature rows:", len(districts))
print("Flood exposure rows:", len(flood))


# --------------------------------------------------
# Clean district names
# --------------------------------------------------

districts["district"] = (
    districts["district"]
    .astype(str)
    .str.strip()
)

flood["district"] = (
    flood["district"]
    .astype(str)
    .str.strip()
)


# --------------------------------------------------
# Validate district matching
# --------------------------------------------------

district_names = set(districts["district"])
flood_names = set(flood["district"])

if district_names != flood_names:

    print("\nOnly in district features:")
    print(district_names - flood_names)

    print("\nOnly in flood dataset:")
    print(flood_names - district_names)

    raise ValueError(
        "District names do not match."
    )

print("District names match perfectly.")


# --------------------------------------------------
# Select ONLY final flood features
# --------------------------------------------------

flood_columns = [
    "district",
    "flood_exposure_10yr",
    "flood_exposure_25yr",
    "flood_exposure_50yr",
    "flood_exposure_100yr",
    "flood_exposure_200yr",
    "flood_exposure_500yr",
]

flood = flood[flood_columns]


# --------------------------------------------------
# Merge
# --------------------------------------------------

merged = districts.merge(
    flood,
    on="district",
    how="inner",
    validate="one_to_one"
)


# --------------------------------------------------
# Validate
# --------------------------------------------------

if len(merged) != 14:
    raise ValueError(
        f"Expected 14 districts, found {len(merged)}"
    )

if merged.isna().any().any():
    raise ValueError(
        "Missing values detected after flood merge."
    )

for column in flood_columns[1:]:

    if not merged[column].between(0, 1).all():
        raise ValueError(
            f"Invalid flood exposure in {column}"
        )


# --------------------------------------------------
# Sort and save
# --------------------------------------------------

merged = (
    merged
    .sort_values("district")
    .reset_index(drop=True)
)

merged.to_csv(
    OUTPUT_FILE,
    index=False
)


# --------------------------------------------------
# Display
# --------------------------------------------------

print("\nFLOOD FEATURES MERGED SUCCESSFULLY\n")

display_columns = [
    "district",
    "population_2018",
    "vulnerability_score",
    "flood_exposure_10yr",
    "flood_exposure_50yr",
    "flood_exposure_100yr",
    "flood_exposure_500yr",
]

display = merged[display_columns].copy()

for column in [
    "flood_exposure_10yr",
    "flood_exposure_50yr",
    "flood_exposure_100yr",
    "flood_exposure_500yr",
]:
    display[column] = (
        display[column] * 100
    ).round(2)

print(display.to_string(index=False))

print("\nRows:", len(merged))
print("Columns:", len(merged.columns))
print("Missing values:", merged.isna().sum().sum())

print("\nSaved:")
print(OUTPUT_FILE)