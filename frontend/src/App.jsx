import React, { useEffect, useMemo, useState } from "react";
import { api, API } from "./api.js";
import { DAYS, RESOURCES, TRUCKLOAD, dayLabel } from "./constants.js";
import { useColorScheme } from "./theme.js";
import MapView from "./components/MapView.jsx";
import OverviewPanel from "./components/OverviewPanel.jsx";
import AlertsPanel from "./components/AlertsPanel.jsx";
import ComparePanel from "./components/ComparePanel.jsx";
import SimulatePanel from "./components/SimulatePanel.jsx";
import WhatIfPanel from "./components/WhatIfPanel.jsx";

const TABS = [
  ["overview", "Overview"], ["alerts", "Alerts & events"], ["compare", "Results"],
  ["simulate", "Simulate"], ["whatif", "What-if"],
];

// Planned shipments -> flows (centre -> district, truckloads) and totals per resource / district.
function summarisePlan(shipments, districts, centres) {
  if (!shipments || !districts || !centres) return null;
  const hq = Object.fromEntries(districts.features.map((f) => [f.properties.name, [f.properties.hq_lat, f.properties.hq_lon]]));
  const cpos = Object.fromEntries(centres.features.map((f) => [f.properties.centre_id, [f.geometry.coordinates[1], f.geometry.coordinates[0]]]));
  const flows = {}, byResource = {}, byDistrict = {};
  for (const s of shipments) {
    byResource[s.resource] = (byResource[s.resource] || 0) + s.amount;
    byDistrict[s.district] = byDistrict[s.district] || {};
    byDistrict[s.district][s.resource] = (byDistrict[s.district][s.resource] || 0) + s.amount;
    if (!TRUCKLOAD[s.resource]) continue;
    const k = `${s.centre}|${s.district}`;
    flows[k] = flows[k] || { centre: s.centre, district: s.district, from: cpos[s.centre], to: hq[s.district], loads: 0 };
    flows[k].loads += s.amount / TRUCKLOAD[s.resource];
  }
  const coverage = {};
  for (const f of districts.features) {
    const p = f.properties;
    const r = RESOURCES.filter((x) => p[x] > 0).map((x) => Math.min(1, (byDistrict[p.name]?.[x] || 0) / p[x]));
    coverage[p.name] = r.length ? r.reduce((a, b) => a + b, 0) / r.length : 1;
  }
  // Only the 25 biggest centre -> district flows, so the map stays readable.
  const top = Object.values(flows).filter((f) => f.loads >= 1).sort((a, b) => b.loads - a.loads).slice(0, 25);
  return { flows: top, byResource, coverage };
}

export default function App() {
  useColorScheme();
  const [day, setDay] = useState(3);
  const [tab, setTab] = useState("overview");
  const [layers, setLayers] = useState({ basemap: true, roads: true, centres: true, flows: true });
  const [colorMode, setColorMode] = useState("severity");
  const [districts, setDistricts] = useState(null);
  const [roads, setRoads] = useState(null);
  const [centres, setCentres] = useState(null);
  const [events, setEvents] = useState(null);
  const [alloc, setAlloc] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [sim, setSim] = useState(null);
  const [error, setError] = useState(null);

  const simDay = sim?.days?.length ? sim.days[sim.days.length - 1] : null;
  const shownDay = tab === "simulate" && simDay ? simDay.day : day;

  useEffect(() => {
    api.centres().then(setCentres).catch((e) => setError(String(e)));
    api.metrics().then(setMetrics).catch(() => {});
  }, []);
  useEffect(() => {
    setEvents(null);
    Promise.all([api.districts(shownDay), api.roads(shownDay), api.events(shownDay), api.allocations(shownDay)])
      .then(([d, r, e, a]) => { setDistricts(d); setRoads(r); setEvents(e); setAlloc(a); setError(null); })
      .catch((e) => setError(String(e)));
  }, [shownDay]);

  const useSim = tab === "simulate" && simDay;
  const plan = useMemo(
    () => summarisePlan(useSim ? simDay.shipments : alloc, districts, centres),
    [useSim, simDay, alloc, districts, centres],
  );

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Kerala Flood Relief · decision support</h1>
          <div className="sub">AI-driven disaster response and resource allocation, Aug 2018 scenario</div>
        </div>
        <div className="daypicker" role="group" aria-label="Scenario day">
          {DAYS.map((d) => (
            <button key={d} className={d === day ? "on" : ""} onClick={() => setDay(d)} title={dayLabel(d)}
              disabled={tab === "simulate" && !!simDay}>
              Day {d}
            </button>
          ))}
        </div>
        <span className="sub">{tab === "simulate" && simDay ? `Simulation: ${dayLabel(shownDay)}` : dayLabel(day)}</span>
        <div className="spacer" />
        <div className="toggles">
          <label>
            Colour by
            <select value={colorMode} onChange={(e) => setColorMode(e.target.value)}>
              <option value="severity">Severity</option>
              <option value="coverage">Share of need met</option>
            </select>
          </label>
          {Object.keys(layers).map((k) => (
            <label key={k}>
              <input type="checkbox" checked={layers[k]} onChange={() => setLayers({ ...layers, [k]: !layers[k] })} />
              {{ basemap: "Base map", roads: "Roads", centres: "Centres", flows: "Shipments" }[k]}
            </label>
          ))}
        </div>
      </header>

      <div className="main">
        <MapView districts={districts} centres={centres} roads={roads} flows={plan?.flows}
          coverage={plan?.coverage} colorMode={colorMode} layers={layers}
          dayKey={`${shownDay}-${useSim ? sim.days.length : "s6"}`} />
        <aside className="side">
          <nav className="tabs">
            {TABS.map(([k, label]) => (
              <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>
            ))}
          </nav>
          <div className="panel">
            {error && <p className="error">Can't reach the backend at {API}. Is it running? ({error})</p>}
            {tab === "overview" && <OverviewPanel districts={districts} events={events} planned={plan} />}
            {tab === "alerts" && <AlertsPanel events={events} />}
            {tab === "compare" && <ComparePanel metrics={metrics} />}
            {tab === "simulate" && <SimulatePanel roads={roads} sim={sim} setSim={setSim} />}
            {tab === "whatif" && <WhatIfPanel roads={roads} />}
          </div>
        </aside>
      </div>
    </div>
  );
}
