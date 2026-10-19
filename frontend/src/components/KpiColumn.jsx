import React from "react";
import { RESOURCES, severityColor } from "../constants.js";
import Icon from "./icons.jsx";

const fmt = (v) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });

// Headline numbers for the day, the worst-hit districts and the latest alerts.
export function dayKpis(districts, events, plan) {
  if (!districts) return null;
  const props = districts.features.map((f) => f.properties);
  const needShare = RESOURCES.map((r) => {
    const need = props.reduce((s, p) => s + (p[r] || 0), 0);
    return need ? Math.min(1, (plan?.byResource[r] || 0) / need) : null;
  }).filter((v) => v != null);
  return {
    displaced: props.reduce((s, p) => s + (p.displaced_people || 0), 0),
    severe: props.filter((p) => p.severity >= 0.5).length,
    alerts: (events || []).filter((e) => e.type === "alert").length,
    covered: plan && needShare.length ? needShare.reduce((a, b) => a + b, 0) / needShare.length : null,
    top: [...props].sort((a, b) => b.severity - a.severity).slice(0, 5),
  };
}

export function KpiCards({ k }) {
  if (!k) return null;
  return (
    <div className="kpis">
      <div className="kpi">
        <span className="kpi-icon"><Icon name="people" /></span>
        <div><div className="kpi-v">{fmt(k.displaced)}</div><div className="kpi-k">people displaced</div></div>
      </div>
      <div className="kpi">
        <span className="kpi-icon"><Icon name="flame" /></span>
        <div><div className="kpi-v">{k.severe} <small>of 14</small></div><div className="kpi-k">districts at high severity</div></div>
      </div>
      <div className="kpi">
        <span className="kpi-icon warn"><Icon name="alerts" /></span>
        <div><div className="kpi-v">{k.alerts}</div><div className="kpi-k">alerts raised today</div></div>
      </div>
      <div className="kpi">
        <span className="kpi-icon"><Icon name="truck" /></span>
        <div>
          <div className="kpi-v">{k.covered == null ? "–" : `${Math.round(k.covered * 100)}%`}</div>
          <div className="kpi-k">of today's need planned</div>
        </div>
      </div>
    </div>
  );
}

export default function KpiColumn({ k, events, onOpenAlerts }) {
  const latest = (events || []).filter((e) => e.type === "alert").slice(-4).reverse();
  return (
    <aside className="kpicol" aria-label="Today at a glance">
      <h3 className="col-title">Today at a glance</h3>
      <KpiCards k={k} />

      <h3 className="col-title">Most affected</h3>
      <ol className="toplist">
        {k?.top.map((p) => (
          <li key={p.name}>
            <div className="toplist-row"><span>{p.name}</span><b>{p.severity.toFixed(2)}</b></div>
            <div className="meter"><span style={{ width: `${Math.min(100, p.severity * 100)}%`, background: severityColor(p.severity) }} /></div>
          </li>
        ))}
      </ol>

      <h3 className="col-title">Latest alerts</h3>
      {latest.length === 0 && <p className="note">No alerts this day.</p>}
      <ul className="mini-feed">
        {latest.map((e, i) => (
          <li key={i}>
            <div className="meta"><span>{e.time}</span>{e.district && <b>{e.district}</b>}</div>
            <div>{e.detail}</div>
          </li>
        ))}
      </ul>
      {latest.length > 0 && <button className="link" onClick={onOpenAlerts}>See all events →</button>}
    </aside>
  );
}
