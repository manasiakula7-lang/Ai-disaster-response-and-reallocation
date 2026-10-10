import geopandas as gpd
import rasterio
from rasterio.mask import mask
import numpy as np
from pathlib import Path

BOUNDARY_FILE = Path(
    "data/raw/boundaries/KERALA_DISTRICT_BDY.shp"
)

RASTER_FILE = Path(
    "data/raw/flood/flood_probability_10_25_50/"
    "1. Flood Return Probability History (10, 25, 50 years)/"
    "Kerala_Flood_10_yr_Historical.tif"
)

# Load boundaries
districts = gpd.read_file(BOUNDARY_FILE)

districts["DISTRICT"] = (
    districts["DISTRICT"]
    .astype(str)
    .str.strip()
)

print("Districts loaded:", len(districts))

with rasterio.open(RASTER_FILE) as src:

    print("Raster CRS:", src.crs)
    print("Boundary CRS:", districts.crs)

    # Match boundary CRS to raster
    districts_raster_crs = districts.to_crs(src.crs)

    print("\nBoundaries transformed to:", districts_raster_crs.crs)

    results = []

    for _, row in districts_raster_crs.iterrows():

        district = row["DISTRICT"]

        clipped, transform = mask(
            src,
            [row.geometry],
            crop=True,
            filled=False
        )

        band = clipped[0]

        total_pixels = band.size
        flood_pixels = band.count()

        exposure_ratio = (
            flood_pixels / total_pixels
            if total_pixels > 0
            else 0
        )

        results.append(
            {
                "district": district,
                "total_pixels_bbox": total_pixels,
                "flood_pixels": flood_pixels,
                "flood_exposure_10yr_test": exposure_ratio,
            }
        )

    result_df = (
        __import__("pandas")
        .DataFrame(results)
        .sort_values(
            "flood_exposure_10yr_test",
            ascending=False
        )
    )

    print("\n--- 10-YEAR FLOOD EXPOSURE TEST ---\n")

    print(
        result_df[
            [
                "district",
                "flood_pixels",
                "flood_exposure_10yr_test"
            ]
        ].to_string(index=False)
    )