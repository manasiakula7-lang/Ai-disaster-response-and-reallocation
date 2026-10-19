import React from "react";
import { DAYS, dayLabel } from "../constants.js";
import Icon from "./icons.jsx";

export const fmt = (v, d = 0) =>
  v == null || Number.isNaN(v) ? "–" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d });
export const pct = (v, d = 0) => (v == null ? "–" : `${(v * 100).toFixed(d)}%`);

export function PageHead({ eyebrow, title, subtitle, children }) {
  return (
    <header className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="head-right">{children}</div>
    </header>
  );
}

export function Card({ eyebrow, title, subtitle, right, children, className = "", style }) {
  return (
    <section className={`card ${className}`} style={style}>
      {(eyebrow || title || right) && (
        <div className="card-head">
          <div>
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            {title && <h2>{title}</h2>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {right && <div className="right">{right}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ icon, tone = "", label, value, unit, sub }) {
  return (
    <div className="stat">
      {icon && <span className={`ico ${tone}`}><Icon name={icon} size={22} /></span>}
      <div>
        <div className="k">{label}</div>
        <div className="v">{value}{unit && <small>{unit}</small>}</div>
        {sub && <div className="s">{sub}</div>}
      </div>
    </div>
  );
}

export function Meter({ value, color = "var(--accent)", thin }) {
  const w = Math.max(0, Math.min(1, value || 0)) * 100;
  return <div className={`meter ${thin ? "thin" : ""}`}><span style={{ width: `${w}%`, background: color }} /></div>;
}

export function Loading({ what = "Loading" }) {
  return <p className="note">{what}…</p>;
}

export function DayPicker({ day, setDay }) {
  return (
    <label className="day-select" title="Scenario day">
      <select value={day} onChange={(e) => setDay(Number(e.target.value))} aria-label="Scenario day">
        {DAYS.map((d) => <option key={d} value={d}>{dayLabel(d)}</option>)}
      </select>
    </label>
  );
}

