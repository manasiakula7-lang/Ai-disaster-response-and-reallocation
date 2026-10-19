import React, { useEffect, useRef } from "react";
import L from "leaflet";
import {
  CircleMarker, GeoJSON, MapContainer, Polyline, TileLayer, Tooltip, useMap,
} from "react-leaflet";
import {
  CLASS_COLOR, CLASS_LABEL, COVERAGE_STEPS, ROAD_STYLE, SEVERITY_STEPS, coverageColor, severityColor,
} from "../constants.js";
import { cssVar } from "../theme.js";

const fmt = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d }));
const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);

// CARTO Voyager base map (OpenStreetMap data): light streets under the coloured districts.
const TILES = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

// Zoom to Kerala once the district shapes arrive.
function FitBounds({ data }) {
  const map = useMap();
  const done = useRef(false);
  useEffect(() => {
    if (data && !done.current) {
      done.current = true;
      setTimeout(() => {   // the card may not have its final size yet on first render
        map.invalidateSize();
        map.fitBounds(L.geoJSON(data).getBounds(), { padding: [16, 16] });
      }, 60);
    }
  }, [data, map]);
  return null;
}

// colorMode: "class" (high / moderate / low), "severity" (score ramp) or "coverage" (share of need met)
export default function MapView({
  districts, centres, roads, flows, colorMode = "class", coverage, layers, dayKey, tall, onPick,
}) {
  const fill = (p) => colorMode === "coverage" ? coverageColor(coverage?.[p.name])
    : colorMode === "severity" ? severityColor(p.severity) : CLASS_COLOR[p.severity_class] || "#888";
  const flowColor = cssVar("--flow");

  return (
    <div className={`mapbox ${tall ? "tall" : ""}`}>
      <MapContainer className="map" center={[10.45, 76.35]} zoom={7} minZoom={6} zoomSnap={0.25} zoomDelta={0.5}
        scrollWheelZoom>
        {layers.basemap && (
          <TileLayer subdomains="abcd" url={TILES}
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>' />
        )}
        <FitBounds data={districts} />
        {districts && (
          <GeoJSON
            key={`d-${dayKey}-${colorMode}-${JSON.stringify(coverage || {}).length}`}
            data={districts}
            style={(f) => ({ fillColor: fill(f.properties), fillOpacity: 0.72, color: cssVar("--district-edge"), weight: 1.4 })}
            onEachFeature={(f, layer) => {
              const p = f.properties;
              layer.bindTooltip(
                `<b>${p.name}</b><br/>Flood priority ${p.severity?.toFixed(2) ?? "–"} (${CLASS_LABEL[p.severity_class] ?? "–"})` +
                  (colorMode === "coverage" ? `<br/>Need met ${pct(coverage?.[p.name])}` : "") +
                  `<br/>Displaced ${fmt(p.displaced_people)}<br/>Food ${fmt(p.food_kits)} kits · ` +
                  `Water ${fmt(p.water_litres / 1000)}k L<br/>Vulnerability ${p.vulnerability.toFixed(2)}`,
                { sticky: true },
              );
              layer.on({
                mouseover: () => layer.setStyle({ weight: 3 }),
                mouseout: () => layer.setStyle({ weight: 1.4 }),
                click: () => onPick?.(p.name),
              });
            }}
          />
        )}
        {layers.roads && roads?.features.map((f) => {
          const p = f.properties;
          const s = ROAD_STYLE[p.status];
          return (
            <Polyline key={`r-${dayKey}-${p.edge_id}`}
              positions={f.geometry.coordinates.map(([lon, lat]) => [lat, lon])}
              pathOptions={{ color: s.color, weight: 3, dashArray: s.dashArray, opacity: 0.95,
                className: p.status === "blocked" ? "road-blocked" : "" }}>
              <Tooltip sticky>
                {p.source} – {p.target}: <b>{s.label}</b>
                {p.current_travel_time_hr ? ` (${p.current_travel_time_hr.toFixed(1)} h)` : ""}
              </Tooltip>
            </Polyline>
          );
        })}
        {layers.flows && flows?.map((f) => {
          const w = Math.max(1.5, Math.min(8, f.loads / 4));
          return (
            <React.Fragment key={`f-${dayKey}-${f.centre}-${f.district}`}>
              <Polyline positions={[f.from, f.to]} interactive={false}
                pathOptions={{ color: flowColor, weight: w + 8, opacity: 0.18, lineCap: "round" }} />
              <Polyline positions={[f.from, f.to]}
                pathOptions={{ color: cssVar("--flow-line"), weight: w, opacity: 0.95, dashArray: "10 8", lineCap: "round", className: "flow-line" }}>
                <Tooltip sticky>{f.centre} → {f.district}: <b>{fmt(f.loads, 1)} truckloads</b></Tooltip>
              </Polyline>
            </React.Fragment>
          );
        })}
        {layers.centres && centres?.features.map((f) => {
          const p = f.properties;
          const [lon, lat] = f.geometry.coordinates;
          return (
            <CircleMarker key={`c-${p.centre_id}`} center={[lat, lon]} radius={4 + p.vehicles / 3}
              pathOptions={{ color: cssVar("--centre"), weight: 2, fillColor: cssVar("--card"), fillOpacity: 0.95 }}>
              <Tooltip>
                <b>{p.name}</b> ({p.centre_id})<br />
                Food {fmt(p.food_kits)} · Water {fmt(p.water_litres / 1000)}k L<br />
                Medicine {fmt(p.medicine_kits)} · Teams {p.rescue_teams} · Vehicles {p.vehicles}
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>

      {colorMode !== "class" && (
        <div className="map-overlay" style={{ left: 12, bottom: 12, width: 190 }}>
          <b style={{ color: "var(--text)" }}>{colorMode === "coverage" ? "Share of need met" : "Flood priority score"}</b>
          <div style={{ display: "flex", margin: "6px 0 2px", borderRadius: 3, overflow: "hidden" }}>
            {(colorMode === "coverage" ? COVERAGE_STEPS : SEVERITY_STEPS).map((c) => <span key={c} style={{ flex: 1, height: 8, background: c }} />)}
          </div>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <span>{colorMode === "coverage" ? "0%" : "low"}</span><span>{colorMode === "coverage" ? "100%" : "high"}</span>
          </div>
        </div>
      )}
      {(layers.roads || layers.centres || layers.flows) && (
        <div className="map-overlay" style={{ right: 12, bottom: 24 }}>
          {layers.roads && Object.entries(ROAD_STYLE).map(([k, s]) => (
            <div className="row" key={k}>
              <svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke={s.color} strokeWidth="3" strokeDasharray={s.dashArray || undefined} /></svg>
              Road {s.label.toLowerCase()}
            </div>
          ))}
          {layers.centres && (
            <div className="row">
              <svg width="26" height="12"><circle cx="13" cy="6" r="5" style={{ fill: "var(--card)", stroke: "var(--text)" }} strokeWidth="2" /></svg>
              Relief centre
            </div>
          )}
          {layers.flows && (
            <div className="row">
              <svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" style={{ stroke: "var(--flow-line)" }} strokeWidth="3" strokeDasharray="6 4" /></svg>
              Shipment
            </div>
          )}
        </div>
      )}
    </div>
  );
}
