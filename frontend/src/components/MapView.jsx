import React, { useEffect, useRef } from "react";
import L from "leaflet";
import { CircleMarker, GeoJSON, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import {
  COVERAGE_STEPS, ROAD_STYLE, SEVERITY_STEPS, coverageColor, severityColor,
} from "../constants.js";
import { cssVar } from "../theme.js";

const fmt = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d }));
const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);

// Zoom to Kerala once the district shapes arrive.
function FitBounds({ data }) {
  const map = useMap();
  const done = useRef(false);
  useEffect(() => {
    if (data && !done.current) {
      done.current = true;
      // the grid cell may not have its final size yet on first render
      setTimeout(() => {
        map.invalidateSize();
        map.fitBounds(L.geoJSON(data).getBounds(), { padding: [8, 8] });
      }, 50);
    }
  }, [data, map]);
  return null;
}

export default function MapView({ districts, centres, roads, flows, colorMode, coverage, layers, dayKey }) {
  const fill = (p) =>
    colorMode === "coverage" ? coverageColor(coverage?.[p.name]) : severityColor(p.severity);

  return (
    <div className="mapwrap">
      <MapContainer className="map" center={[10.45, 76.35]} zoom={7} minZoom={6} zoomSnap={0.25} zoomDelta={0.5} scrollWheelZoom>
        {layers.basemap && (
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            opacity={0.55}
          />
        )}
        <FitBounds data={districts} />
        {districts && (
          <GeoJSON
            key={`d-${dayKey}-${colorMode}-${JSON.stringify(coverage || {}).length}`}
            data={districts}
            style={(f) => ({
              fillColor: fill(f.properties), fillOpacity: 0.78,
              color: "#ffffff", weight: 1.5,
            })}
            onEachFeature={(f, layer) => {
              const p = f.properties;
              layer.bindTooltip(
                `<b>${p.name}</b><br/>Severity ${p.severity?.toFixed(2) ?? "–"} (${p.severity_class ?? "–"})` +
                  (colorMode === "coverage" ? `<br/>Need met ${pct(coverage?.[p.name])}` : "") +
                  `<br/>Displaced ${fmt(p.displaced_people)}<br/>Food ${fmt(p.food_kits)} kits · ` +
                  `Water ${fmt(p.water_litres / 1000)}k L<br/>Vulnerability ${p.vulnerability.toFixed(2)}`,
                { sticky: true },
              );
            }}
          />
        )}
        {layers.roads && roads?.features.map((f) => {
          const p = f.properties;
          const s = ROAD_STYLE[p.status];
          return (
            <Polyline
              key={`r-${dayKey}-${p.edge_id}`}
              positions={f.geometry.coordinates.map(([lon, lat]) => [lat, lon])}
              pathOptions={{ color: s.color, weight: 3, dashArray: s.dashArray, opacity: 0.95 }}
            >
              <Tooltip sticky>
                {p.source} – {p.target}: <b>{s.label}</b>
                {p.current_travel_time_hr ? ` (${p.current_travel_time_hr.toFixed(1)} h)` : ""}
              </Tooltip>
            </Polyline>
          );
        })}
        {layers.flows && flows?.map((f) => (
          <Polyline
            key={`f-${dayKey}-${f.centre}-${f.district}`}
            positions={[f.from, f.to]}
            pathOptions={{ color: cssVar("--series-1"), weight: Math.max(1.5, Math.min(10, f.loads / 4)), opacity: 0.6 }}
          >
            <Tooltip sticky>
              {f.centre} → {f.district}: <b>{fmt(f.loads, 1)} truckloads</b>
            </Tooltip>
          </Polyline>
        ))}
        {layers.centres && centres?.features.map((f) => {
          const p = f.properties;
          const [lon, lat] = f.geometry.coordinates;
          return (
            <CircleMarker
              key={p.centre_id}
              center={[lat, lon]}
              radius={5 + p.vehicles / 3}
              pathOptions={{ color: cssVar("--surface"), weight: 2, fillColor: cssVar("--text"), fillOpacity: 0.85 }}
            >
              <Tooltip>
                <b>{p.name}</b> ({p.centre_id})<br />
                Food {fmt(p.food_kits)} · Water {fmt(p.water_litres / 1000)}k L<br />
                Medicine {fmt(p.medicine_kits)} · Teams {p.rescue_teams} · Vehicles {p.vehicles}
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>

      <details className="legend" open={window.innerWidth > 900}>
        <summary><b>{colorMode === "coverage" ? "Share of need met" : "Severity (GAT, Step 2)"}</b></summary>
        <div className="ramp">
          {(colorMode === "coverage" ? COVERAGE_STEPS : SEVERITY_STEPS).map((c) => (
            <span key={c} style={{ background: c }} />
          ))}
        </div>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <span>{colorMode === "coverage" ? "0%" : "low"}</span>
          <span>{colorMode === "coverage" ? "100%" : "high"}</span>
        </div>
        {layers.roads && Object.entries(ROAD_STYLE).map(([k, s]) => (
          <div className="row" key={k}>
            <svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke={s.color} strokeWidth="3"
              strokeDasharray={s.dashArray || undefined} /></svg>
            Road {s.label.toLowerCase()}
          </div>
        ))}
        {layers.centres && (
          <div className="row">
            <svg width="26" height="12"><circle cx="13" cy="6" r="5" fill={cssVar("--text")} stroke={cssVar("--surface")} strokeWidth="2" /></svg>
            Relief centre (size = vehicles)
          </div>
        )}
        {layers.flows && (
          <div className="row">
            <svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke={cssVar("--series-1")} strokeWidth="4" opacity="0.6" /></svg>
            Biggest shipments (width = truckloads)
          </div>
        )}
      </details>
    </div>
  );
}
