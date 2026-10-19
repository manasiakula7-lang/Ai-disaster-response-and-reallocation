import React, { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { POLICY_LABEL } from "../constants.js";
import { axisProps, cssVar, gridProps, tooltipProps } from "../theme.js";

// Day score from a /simulate step: demand met (totals per resource) and worst district.
export function dayStats(day) {
  const tot = {};
  for (const res of Object.values(day.districts)) {
    for (const [r, v] of Object.entries(res)) {
      if (r === "coverage") continue;
      tot[r] = tot[r] || [0, 0];
      tot[r][0] += Math.min(v.demand, v.delivered); tot[r][1] += v.demand;
    }
  }
  const ratios = Object.values(tot).filter(([, d]) => d > 0).map(([c, d]) => c / d);
  const cov = Object.values(day.districts).map((d) => d.coverage);
  return { day: `Day ${day.day}`, met: ratios.reduce((a, b) => a + b, 0) / ratios.length, worst: Math.min(...cov) };
}

export default function SimulatePanel({ roads, sim, setSim }) {
  const [policy, setPolicy] = useState("mappo");
  const [edge, setEdge] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const run = async (f) => {
    setBusy(true); setErr(null);
    try { await f(); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const start = () => run(async () => setSim({ state: await api.startSim({ policy }), days: [] }));
  const step = () => run(async () => {
    const r = await api.stepSim(sim.state.session_id);
    setSim({ state: r.state, days: [...sim.days, r] });
  });
  const playAll = () => run(async () => {
    let days = [...sim.days], state = sim.state;
    while (!state.done) {
      const r = await api.stepSim(state.session_id);
      days = [...days, r]; state = r.state;
    }
    setSim({ state, days });
  });
  const close = () => run(async () => {
    const state = await api.closeRoad(sim.state.session_id, Number(edge));
    setSim({ ...sim, state });
  });

  const series = (sim?.days || []).map(dayStats);
  const m = sim?.state?.metrics;
  return (
    <div>
      <p className="note">Plays the official flood week day by day through the backend. The map shows the
        latest day's shipments and the share of need met in each district.</p>
      <div className="form">
        <label>Strategy
          <select value={policy} onChange={(e) => setPolicy(e.target.value)}>
            {Object.entries(POLICY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <div className="row">
          <button className="btn" onClick={start} disabled={busy}>{sim ? "Restart" : "Start week"}</button>
          <button className="btn secondary" onClick={step} disabled={busy || !sim || sim.state.done}>
            {sim && !sim.state.done ? `Play day ${sim.state.next_day}` : "Play next day"}
          </button>
          <button className="btn secondary" onClick={playAll} disabled={busy || !sim || sim.state.done}>Play to end</button>
        </div>
        {sim && !sim.state.done && (
          <label>Close a road from today on (live what-if)
            <div className="row">
              <select value={edge} onChange={(e) => setEdge(e.target.value)} style={{ flex: 1 }}>
                <option value="">Choose a road…</option>
                {roads?.features.map((f) => (
                  <option key={f.properties.edge_id} value={f.properties.edge_id}>
                    {f.properties.source} – {f.properties.target}
                  </option>
                ))}
              </select>
              <button className="btn secondary" onClick={close} disabled={busy || edge === ""}>Close</button>
            </div>
          </label>
        )}
        {err && <p className="error">{err}</p>}
      </div>

      {sim?.state?.closed_roads?.length > 0 && (
        <p className="note">Closed by you: {sim.state.closed_roads.map((id) => {
          const p = roads?.features.find((f) => f.properties.edge_id === id)?.properties;
          return p ? `${p.source} – ${p.target}` : id;
        }).join(", ")}</p>
      )}

      {series.length > 0 && (
        <>
          <h2>Day by day</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={series} margin={{ top: 8, right: 16 }}>
              <CartesianGrid {...gridProps()} />
              <XAxis dataKey="day" {...axisProps()} />
              <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} {...axisProps()} width={42} />
              <Tooltip {...tooltipProps()} formatter={(v) => `${(v * 100).toFixed(1)}%`} />
              <Legend wrapperStyle={{ fontSize: 12, color: cssVar("--text-2") }} />
              <Line dataKey="met" name="Demand met" stroke={cssVar("--series-1")} strokeWidth={2} dot={{ r: 4 }} />
              <Line dataKey="worst" name="Worst-off district" stroke={cssVar("--series-2")} strokeWidth={2} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </>
      )}
      {m && (
        <>
          <h2>Week so far</h2>
          <div className="tiles">
            <div className="tile"><div className="v">{(m.fulfilment * 100).toFixed(1)}%</div><div className="k">demand met</div></div>
            <div className="tile"><div className="v">{(m.worst_district_fulfilment * 100).toFixed(1)}%</div><div className="k">worst-off district</div></div>
            <div className="tile"><div className="v">{m.gini.toFixed(3)}</div><div className="k">Gini (lower = fairer)</div></div>
          </div>
        </>
      )}
    </div>
  );
}
