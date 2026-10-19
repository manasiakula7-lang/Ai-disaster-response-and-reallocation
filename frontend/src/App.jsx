import React, { useEffect, useMemo, useState } from "react";
import { api, API } from "./api.js";
import { RESOURCES, TRUCKLOAD } from "./constants.js";
import Icon from "./components/icons.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import GisPage from "./pages/GisPage.jsx";
import NetworkPage from "./pages/NetworkPage.jsx";
import DecisionPage from "./pages/DecisionPage.jsx";
import AllocationPage from "./pages/AllocationPage.jsx";
import AnalyticsPage from "./pages/AnalyticsPage.jsx";

const PAGES = [
  { key: "overview", label: "Overview", icon: "overview" },
  { key: "gis", label: "GIS Intelligence", icon: "map" },
  { key: "network", label: "GAT Network", icon: "network" },
  { key: "decision", label: "Decision Support", icon: "shield" },
  { key: "allocation", label: "Resource Allocation", icon: "layers" },
  { key: "analytics", label: "Model Analytics", icon: "chart" },
];

// "#decision?tweet=123" -> { page: "decision", params: { tweet: "123" } }
function readHash() {
  const [page, query] = window.location.hash.replace(/^#/, "").split("?");
  return { page: PAGES.some((p) => p.key === page) ? page : "overview", params: Object.fromEntries(new URLSearchParams(query || "")) };
}

// Planned shipments -> flows (centre -> district, truckloads) and totals per resource / district.
export function summarisePlan(shipments, districts, centres) {
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
  const [route, setRoute] = useState(readHash);
  const [day, setDay] = useState(3);
  const [centres, setCentres] = useState(null);
  const [dayData, setDayData] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    const f = () => { setRoute(readHash()); document.querySelector(".main")?.scrollTo(0, 0); };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  useEffect(() => { api.centres().then(setCentres).catch((e) => setError(String(e))); }, []);
  useEffect(() => {
    Promise.all([api.districts(day), api.roads(day), api.events(day), api.allocations(day), api.decisions(day)])
      .then(([districts, roads, events, alloc, reports]) => { setDayData({ districts, roads, events, alloc, reports }); setError(null); })
      .catch((e) => setError(String(e)));
  }, [day]);

  const plan = useMemo(() => summarisePlan(dayData.alloc, dayData.districts, centres), [dayData, centres]);
  const go = (page, params) => { window.location.hash = params ? `${page}?${new URLSearchParams(params)}` : page; };
  const shared = { day, setDay, centres, ...dayData, plan, go, params: route.params };

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <span className="brand-mark"><Icon name="logo" size={24} /></span>
          <div>
            <div className="brand-name">RESPONDA.</div>
            <div className="brand-sub">DISASTER INTELLIGENCE</div>
          </div>
        </div>
        <div className="side-label">WORKSPACE</div>
        <nav className="nav" aria-label="Pages">
          {PAGES.map((p) => (
            <a key={p.key} href={`#${p.key}`} className={route.page === p.key ? "on" : ""}
              aria-current={route.page === p.key ? "page" : undefined}>
              <Icon name={p.icon} size={20} />{p.label}
            </a>
          ))}
        </nav>
        <div className="side-spacer" />
        <div className="side-foot">
          <span className="pin"><Icon name="pin" size={18} /></span>
          <div><b>Kerala, India</b><span>2018 floods · 14 districts</span></div>
        </div>
      </aside>

      <main className="main">
        {error && (
          <div className="page" style={{ paddingBottom: 0 }}>
            <div className="error-box">
              <b>Can't reach the backend.</b> Start it with <code>uvicorn backend.app.main:app --reload</code>, then
              refresh this page. <span className="muted">({API}: {error})</span>
            </div>
          </div>
        )}
        {route.page === "overview" && <OverviewPage {...shared} />}
        {route.page === "gis" && <GisPage {...shared} />}
        {route.page === "network" && <NetworkPage {...shared} />}
        {route.page === "decision" && <DecisionPage {...shared} />}
        {route.page === "allocation" && <AllocationPage {...shared} />}
        {route.page === "analytics" && <AnalyticsPage {...shared} />}
      </main>
    </div>
  );
}
