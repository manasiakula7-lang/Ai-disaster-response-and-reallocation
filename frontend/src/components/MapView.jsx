import React, { useEffect, useRef } from "react";
import L from "leaflet";
import {
  CircleMarker, GeoJSON, MapContainer, Polyline, TileLayer, Tooltip, ZoomControl, useMap,
} from "react-leaflet";
import {
  COVERAGE_STEPS, ROAD_STYLE, SEVERITY_STEPS, coverageColor, severityColor,
} from "../constants.js";
import { cssVar } from "../theme.js";
import Icon from "./icons.jsx";

const fmt = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d }));
const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);

// CARTO base maps (OpenStreetMap data): a dark one for the control-room look, a light one for light mode.
const TILES = {
  dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
  light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
};
const LAYER_LABEL = { basemap: "Streets", roads: "Roads", centres: "Centres", flows: "Shipments" };

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
        // keep Kerala clear of the floating title, legend and timeline
        const wide = window.innerWidth > 900;
        map.fitBounds(L.geoJSON(data).getBounds(), wide
          ? { paddingTopLeft: [250, 20], paddingBottomRight: [20, 80] }
          : { paddingTopLeft: [10, 60], paddingBottomRight: [10, 110] });
      }, 50);
    }
  }, [data, map]);
  return null;
}

export default function MapView({
  districts, centres, roads, flows, colorMode, setColorMode, coverage, layers, setLayers, theme, title, dayKey,
}) {
  const fill = (p) =>
    colorMode === "coverage" ? coverageColor(coverage?.[p.name]) : severityColor(p.severity);
  const flowColor = cssVar("--flow");

  return (
    <div className="mapwrap">
      <MapContainer className="map" center={[10.45, 76.35]} zoom={7} minZoom={6} zoomSnap={0.25} zoomDelta={0.5}
        scrollWheelZoom zoomControl={false}>
        {layers.basemap && (
          <TileLayer
            key={theme}
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
            url={TILES[theme] || TILES.dark}
            subdomains="abcd"
          />
        )}
        <ZoomControl position="bottomright" />
        <FitBounds data={districts} />
        {districts && (
          <GeoJSON
            key={`d-${dayKey}-${colorMode}-${theme}-${JSON.stringify(coverage || {}).length}`}
            data={districts}
            style={(f) => ({
              fillColor: fill(f.properties), fillOpacity: theme === "dark" ? 0.7 : 0.72,
              color: cssVar("--district-edge"), weight: 1.2,
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
              layer.on({
                mouseover: () => layer.setStyle({ weight: 2.5, color: cssVar("--text") }),
                mouseout: () => layer.setStyle({ weight: 1.2, color: cssVar("--district-edge") }),
              });
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
              pathOptions={{ color: s.color, weight: 3, dashArray: s.dashArray, opacity: 0.95,
                className: p.status === "blocked" ? "road-blocked" : "" }}
            >
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
            <React.Fragment key={`f-${dayKey}-${theme}-${f.centre}-${f.district}`}>
              {/* soft glow underneath, then a thin moving line on top */}
              <Polyline positions={[f.from, f.to]} interactive={false}
                pathOptions={{ color: flowColor, weight: w + 8, opacity: 0.16, lineCap: "round" }} />
              <Polyline positions={[f.from, f.to]}
                pathOptions={{ color: flowColor, weight: w, opacity: 0.95, dashArray: "10 8",
                  lineCap: "round", className: "flow-line" }}>
                <Tooltip sticky>
                  {f.centre} → {f.district}: <b>{fmt(f.loads, 1)} truckloads</b>
                </Tooltip>
              </Polyline>
            </React.Fragment>
          );
        })}
        {layers.centres && centres?.features.map((f) => {
          const p = f.properties;
          const [lon, lat] = f.geometry.coordinates;
          return (
            <CircleMarker
              key={`c-${theme}-${p.centre_id}`}
              center={[lat, lon]}
              radius={4 + p.vehicles / 3}
              pathOptions={{ color: cssVar("--centre-ring"), weight: 2, fillColor: cssVar("--centre"), fillOpacity: 0.95 }}
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

      {/* floating title, top left */}
      <div className="map-title glass">
        <div className="eyebrow">Kerala floods · live picture</div>
        <div className="big">{title}</div>
      </div>

      {/* floating controls, top right */}
      <div className="map-controls glass">
        <div className="seg" role="group" aria-label="Colour districts by">
          <button className={colorMode === "severity" ? "on" : ""} onClick={() => setColorMode("severity")}>Severity</button>
          <button className={colorMode === "coverage" ? "on" : ""} onClick={() => setColorMode("coverage")}>Need met</button>
        </div>
        <div className="chips" aria-label="Map layers">
          <Icon name="layers" size={15} />
          {Object.keys(layers).map((k) => (
            <button key={k} className={`chip ${layers[k] ? "on" : ""}`} aria-pressed={layers[k]}
              onClick={() => setLayers({ ...layers, [k]: !layers[k] })}>
              {LAYER_LABEL[k]}
            </button>
          ))}
        </div>
      </div>

      {/* legend, under the title */}
      <details className="legend glass" open={window.innerWidth > 900}>
        <summary>{colorMode === "coverage" ? "Share of need met" : "Severity (AI score)"}</summary>
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
            <svg width="26" height="12"><circle cx="13" cy="6" r="5" fill={cssVar("--centre")} stroke={cssVar("--centre-ring")} strokeWidth="2" /></svg>
            Relief centre (size = vehicles)
          </div>
        )}
        {layers.flows && (
          <div className="row">
            <svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke={flowColor} strokeWidth="3" strokeDasharray="6 4" /></svg>
            Shipment (width = truckloads)
          </div>
        )}
      </details>
    </div>
  );
}
