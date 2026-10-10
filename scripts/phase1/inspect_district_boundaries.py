import geopandas as gpd
from pathlib import Path

FILE = Path(
    "data/raw/boundaries/KERALA_DISTRICT_BDY.shp"
)

print("Loading district boundaries...")

gdf = gpd.read_file(FILE)

print("\n--- BASIC INFORMATION ---")
print("Rows:", len(gdf))
print("CRS:", gdf.crs)
print("Geometry types:")
print(gdf.geometry.geom_type.value_counts())

print("\n--- COLUMNS ---")
for column in gdf.columns:
    print("-", column)

print("\n--- ATTRIBUTE DATA ---")
print(gdf.drop(columns="geometry").to_string(index=False))

print("\n--- GEOMETRY VALIDATION ---")
print("Missing geometries:", gdf.geometry.isna().sum())
print("Empty geometries:", gdf.geometry.is_empty.sum())
print("Valid geometries:", gdf.geometry.is_valid.sum())
print("Invalid geometries:", (~gdf.geometry.is_valid).sum())

print("\nBounds:")
print(gdf.total_bounds)