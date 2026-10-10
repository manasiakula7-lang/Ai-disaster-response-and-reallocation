# Kerala boundaries

Shapefiles for the state and district boundaries plus HQ points. Projection: Lambert Conformal Conic on WGS84 (metres; see `.prj`). Reproject to EPSG:4326 for Leaflet.

- `KERALA_DISTRICT_BDY`: 14 district polygons (DISTRICT, DIST_LGD code, area)
- `KERALA_DISTRICT_HQ`: 14 HQ points with LATITUDE/LONGITUDE columns (Ernakulam HQ = Kakkanad, Idukki = Painavu, Wayanad = Kalpetta)
- `KERALA_STATE_BDY`, `KERALA_STATE_HQ`: state outline and capital

Spelling differs from the processed CSVs in the HQ file (ALAPUZHA, PATTANAMTITTA, upper case), so normalise names before joining.
