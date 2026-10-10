# Phase 1 scripts

Run from the repo root, in this order:

1. `prepare_population.py`: district mid-year population 2018 (Kerala Annual Vital Statistics Report 2018, Table A-1)
2. `prepare_vulnerability.py`: Kerala rows from NFHS-5 district factsheet (`data/raw/vulnerability/`, not in repo)
3. `calculate_vulnerability.py`: min-max normalised, equal-weight vulnerability index
4. `merge_district_features.py`: population + vulnerability
5. `calculate_flood_exposure.py`: KSDMA flood rasters (`data/raw/flood/`, not in repo) zonal stats per district
6. `add_flood_features.py`: adds the six flood exposure columns
7. `build_district_graph.py`: nodes + adjacency edges from `data/raw/boundaries/KERALA_DISTRICT_BDY.shp`
8. `validate_phase1.py`: final checks

`download_humaid.py` fetches HumAID from Hugging Face; `inspect_*.py` and `calculate_flood_exposure_test.py` are exploration helpers.

Steps 2 and 5 need the large raw files (NFHS-5 .xls, flood .tif) which are kept out of git; their outputs are already in `data/processed/`.
