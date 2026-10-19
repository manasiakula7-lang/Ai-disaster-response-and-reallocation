import React, { useState } from "react";
import { api } from "../api.js";
import { POLICY_LABEL } from "../constants.js";

const ROWS = [
  ["fulfilment", "Demand met", "pct", true],
  ["vuln_weighted_fulfilment", "Vulnerability-weighted coverage", "pct", true],
  ["worst_district_fulfilment", "Worst-off district", "pct", true],
  ["gini", "Gini", "num", false],
  ["avg_delay_hr", "Delivery time (h)", "num", false],
  ["neglect_district_days", "Neglected district-days", "int", false],
];
const show = (v, kind) => (kind === "pct" ? `${(v * 100).toFixed(1)}%` : kind === "int" ? v.toFixed(0) : v.toFixed(2));

export default function WhatIfPanel({ roads }) {
  const [policy, setPolicy] = useState("mappo");
  const [stock, setStock] = useState(1);
  const [demand, setDemand] = useState(1);
  const [closed, setClosed] = useState([]);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const run = async () => {
    setBusy(true); setErr(null);
    try {
      setRes(await api.whatIf({ policy, stock_factor: stock, demand_factor: demand, closed_edges: closed }));
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const toggle = (id) => setClosed(closed.includes(id) ? closed.filter((x) => x !== id) : [...closed, id]);

  return (
    <div>
      <p className="note">Change the scenario and replay the whole week, compared with the same week unchanged.</p>
      <div className="form">
        <label>Strategy
          <select value={policy} onChange={(e) => setPolicy(e.target.value)}>
            {Object.entries(POLICY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label>Stock: {Math.round(stock * 100)}% of normal
          <input type="range" min="0.3" max="2" step="0.1" value={stock} onChange={(e) => setStock(Number(e.target.value))} />
        </label>
        <label>Demand: {Math.round(demand * 100)}% of normal
          <input type="range" min="0.5" max="2" step="0.1" value={demand} onChange={(e) => setDemand(Number(e.target.value))} />
        </label>
        <label>Close roads for the whole week ({closed.length} selected)
          <div className="roads">
            {roads?.features.map((f) => {
              const p = f.properties;
              return (
                <label key={p.edge_id}>
                  <input type="checkbox" checked={closed.includes(p.edge_id)} onChange={() => toggle(p.edge_id)} />
                  {p.source} – {p.target}
                </label>
              );
            })}
          </div>
        </label>
        <div className="row">
          <button className="btn" onClick={run} disabled={busy}>{busy ? "Running…" : "Run what-if"}</button>
        </div>
        {err && <p className="error">{err}</p>}
      </div>

      {res && (
        <>
          <h2>Result: {POLICY_LABEL[res.policy]}</h2>
          <table className="t">
            <thead><tr><th>Measure</th><th>Normal week</th><th>What-if</th><th>Change</th></tr></thead>
            <tbody>
              {ROWS.map(([k, label, kind, higherBetter]) => {
                const d = res.change[k];
                const good = Math.abs(d) < 1e-9 ? null : (d > 0) === higherBetter;
                return (
                  <tr key={k}>
                    <td>{label}</td>
                    <td>{show(res.baseline[k], kind)}</td>
                    <td>{show(res.what_if[k], kind)}</td>
                    <td className={good == null ? "" : good ? "up" : "down"}>
                      {good == null ? "no change" : `${good ? "▲ better" : "▼ worse"} ${d > 0 ? "+" : "−"}${
                        kind === "pct" ? `${(Math.abs(d) * 100).toFixed(1)} pts` : show(Math.abs(d), kind)}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
