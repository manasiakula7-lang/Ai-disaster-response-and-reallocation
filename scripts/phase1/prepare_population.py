import pandas as pd
from pathlib import Path

OUTPUT_FILE = Path("data/processed/kerala_population_2018.csv")

# Official district-wise Mid-Year Population 2018
# Source: Kerala Annual Vital Statistics Report 2018, Table A-1

population_data = [
    ["Thiruvananthapuram", 2166103, 1189045, 3355148],
    ["Kollam",             2115135,  544296, 2659431],
    ["Pathanamthitta",     1013372,  158840, 1172212],
    ["Alappuzha",          1795976,  350057, 2146033],
    ["Kottayam",           1679472,  304101, 1983573],
    ["Idukki",              991562,  101594, 1093156],
    ["Ernakulam",          2239008, 1188651, 3427659],
    ["Thrissur",           2514037,  729133, 3243170],
    ["Palakkad",           2597404,  354850, 2952254],
    ["Malappuram",         3684433,  810565, 4494998],
    ["Kozhikode",          2238323, 1011438, 3249761],
    ["Wayanad",             715586,  131051,  846637],
    ["Kannur",             1917361,  697905, 2615266],
    ["Kasaragod",          1214971,  175923, 1390894],
]

df = pd.DataFrame(
    population_data,
    columns=[
        "district",
        "rural_population_2018",
        "urban_population_2018",
        "population_2018",
    ],
)

# -----------------------------
# Validation
# -----------------------------

if len(df) != 14:
    raise ValueError(f"Expected 14 districts, found {len(df)}")

if df["district"].duplicated().any():
    raise ValueError("Duplicate district names found.")

if df["population_2018"].isna().any():
    raise ValueError("Missing population values found.")

if (df["population_2018"] <= 0).any():
    raise ValueError("Invalid population value found.")

# Check rural + urban = total
calculated_total = (
    df["rural_population_2018"]
    + df["urban_population_2018"]
)

if not calculated_total.equals(df["population_2018"]):
    raise ValueError("Rural + urban population does not match total.")

# Official Kerala state total from Table A-1
OFFICIAL_STATE_TOTAL = 34630192

calculated_state_total = int(df["population_2018"].sum())

if calculated_state_total != OFFICIAL_STATE_TOTAL:
    raise ValueError(
        f"Population total mismatch: "
        f"{calculated_state_total} != {OFFICIAL_STATE_TOTAL}"
    )

df.to_csv(OUTPUT_FILE, index=False)

print("Population dataset created successfully.\n")
print(df.to_string(index=False))

print("\nDistrict count:", len(df))
print("Calculated Kerala population:", calculated_state_total)
print("Official Kerala population:", OFFICIAL_STATE_TOTAL)
print("\nVALIDATION PASSED")
print("Saved:", OUTPUT_FILE)