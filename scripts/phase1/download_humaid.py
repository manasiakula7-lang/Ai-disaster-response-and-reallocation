from datasets import load_dataset
from pathlib import Path

OUTPUT_DIR = Path("data/raw/humaid_kerala_2018")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Loading HumAID Kerala Floods 2018...")

dataset = load_dataset(
    "QCRI/HumAID-events",
    "kerala_floods_2018"
)

print("\nDataset loaded successfully.")
print(dataset)

for split_name, split_data in dataset.items():
    print(f"\n--- {split_name.upper()} ---")
    print("Rows:", len(split_data))
    print("Columns:", split_data.column_names)

    df = split_data.to_pandas()

    output_file = OUTPUT_DIR / f"{split_name}.csv"
    df.to_csv(output_file, index=False)

    print("Saved:", output_file)

print("\nHumAID Kerala dataset saved successfully.")