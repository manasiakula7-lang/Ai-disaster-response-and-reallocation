import React, { useState } from "react";

const TYPES = [
  ["alert", "Alerts"], ["report", "Reports"], ["dispatch", "Dispatches"], ["road", "Roads"],
];

export default function AlertsPanel({ events }) {
  const [on, setOn] = useState({ alert: true, report: false, dispatch: true, road: true });
  if (!events) return <p className="note">Loading…</p>;
  const kind = (t) => (t.startsWith("road_") ? "road" : t);
  const shown = events.filter((e) => on[kind(e.type)]);
  const count = (k) => events.filter((e) => kind(e.type) === k).length;
  return (
    <div>
      <p className="note">The Step 6 loop for this day, in time order: real tweets (HumAID), road changes,
        the 4 dispatch waves and the alerts they triggered.</p>
      <div className="filters">
        {TYPES.map(([k, label]) => (
          <button key={k} className={on[k] ? "on" : ""} onClick={() => setOn({ ...on, [k]: !on[k] })}>
            {on[k] ? "✓ " : ""}{label} ({count(k)})
          </button>
        ))}
      </div>
      {shown.length === 0 && <p className="note">Nothing to show for this filter.</p>}
      <ul className="feed">
        {shown.map((e, i) => (
          <li key={i}>
            <div className="meta">
              <span>{e.time}</span>
              <span className={`badge ${e.type === "alert" ? "alert" : ""}`}>
                {e.type === "alert" ? "⚠ alert" : e.type.replace("_", " ")}
              </span>
              {e.district && <b>{e.district}</b>}
            </div>
            <div>{e.detail}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
