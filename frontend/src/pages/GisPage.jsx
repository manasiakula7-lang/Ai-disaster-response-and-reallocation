import React, { useEffect, useState } from "react";
import { CLASS_LABEL, DAYS, dayDate } from "../constants.js";
import Icon from "../components/icons.jsx";
import MapView from "../components/MapView.jsx";
import { Card, DayPicker, Meter, PageHead, fmt, pct } from "../components/ui.jsx";
import { CLASS_COLOR } from "../constants.js";

const LAYER_LABEL = { basemap: "Streets", roads: "Roads", centres: "Centres", flows: "Shipments" };
const MODES = [["class", "Priority class"], ["severity", "Priority score"], ["coverage", "Need met"]];

export default function GisPage({ day, setDay, districts, centres, roads, plan }) {
  const [layers, setLayers] = useState({ basemap: true, roads: true, centres: true, flows: true });
  const [mode, setMode] = useState("class");
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return undefined;
    const t = setInterval(() => setDay((d) => (d >= DAYS.length ? 1 : d + 1)), 1800);
    return () => clearInterval(t);
  }, [playing, setDay]);

  const rows = (districts?.features.map((f) => f.properties) || []).sort((a, b) => b.severity - a.severity);
  return (
    <>
      <PageHead eyebrow="Geospatial intelligence" title="Flood Priority Map"
        subtitle="All 14 districts with road status, relief centres and today's planned shipments">
        <span className="region">KERALA · AUG 2018</span>
        <DayPicker day={day} setDay={setDay} />
      </PageHead>
      <div className="page">
        <Card eyebrow="Geospatial view" title="Live flood picture"
          right={<span className="pill">{plan ? plan.flows.length : 0} main shipment routes</span>}>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
            <div className="chips" role="group" aria-label="Colour districts by">
              {MODES.map(([k, l]) => (
                <button key={k} className={`chip ${mode === k ? "on" : ""}`} onClick={() => setMode(k)}>{l}</button>
              ))}
            </div>
            <div className="chips" style={{ marginLeft: "auto" }} aria-label="Map layers">
              {Object.keys(layers).map((k) => (
                <button key={k} className={`chip ${layers[k] ? "on" : ""}`} aria-pressed={layers[k]}
                  onClick={() => setLayers({ ...layers, [k]: !layers[k] })}>{layers[k] ? "✓ " : ""}{LAYER_LABEL[k]}</button>
              ))}
            </div>
          </div>
          {mode === "class" && (
            <div className="legend-row">
              {["high", "medium", "low"].map((c) => <span key={c}><span className="dot" style={{ background: CLASS_COLOR[c] }} />{CLASS_LABEL[c]}</span>)}
            </div>
          )}
          <MapView districts={districts} centres={centres} roads={roads} flows={plan?.flows} coverage={plan?.coverage}
            layers={layers} colorMode={mode} dayKey={day} tall />
          <div className="timeline" style={{ marginTop: 16 }}>
            <button className="play" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pause" : "Play the week"}
              title={playing ? "Pause" : "Play the week"}>
              <Icon name={playing ? "pause" : "play"} size={16} />
            </button>
            <div className="days">
              {DAYS.map((d) => (
                <button key={d} className={d === day ? "on" : ""} onClick={() => { setPlaying(false); setDay(d); }}>
                  <span className="d">Day {d}</span><span className="date">{dayDate(d)}</span>
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Card eyebrow="District status" title="Priority and planned coverage"
          subtitle="Flood priority is the GAT severity score. Need met is the share of today's need the AI agents' plan ships.">
          <table className="t">
            <thead><tr><th>District</th><th>Priority</th><th className="num">Score</th><th className="num">Displaced</th><th style={{ width: "30%" }}>Need met (plan)</th></tr></thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.name}>
                  <td><b>{p.name}</b></td>
                  <td><span className={`tag ${p.severity_class}`}>{CLASS_LABEL[p.severity_class]}</span></td>
                  <td className="num">{p.severity.toFixed(2)}</td>
                  <td className="num">{fmt(p.displaced_people)}</td>
                  <td>
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      <div style={{ flex: 1 }}><Meter value={plan?.coverage[p.name]} color="var(--accent)" thin /></div>
                      <b style={{ width: 42, textAlign: "right" }}>{pct(plan?.coverage[p.name])}</b>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  );
}
