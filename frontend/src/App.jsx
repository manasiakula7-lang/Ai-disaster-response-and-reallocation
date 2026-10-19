import React, { useEffect, useMemo, useState } from "react";
import { api, API } from "./api.js";
import { RESOURCES, TRUCKLOAD, dayLabel } from "./constants.js";
import { useTheme } from "./theme.js";
import MapView from "./components/MapView.jsx";
import OverviewPanel from "./components/OverviewPanel.jsx";
import AlertsPanel from "./components/AlertsPanel.jsx";
import ComparePanel from "./components/ComparePanel.jsx";
import SimulatePanel from "./components/SimulatePanel.jsx";
import WhatIfPanel from "./components/WhatIfPanel.jsx";
import KpiColumn, { dayKpis } from "./components/KpiColumn.jsx";
import Timeline from "./components/Timeline.jsx";
import HelpOverlay from "./components/HelpOverlay.jsx";
import Icon from "./components/icons.jsx";

const TABS = [
  { key: "overview", label: "Overview", icon: "overview", title: "Situation overview",
    blurb: "How bad the flood is in each district today, and how much of the need today's plan covers." },
  { key: "alerts", label: "Alerts", icon: "alerts", title: "Alerts & events",
    blurb: "Everything that happened today, in time order: tweets from the public, road changes, dispatches and alerts." },
  { key: "compare", label: "Results", icon: "results", title: "How the strategies compare",
    blurb: "Every allocation strategy tested on 50 flood weeks it had never seen." },
  { key: "simulate", label: "Simulate", icon: "simulate", title: "Run the week live",
    blurb: "Pick a strategy and play the flood week day by day. You can close a road halfway through." },
  { key: "whatif", label: "What-if", icon: "whatif", title: "What if…?",
    blurb: "Change the supplies, the size of the disaster or the roads, and see what gets better or worse." },
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
  const [theme, setTheme] = useTheme();
  const [day, setDay] = useState(3);
  const [playing, setPlaying] = useState(false);
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
  const [help, setHelp] = useState(() => {
    try { return !localStorage.getItem("seenHelp"); } catch { return false; }
  });

  const simDay = sim?.days?.length ? sim.days[sim.days.length - 1] : null;
  const useSim = tab === "simulate" && !!simDay;
  const shownDay = useSim ? simDay.day : day;

  useEffect(() => {
    api.centres().then(setCentres).catch((e) => setError(String(e)));
    api.metrics().then(setMetrics).catch(() => {});
  }, []);
  useEffect(() => {
    Promise.all([api.districts(shownDay), api.roads(shownDay), api.events(shownDay), api.allocations(shownDay)])
      .then(([d, r, e, a]) => { setDistricts(d); setRoads(r); setEvents(e); setAlloc(a); setError(null); })
      .catch((e) => setError(String(e)));
  }, [shownDay]);
  useEffect(() => { if (tab === "simulate") setPlaying(false); }, [tab]);

  const plan = useMemo(
    () => summarisePlan(useSim ? simDay.shipments : alloc, districts, centres),
    [useSim, simDay, alloc, districts, centres],
  );
  const kpis = useMemo(() => dayKpis(districts, events, plan), [districts, events, plan]);
  const current = TABS.find((t) => t.key === tab);
  const closeHelp = () => { setHelp(false); try { localStorage.setItem("seenHelp", "1"); } catch { /* ignore */ } };

  return (
    <div className="app">
      <nav className="rail" aria-label="Sections">
        <div className="brand" title="Kerala Flood Relief"><Icon name="logo" size={22} /></div>
        {TABS.map((t) => (
          <button key={t.key} className={`rail-btn ${tab === t.key ? "on" : ""}`} onClick={() => setTab(t.key)}
            aria-current={tab === t.key ? "page" : undefined}>
            <Icon name={t.icon} size={20} />
            <span>{t.label}</span>
          </button>
        ))}
        <div className="rail-spacer" />
        <button className="rail-btn small" onClick={() => setHelp(true)} title="How to use this dashboard">
          <Icon name="help" size={20} /><span>Help</span>
        </button>
        <button className="rail-btn small" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
          <Icon name={theme === "dark" ? "sun" : "moon"} size={20} /><span>{theme === "dark" ? "Light" : "Dark"}</span>
        </button>
      </nav>

      <section className="panel" aria-label={current.title}>
        <header className="panel-head">
          <h2>{current.title}</h2>
          <p>{current.blurb}</p>
        </header>
        <div className="panel-body">
          {error && (
            <div className="error-box">
              <b>Can't reach the backend.</b> Start it with <code>uvicorn backend.app.main:app --reload</code> and
              refresh this page. <span className="note">({API}: {error})</span>
            </div>
          )}
          {tab === "overview" && <OverviewPanel districts={districts} planned={plan} kpis={kpis} />}
          {tab === "alerts" && <AlertsPanel events={events} />}
          {tab === "compare" && <ComparePanel metrics={metrics} />}
          {tab === "simulate" && <SimulatePanel roads={roads} sim={sim} setSim={setSim} />}
          {tab === "whatif" && <WhatIfPanel roads={roads} />}
        </div>
      </section>

      <main className="stage">
        <MapView districts={districts} centres={centres} roads={roads} flows={plan?.flows}
          coverage={plan?.coverage} colorMode={colorMode} setColorMode={setColorMode}
          layers={layers} setLayers={setLayers} theme={theme}
          title={useSim ? `Simulation · ${dayLabel(shownDay)}` : dayLabel(shownDay)}
          dayKey={`${shownDay}-${useSim ? sim.days.length : "s6"}`} />
        <Timeline day={day} setDay={setDay} playing={playing} setPlaying={setPlaying}
          locked={tab === "simulate" && !!sim}
          lockedLabel={simDay ? `Simulation running · showing Day ${simDay.day}` : "Simulation started · press Play day 1"} />
      </main>

      <KpiColumn k={kpis} events={events} onOpenAlerts={() => setTab("alerts")} />

      {help && <HelpOverlay onClose={closeHelp} />}
    </div>
  );
}
