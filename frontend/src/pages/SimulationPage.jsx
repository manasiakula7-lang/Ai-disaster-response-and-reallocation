import React, { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { RESOURCES, RESOURCE_LABEL, STRATEGIES, dayDate, dayLabel } from "../constants.js";
import { axisProps, cssVar, gridProps, tooltipProps } from "../theme.js";
import MapView from "../components/MapView.jsx";
import { Card, Meter, PageHead, Stat, fmt, pct } from "../components/ui.jsx";
import { summarisePlan } from "../App.jsx";

// Score of one simulated day: share of total demand met per resource (averaged) and the worst district.
function dayStats(d) {
  const tot = {};
  for (const res of Object.values(d.districts)) {
    for (const [r, v] of Object.entries(res)) {
      if (r === "coverage") continue;
      tot[r] = tot[r] || [0, 0];
      tot[r][0] += Math.min(v.demand, v.delivered); tot[r][1] += v.demand;
    }
  }
  const ratios = Object.values(tot).filter(([, x]) => x > 0).map(([c, x]) => c / x);
  const cov = Object.entries(d.districts).map(([name, v]) => [name, v.coverage]).sort((a, b) => a[1] - b[1]);
  return { day: d.day, label: `Day ${d.day}`, met: ratios.reduce((a, b) => a + b, 0) / ratios.length,
    worst: cov[0][1], worstName: cov[0][0], truckloads: d.truckloads, delay: d.avg_delay_hr };
}

const stockTotals = (stock) => {
  const t = {};
  for (const c of Object.values(stock || {})) for (const r of RESOURCES) t[r] = (t[r] || 0) + (c[r] || 0);
  return t;
};

export default function SimulationPage({ centres }) {
  const [policy, setPolicy] = useState("mappo");
  const [sim, setSim] = useState(null);         // { state, days: [step results], start: stock totals }
  const [edge, setEdge] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [map, setMap] = useState({});

  const last = sim?.days.length ? sim.days[sim.days.length - 1] : null;
  const mapDay = last ? last.day : 1;
  useEffect(() => {
    Promise.all([api.districts(mapDay), api.roads(mapDay)])
      .then(([districts, roads]) => setMap({ districts, roads })).catch((e) => setErr(String(e)));
  }, [mapDay]);

  const run = async (f) => {
    setBusy(true); setErr(null);
    try { await f(); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const start = () => run(async () => {
    const state = await api.startSim({ policy });
    setSim({ state, days: [], start: stockTotals(state.stock_left) });
  });
  const step = () => run(async () => {
    const r = await api.stepSim(sim.state.session_id);
    setSim({ ...sim, state: r.state, days: [...sim.days, r] });
  });
  const playAll = () => run(async () => {
    let days = [...sim.days], state = sim.state;
    while (!state.done) {
      const r = await api.stepSim(state.session_id);
      days = [...days, r]; state = r.state;
      setSim({ ...sim, state, days });
    }
  });
  const close = () => run(async () => {
    const state = await api.closeRoad(sim.state.session_id, Number(edge));
    setSim({ ...sim, state }); setEdge("");
  });

  const series = useMemo(() => (sim?.days || []).map(dayStats), [sim]);
  const plan = useMemo(() => last && summarisePlan(last.shipments, map.districts, centres), [last, map.districts, centres]);
  const coverage = last ? Object.fromEntries(Object.entries(last.districts).map(([k, v]) => [k, v.coverage])) : null;
  const m = sim?.state?.metrics;
  const left = stockTotals(sim?.state?.stock_left);
  const roadName = (id) => {
    const p = map.roads?.features.find((f) => f.properties.edge_id === id)?.properties;
    return p ? `${p.source} – ${p.target}` : `road ${id}`;
  };
  const ranked = last ? Object.entries(coverage).sort((a, b) => a[1] - b[1]) : [];

  return (
    <>
      <PageHead eyebrow="Step-by-step week" title="7-Day Simulation"
        subtitle="Play the flood week one day at a time through the backend, and close roads while it runs">
        <span className="region">{sim ? (sim.state.done ? "WEEK FINISHED" : `NEXT · DAY ${sim.state.next_day}`) : "NOT STARTED"}</span>
      </PageHead>
      <div className="page">
        <Card>
          <div className="controls" style={{ gridTemplateColumns: "1.2fr auto auto auto" }}>
            <label className="field">Allocation strategy
              <select value={policy} onChange={(e) => setPolicy(e.target.value)} disabled={busy}>
                {STRATEGIES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <button className="btn" onClick={start} disabled={busy}>{sim ? "Restart week" : "Start week"}</button>
            <button className="btn ghost" onClick={step} disabled={busy || !sim || sim.state.done}>
              {sim && !sim.state.done ? `▶ Play day ${sim.state.next_day}` : "▶ Play next day"}
            </button>
            <button className="btn ghost" onClick={playAll} disabled={busy || !sim || sim.state.done}>⏭ Play to end</button>
          </div>
          {sim && !sim.state.done && (
            <div className="controls" style={{ gridTemplateColumns: "1fr auto", marginTop: 16 }}>
              <label className="field">Close a road from today on (live what-if)
                <select value={edge} onChange={(e) => setEdge(e.target.value)}>
                  <option value="">Choose a road…</option>
                  {map.roads?.features.filter((f) => !sim.state.closed_roads.includes(f.properties.edge_id)).map((f) => (
                    <option key={f.properties.edge_id} value={f.properties.edge_id}>{f.properties.source} – {f.properties.target}</option>
                  ))}
                </select>
              </label>
              <button className="btn ghost" onClick={close} disabled={busy || edge === ""}>Close road</button>
            </div>
          )}
          {sim?.state.closed_roads.length > 0 && (
            <div className="chips" style={{ marginTop: 14 }}>
              <span className="note" style={{ margin: 0 }}>Closed by you:</span>
              {sim.state.closed_roads.map((id) => <span key={id} className="chip static" style={{ borderColor: "var(--high)" }}>{roadName(id)}</span>)}
            </div>
          )}
          {!sim && <p className="note" style={{ marginTop: 14 }}>Pick a strategy and press <b>Start week</b>. Each press of <b>Play day</b> runs one
            day of the official 18-24 Aug 2018 week: the centres plan, trucks move on that day's roads, and the map shows the result.</p>}
          {err && <p className="error-box" style={{ marginTop: 14 }}>{err}</p>}
        </Card>

        <div className="stats">
          <Stat icon="pulse" label="Days played" value={`${sim?.days.length || 0} / 7`} sub={last ? dayLabel(last.day) : "press Start week"} />
          <Stat icon="chart" tone="teal" label="Demand met so far" value={m ? pct(m.fulfilment, 1) : "–"} sub="whole week up to now" />
          <Stat icon="shield" tone="red" label="Worst-off district" value={m ? pct(m.worst_district_fulfilment, 1) : "–"} sub={series.length ? `today: ${series[series.length - 1].worstName}` : ""} />
          <Stat icon="network" tone="violet" label="Fairness gap (Gini)" value={m ? m.gini.toFixed(3) : "–"} sub="lower = more equal" />
        </div>

        <div className="grid-2">
          <Card eyebrow={last ? dayLabel(last.day) : "Before the week starts"} title="Simulated day on the map"
            subtitle="Districts coloured by the share of that day's need delivered; blue lines are the day's shipments."
            right={<span className="pill">{last ? `${fmt(last.truckloads)} truckloads` : "Day 1 roads"}</span>}>
            <MapView districts={map.districts} centres={centres} roads={map.roads} flows={plan?.flows}
              colorMode={last ? "coverage" : "class"} coverage={coverage}
              layers={{ basemap: true, roads: true, centres: true, flows: true }} dayKey={`sim-${mapDay}-${sim?.days.length || 0}`} />
          </Card>

          <Card eyebrow="Day by day" title="Demand met and worst-off district">
            {series.length === 0 ? <p className="note">The chart fills in as you play each day.</p> : (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={series} margin={{ top: 8, right: 16, left: 0 }}>
                  <CartesianGrid {...gridProps()} />
                  <XAxis dataKey="label" {...axisProps()} />
                  <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} {...axisProps()} width={44} />
                  <Tooltip {...tooltipProps()} formatter={(v) => `${(v * 100).toFixed(1)}%`} />
                  <Legend wrapperStyle={{ fontSize: 12, color: cssVar("--text-2") }} />
                  <Line dataKey="met" name="Demand met" stroke={cssVar("--series-1")} strokeWidth={2} dot={{ r: 4 }} />
                  <Line dataKey="worst" name="Worst-off district" stroke={cssVar("--series-2")} strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
            {sim && (
              <>
                <h3 style={{ margin: "18px 0 8px", fontSize: 15 }}>Stock left in all centres</h3>
                {RESOURCES.map((r) => (
                  <div className="bar-row" key={r} style={{ gridTemplateColumns: "110px 1fr 50px" }}>
                    <span>{RESOURCE_LABEL[r]}</span>
                    <Meter value={sim.start[r] ? left[r] / sim.start[r] : 0} color="var(--teal-grad)" thin />
                    <b>{sim.start[r] ? pct(left[r] / sim.start[r]) : "–"}</b>
                  </div>
                ))}
              </>
            )}
          </Card>
        </div>

        {last && (
          <div className="grid-2 even">
            <Card eyebrow="Week so far" title="Day-by-day results">
              <table className="t">
                <thead><tr><th>Day</th><th className="num">Met</th><th>Worst-off district</th><th className="num">Trucks</th><th className="num">Delay</th></tr></thead>
                <tbody>{series.map((x) => (
                  <tr key={x.day}><td><b>Day {x.day}</b> <span className="muted">{dayDate(x.day)}</span></td><td className="num">{pct(x.met, 1)}</td>
                    <td>{x.worstName} <span className="muted">{pct(x.worst)}</span></td><td className="num">{fmt(x.truckloads)}</td><td className="num">{x.delay.toFixed(1)} h</td></tr>
                ))}</tbody>
              </table>
            </Card>
            <Card eyebrow={dayLabel(last.day)} title="District coverage today" subtitle="Share of each district's need delivered on the latest simulated day, lowest first.">
              {ranked.map(([d, c]) => (
                <div className="bar-row" key={d} style={{ gridTemplateColumns: "140px 1fr 50px" }}>
                  <span>{d}</span>
                  <Meter value={c} color={c < 0.5 ? "var(--high)" : c < 0.7 ? "var(--medium)" : "var(--teal-grad)"} thin />
                  <b>{pct(c)}</b>
                </div>
              ))}
            </Card>
          </div>
        )}
      </div>
    </>
  );
}
