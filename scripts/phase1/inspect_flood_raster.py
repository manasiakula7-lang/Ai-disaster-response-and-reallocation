import rasterio
import numpy as np
from pathlib import Path

RASTER = Path(
    "data/raw/flood/flood_probability_10_25_50/"
    "1. Flood Return Probability History (10, 25, 50 years)/"
    "Kerala_Flood_10_yr_Historical.tif"
)

print("Opening:", RASTER)

with rasterio.open(RASTER) as src:

    print("\n--- RASTER METADATA ---")
    print("CRS:", src.crs)
    print("Width:", src.width)
    print("Height:", src.height)
    print("Bands:", src.count)
    print("Data type:", src.dtypes)
    print("NoData:", src.nodata)
    print("Bounds:", src.bounds)
    print("Resolution:", src.res)

    data = src.read(1, masked=True)
    values = data.compressed()

    print("\n--- VALID DATA ---")
    print("Valid pixels:", data.count())
    print("Masked/NoData pixels:", data.size - data.count())

    print("\n--- VALUE STATISTICS ---")
    print("Unique values:", len(np.unique(values)))
    print("Minimum:", np.min(values))
    print("Maximum:", np.max(values))
    print("Mean:", np.mean(values))
    print("Median:", np.median(values))
    print("Standard deviation:", np.std(values))

    print("\nPercentiles:")
    for p in [1, 5, 25, 50, 75, 95, 99]:
        print(f"{p}%:", np.percentile(values, p))

    print("\n--- BAND INFORMATION ---")
    print("Descriptions:", src.descriptions)
    print("Units:", src.units)
    print("Tags:", src.tags())
    print("Band tags:", src.tags(1))