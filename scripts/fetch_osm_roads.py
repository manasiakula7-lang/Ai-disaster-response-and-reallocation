"""Build real road distances between Kerala district HQs from OpenStreetMap.

Replaces the straight-line placeholder in data/simulated/road_edges.csv.
Uses osmnx, which downloads only the major roads it needs through the
Overpass API, so no .osm.pbf file (and no pyrosm) is required.

Run on a machine with internet access:
    pip install osmnx
    python scripts/fetch_osm_roads.py

Outputs (small enough to commit):
    data/processed/road_edges_osm.csv   one row per Phase 1 adjacency edge:
        road distance (km) and free-flow travel time (hr) along the
        shortest major-road path between the two district HQs
    data/processed/kerala_major_roads.graphml   the road graph itself (cached;
        delete it to force a fresh download)
"""
import csv
from pathlib import Path

import networkx as nx
import osmnx as ox

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
SIMULATED = ROOT / "data" / "simulated"
GRAPH_FILE = PROCESSED / "kerala_major_roads.graphml"
OUTPUT_FILE = PROCESSED / "road_edges_osm.csv"

# Major roads only: enough for district-to-district routing, small download.
ROAD_FILTER = '["highway"~"motorway|trunk|primary|secondary|motorway_link|trunk_link|primary_link|secondary_link"]'

# Default speeds (km/h) where OSM has no maxspeed tag.
SPEEDS = {"motorway": 80, "trunk": 60, "primary": 50, "secondary": 40}


# Public Overpass servers, tried in order. The main one is often busy or
# blocked on campus networks; the mirrors serve the same data.
OVERPASS_SERVERS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
]


def download_graph():
    ox.settings.requests_timeout = 300
    last_error = None
    for server in OVERPASS_SERVERS:
        ox.settings.overpass_url = server
        print("Trying", server)
        try:
            return ox.graph_from_place("Kerala, India", custom_filter=ROAD_FILTER, simplify=True)
        except Exception as e:  # timeouts, connection errors, server busy
            print(f"  failed: {type(e).__name__}: {str(e)[:150]}")
            last_error = e
    raise SystemExit(f"All Overpass servers failed. Last error: {last_error}")


def load_graph():
    if GRAPH_FILE.exists():
        print("Loading cached graph:", GRAPH_FILE)
        return ox.load_graphml(GRAPH_FILE)
    print("Downloading Kerala major roads from OpenStreetMap (a few minutes)...")
    G = download_graph()
    G = ox.add_edge_speeds(G, hwy_speeds=SPEEDS)
    G = ox.add_edge_travel_times(G)
    ox.save_graphml(G, GRAPH_FILE)
    print("Saved graph:", GRAPH_FILE)
    return G


def main():
    G = load_graph()
    print(f"Graph: {len(G.nodes)} nodes, {len(G.edges)} edges")

    with open(SIMULATED / "district_locations.csv", newline="") as f:
        hq = {r["district"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)}
    with open(PROCESSED / "graph_edges.csv", newline="") as f:
        edges = list(csv.DictReader(f))

    hq_node = {d: ox.distance.nearest_nodes(G, lon, lat) for d, (lat, lon) in hq.items()}

    rows = []
    for i, e in enumerate(edges):
        a, b = hq_node[e["source"]], hq_node[e["target"]]
        try:
            length_m = nx.shortest_path_length(G, a, b, weight="length")
            time_s = nx.shortest_path_length(G, a, b, weight="travel_time")
            status = "ok"
        except nx.NetworkXNoPath:
            length_m = time_s = float("nan")
            status = "no_path"
        rows.append({
            "edge_id": i, "source_id": e["source_id"], "target_id": e["target_id"],
            "source": e["source"], "target": e["target"],
            "distance_km": round(length_m / 1000, 1),
            "travel_time_hr": round(time_s / 3600, 2),
            "status": status,
        })
        print(f"{e['source']:>18} -> {e['target']:<18} {rows[-1]['distance_km']:>6} km  "
              f"{rows[-1]['travel_time_hr']:>5} hr  {status}")

    with open(OUTPUT_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\nSaved:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
