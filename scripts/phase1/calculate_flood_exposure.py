import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from pathlib import Path
import numpy as np

# --------------------------------------------------
# Paths
# --------------------------------------------------

BOUNDARY_FILE = Path(
    "data/raw/boundaries/KERALA_DISTRICT_BDY.shp"
)

OUTPUT_FILE = Path(
    "data/processed/kerala_flood_exposure.csv"
)

RASTERS = {
    "10yr": Path(
        "data/raw/flood/flood_probability_10_25_50/"
        "1. Flood Return Probability History (10, 25, 50 years)/"
        "Kerala_Flood_10_yr_Historical.tif"
    ),

    "25yr": Path(
        "data/raw/flood/flood_probability_10_25_50/"
        "1. Flood Return Probability History (10, 25, 50 years)/"
        "Kerala_Flood_25_yr_Historical.tif"
    ),

    "50yr": Path(
        "data/raw/flood/flood_probability_10_25_50/"
        "1. Flood Return Probability History (10, 25, 50 years)/"
        "Kerala_Flood_50_yr_Historical.tif"
    ),

    "100yr": Path(
        "data/raw/flood/flood_probability_100_200_500/"
        "2.Flood Return Probability History (100, 200, 500 years)/"
        "Kerala_Flood_100_yr_Historical.tif"
    ),

    "200yr": Path(
        "data/raw/flood/flood_probability_100_200_500/"
        "2.Flood Return Probability History (100, 200, 500 years)/"
        "Kerala_Flood_200_yr_Historical.tif"
    ),

    "500yr": Path(
        "data/raw/flood/flood_probability_100_200_500/"
        "2.Flood Return Probability History (100, 200, 500 years)/"
        "Kerala_Flood_500_yr_Historical.tif"
    )
}


# --------------------------------------------------
# Load district boundaries
# --------------------------------------------------

districts = gpd.read_file(BOUNDARY_FILE)

districts["DISTRICT"] = (
    districts["DISTRICT"]
    .astype(str)
    .str.strip()
)

if len(districts) != 14:
    raise ValueError(
        f"Expected 14 districts, found {len(districts)}"
    )

results = pd.DataFrame({
    "district": sorted(districts["DISTRICT"].tolist())
})


# --------------------------------------------------
# Process each flood raster
# --------------------------------------------------

for period, raster_file in RASTERS.items():

    print(f"Processing {period}...")

    if not raster_file.exists():
        raise FileNotFoundError(
            f"Raster not found: {raster_file}"
        )

    with rasterio.open(raster_file) as src:

        # Convert district polygons to raster CRS
        district_geo = districts.to_crs(src.crs)

        period_results = []

        for _, row in district_geo.iterrows():

            district_name = row["DISTRICT"]
            geometry = row.geometry

            # --------------------------------------
            # Create small raster window around
            # the district instead of loading the
            # entire Kerala raster repeatedly.
            # --------------------------------------

            minx, miny, maxx, maxy = geometry.bounds

            window = from_bounds(
                minx,
                miny,
                maxx,
                maxy,
                transform=src.transform
            )

            # Convert to integer pixel window
            window = window.round_offsets().round_lengths()

            data = src.read(
                1,
                window=window,
                masked=False
            )

            window_transform = src.window_transform(window)

            # --------------------------------------
            # DISTRICT MASK
            #
            # True = pixel centre lies inside district
            # --------------------------------------

            district_mask = geometry_mask(
                [geometry],
                out_shape=data.shape,
                transform=window_transform,
                invert=True,
                all_touched=False
            )

            district_pixels = int(
                np.count_nonzero(district_mask)
            )

            # --------------------------------------
            # FLOOD MASK
            #
            # A flood pixel is a valid raster pixel
            # inside the district.
            # --------------------------------------

            if src.nodata is not None:

                valid_raster = (
                    data != src.nodata
                )

            else:

                valid_raster = np.isfinite(data)

            # Also reject NaN / infinity
            valid_raster &= np.isfinite(data)

            flood_mask = (
                district_mask &
                valid_raster
            )

            flood_pixels = int(
                np.count_nonzero(flood_mask)
            )

            # --------------------------------------
            # Exposure ratio
            # --------------------------------------

            if district_pixels == 0:
                raise ValueError(
                    f"No district pixels found for "
                    f"{district_name}"
                )

            exposure = (
                flood_pixels /
                district_pixels
            )

            period_results.append({
                "district": district_name,
                f"district_pixels_{period}": district_pixels,
                f"flood_pixels_{period}": flood_pixels,
                f"flood_exposure_{period}": exposure
            })

        period_df = pd.DataFrame(period_results)

        results = results.merge(
            period_df,
            on="district",
            how="left",
            validate="one_to_one"
        )


# --------------------------------------------------
# Validation
# --------------------------------------------------

exposure_columns = [
    f"flood_exposure_{period}"
    for period in RASTERS.keys()
]

if len(results) != 14:
    raise ValueError(
        f"Expected 14 districts, got {len(results)}"
    )

if results[exposure_columns].isna().any().any():
    raise ValueError(
        "Missing flood exposure values detected."
    )

for column in exposure_columns:

    if not results[column].between(0, 1).all():
        raise ValueError(
            f"Invalid exposure value in {column}"
        )


# --------------------------------------------------
# Additional consistency test
# --------------------------------------------------

# A rarer/extreme return-period footprint would
# normally not be expected to be smaller than a
# more frequent footprint if the source layers
# represent nested flood extents.
#
# We only REPORT violations here rather than fail,
# because we first need to verify that assumption
# against the source data.

period_order = [
    "10yr",
    "25yr",
    "50yr",
    "100yr",
    "200yr",
    "500yr"
]

print("\nChecking return-period consistency...")

for _, row in results.iterrows():

    exposures = [
        row[f"flood_exposure_{p}"]
        for p in period_order
    ]

    monotonic = all(
        exposures[i] <= exposures[i + 1]
        for i in range(len(exposures) - 1)
    )

    if not monotonic:
        print(
            "WARNING:",
            row["district"],
            "is not monotonically increasing."
        )


# --------------------------------------------------
# Save
# --------------------------------------------------

results = results.sort_values(
    "district"
).reset_index(drop=True)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

results.to_csv(
    OUTPUT_FILE,
    index=False
)


# --------------------------------------------------
# Display
# --------------------------------------------------

print("\n--- DISTRICT FLOOD EXPOSURE ---\n")

display = results[
    ["district"] + exposure_columns
].copy()

for column in exposure_columns:
    display[column] = (
        display[column] * 100
    ).round(2)

print(display.to_string(index=False))

print("\nValues above are percentages.")

print("\nDistricts:", len(results))
print(
    "Missing exposure values:",
    results[exposure_columns].isna().sum().sum()
)

print("\nSaved:")
print(OUTPUT_FILE)