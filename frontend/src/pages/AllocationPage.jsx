import React, { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { RESOURCES, RESOURCE_LABEL, RESOURCE_SHORT, RESOURCE_UNIT, STRATEGIES } from "../constants.js";
import { axisProps, cssVar, gridProps, tooltipProps } from "../theme.js";
import { Card, Meter, PageHead, Stat, fmt, pct } from "../components/ui.jsx";

const SCENARIOS = [
  { key: "official", label: "Official flood week (as it happened)", body: {} },
  { key: "shortage", label: "Supply shortage: half the stock", body: { stock_factor: 0.5 } },
  { key: "surge", label: "Bigger flood: 50% more demand", body: { demand_factor: 1.5 } },
  { key: "roads", label: "Main roads cut: Alappuzha–Ernakulam and Ernakulam–Thrissur", body: { closed_edges: [0, 6] } },
  { key: "worst", label: "Worst case: half the stock and 50% more demand", body: { stock_factor: 0.5, demand_factor: 1.5 } },
  { key: "custom", label: "Custom what-if: set stock, demand and roads yourself", body: null },
];
const NAME = Object.fromEntries(STRATEGIES);
const SHORT = { mappo: "AI agents", lp_rationed: "Optimiser + rationing", lp_fair: "Optimiser (fair)", lp: "Optimiser (max)", greedy: "Greedy", local_first: "Local-first" };

function Bars({ a, b, la, lb }) {
  const ra = a.demand ? a.delivered / a.demand : 1, rb = b.demand ? b.delivered / b.demand : 1;
  return (
    <>
      <div className="bar-row"><span>{la}</span><Meter value={ra} color="var(--accent-grad)" /><b>{pct(ra, 1)}</b></div>
      <div className="bar-row"><span>{lb}</span><Meter value={rb} color="var(--teal-grad)" /><b>{pct(rb, 1)}</b></div>
    </>
  );
}

export default function AllocationPage({ roads }) {
  const [scenario, setScenario] = useState("official");
  const [custom, setCustom] = useState({ stock: 100, demand: 100, closed: [] });
  const [policy, setPolicy] = useState("mappo");
  const [baseline, setBaseline] = useState("lp");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [view, setView] = useState("policy");
  const [resource, setResource] = useState("all");

  const run = async () => {
    setBusy(true); setErr(null);
    try {
      const body = SCENARIOS.find((s) => s.key === scenario).body
        || { stock_factor: custom.stock / 100, demand_factor: custom.demand / 100, closed_edges: custom.closed };
      setRes(await api.evaluate({ policy, baseline, ...body }));
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  useEffect(() => { run(); }, []);

  const P = res?.results[res.policy], B = res?.results[res.baseline];
  const shown = res ? (view === "policy" ? P : B) : null;
  const dist = shown ? Object.entries(shown.per_district).map(([d, v]) => {
    const rs = resource === "all" ? RESOURCES : [resource];
    const ratios = rs.filter((r) => v[r].demand > 0).map((r) => v[r].delivered / v[r].demand);
    const tot = rs.reduce((s, r) => s + v[r].demand, 0), got = rs.reduce((s, r) => s + v[r].delivered, 0);
    return { d, cov: ratios.length ? ratios.reduce((a, b) => a + b, 0) / ratios.length : 1, tot, got, vuln: res.vulnerability[d] };
  }).sort((a, b) => a.cov - b.cov) : [];
  const daily = P ? P.daily.map((x, i) => ({ day: `Day ${x.day}`, a: x.met, b: B.daily[i]?.met })) : [];
  const delta = (k, higher = true) => {
    const v = P.metrics[k] - B.metrics[k];
    if (Math.abs(v) < 1e-9) return "same as the comparison";
    const good = (v > 0) === higher;
    return <span className={good ? "up" : "down"}>{v > 0 ? "+" : "−"}{k === "gini" || k === "avg_delay_hr" ? Math.abs(v).toFixed(3) : `${(Math.abs(v) * 100).toFixed(1)} pts`} vs {SHORT[res.baseline]}</span>;
  };

  return (
    <>
      <PageHead eyebrow="Resource allocation" title="Allocation Simulator"
        subtitle="Play the whole flood week with two strategies on the same scenario and compare who got what">
        <span className="region">KERALA · 7-DAY WEEK</span>
      </PageHead>
      <div className="page">
        <Card>
          <div className="controls" style={{ gridTemplateColumns: "1.3fr 1fr 1fr auto" }}>
            <label className="field">Disaster scenario
              <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
                {SCENARIOS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </label>
            <label className="field">Allocation strategy
              <select value={policy} onChange={(e) => setPolicy(e.target.value)}>
                {STRATEGIES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="field">Compare with
              <select value={baseline} onChange={(e) => setBaseline(e.target.value)}>
                {STRATEGIES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <button className="btn" onClick={run} disabled={busy}>{busy ? <><span className="spinner" />Running…</> : "Run simulation"}</button>
          </div>
          {scenario === "custom" && (
            <div style={{ marginTop: 18 }}>
              <div className="grid-2 even" style={{ gap: 24, marginBottom: 14 }}>
                <label className="field">Stock in the centres: {custom.stock}%
                  <input type="range" min="20" max="200" step="10" value={custom.stock}
                    onChange={(e) => setCustom({ ...custom, stock: Number(e.target.value) })} />
                </label>
                <label className="field">Demand (flood size): {custom.demand}%
                  <input type="range" min="50" max="250" step="10" value={custom.demand}
                    onChange={(e) => setCustom({ ...custom, demand: Number(e.target.value) })} />
                </label>
              </div>
              <div className="field" style={{ marginBottom: 8 }}>Close roads for the whole week</div>
              <div className="chips">
                {roads?.features.map((f) => {
                  const id = f.properties.edge_id, on = custom.closed.includes(id);
                  return (
                    <button key={id} className={`chip ${on ? "on" : ""}`} aria-pressed={on}
                      style={on ? { borderColor: "var(--high)" } : undefined}
                      onClick={() => setCustom({ ...custom, closed: on ? custom.closed.filter((x) => x !== id) : [...custom.closed, id] })}>
                      {on ? "✕ " : ""}{f.properties.source} – {f.properties.target}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {err && <p className="error-box" style={{ marginTop: 14 }}>{err}</p>}
        </Card>

        {P && (
          <>
            <div className="stats">
              <Stat label="Demand met" value={pct(P.metrics.fulfilment, 1)} sub={delta("fulfilment")} />
              <Stat label="Fairness gap (Gini)" value={P.metrics.gini.toFixed(3)} sub={<>Lower = more equal · {delta("gini", false)}</>} />
              <Stat label="Worst-off district" value={pct(P.metrics.worst_district_fulfilment, 1)} sub={delta("worst_district_fulfilment")} />
              <Stat label="Average delivery time" value={P.metrics.avg_delay_hr.toFixed(1)} unit="h" sub={delta("avg_delay_hr", false)} />
            </div>

            <Card eyebrow="Model performance" title={`${NAME[res.policy]} vs ${NAME[res.baseline]}`}
              subtitle="Share of each resource's demand delivered over the week, same scenario for both.">
              <div className="legend-row">
                <span><span className="dot" style={{ background: "var(--series-1)" }} />{SHORT[res.policy]}</span>
                <span><span className="dot" style={{ background: "var(--series-2)" }} />{SHORT[res.baseline]}</span>
              </div>
              <div className="grid-2 even" style={{ gap: 14 }}>
                {RESOURCES.map((r) => (
                  <div className="res-card" key={r}>
                    <div className="head"><b>{RESOURCE_LABEL[r]}</b><span>Demand: {fmt(P.per_resource[r].demand)} {RESOURCE_UNIT[r]}</span></div>
                    <Bars a={P.per_resource[r]} b={B.per_resource[r]} la={SHORT[res.policy]} lb={SHORT[res.baseline]} />
                    <div className="foot">Delivered: {fmt(P.per_resource[r].delivered)} vs {fmt(B.per_resource[r].delivered)} {RESOURCE_UNIT[r]}</div>
                  </div>
                ))}
              </div>
              <h3 style={{ margin: "22px 0 4px", fontSize: 16 }}>Demand met, day by day</h3>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={daily} margin={{ top: 10, right: 20, left: 0 }}>
                  <CartesianGrid {...gridProps()} />
                  <XAxis dataKey="day" {...axisProps()} />
                  <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} {...axisProps()} width={44} />
                  <Tooltip {...tooltipProps()} formatter={(v) => `${(v * 100).toFixed(1)}%`} />
                  <Legend wrapperStyle={{ fontSize: 12, color: cssVar("--text-2") }} />
                  <Line dataKey="a" name={SHORT[res.policy]} stroke={cssVar("--series-1")} strokeWidth={2} dot={{ r: 4 }} />
                  <Line dataKey="b" name={SHORT[res.baseline]} stroke={cssVar("--series-2")} strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </Card>

            <Card eyebrow="Equitable distribution" title="District-level allocation analysis"
              subtitle={<>Viewing results from: <b>{NAME[view === "policy" ? res.policy : res.baseline]}</b>. Worst-served first.</>}
              right={
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <div className="chips">
                    <button className={`chip ${view === "policy" ? "on" : ""}`} onClick={() => setView("policy")}>{SHORT[res.policy]}</button>
                    <button className={`chip ${view === "baseline" ? "on" : ""}`} onClick={() => setView("baseline")}>{SHORT[res.baseline]}</button>
                  </div>
                  <label className="field" style={{ minWidth: 150 }}>
                    <select value={resource} onChange={(e) => setResource(e.target.value)} aria-label="Resource">
                      <option value="all">All resources</option>
                      {RESOURCES.map((r) => <option key={r} value={r}>{RESOURCE_SHORT[r]}</option>)}
                    </select>
                  </label>
                </div>
              }>
              <div className="grid-3">
                {dist.map((x) => (
                  <div className="dist-card" key={x.d}>
                    <div className="head"><b>{x.d}</b><span>Vulnerability {x.vuln.toFixed(2)}</span></div>
                    <div className="val">
                      <Meter value={x.cov} color={x.cov < 0.5 ? "var(--high)" : x.cov < 0.7 ? "var(--medium)" : "var(--teal-grad)"} />
                      <b>{pct(x.cov, 1)}</b>
                    </div>
                    {resource !== "all" && <div className="sub">{fmt(x.got)} / {fmt(x.tot)} {RESOURCE_UNIT[resource]} · {fmt(x.tot - x.got)} unmet</div>}
                  </div>
                ))}
              </div>
            </Card>

            <Card eyebrow="Allocation summary" title="Delivered and unmet resources"
              subtitle={`${NAME[res.policy]}, whole week.`}>
              <div className="grid-2 even" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 14 }}>
                {RESOURCES.map((r) => {
                  const x = P.per_resource[r], s = x.demand ? x.delivered / x.demand : 1;
                  return (
                    <div className="sum-card" key={r}>
                      <div className="k">{RESOURCE_SHORT[r]}</div>
                      <div className="v">{fmt(r === "water_litres" ? x.delivered / 1000 : x.delivered, r === "rescue_teams" ? 1 : 0)}<small>{r === "water_litres" ? "k litres" : RESOURCE_UNIT[r]}</small></div>
                      <Meter value={s} color="var(--accent-grad)" thin />
                      <div className="s">{fmt(r === "water_litres" ? (x.demand - x.delivered) / 1000 : x.demand - x.delivered)}{r === "water_litres" ? "k" : ""} unmet · {pct(s, 1)} satisfied</div>
                    </div>
                  );
                })}
              </div>
            </Card>

            <Card eyebrow="Adaptive response" title="Disaster event timeline"
              subtitle="What changed each day of the week. Red = blocked, amber = slowed, teal = reopened. Both strategies replan around these.">
              <div className="tl">
                {[...new Set(res.timeline.map((e) => e.day))].map((day) => {
                  const ev = res.timeline.filter((e) => e.day === day);
                  const roads = ev.filter((e) => e.kind === "road");
                  const surges = ev.filter((e) => e.kind !== "road");
                  return (
                    <div className="tl-item" key={day}>
                      <span className="when">Day {day}</span>
                      <div>
                        {surges.length > 0 && <>
                          <b>Demand surge in {surges.map((e) => e.district).join(", ")}</b>
                          <div className="chips" style={{ margin: "6px 0 8px" }}>
                            {surges.map((e) => (
                              <span key={e.district} className="chip static">{e.district}: {RESOURCES.filter((r) => e.change[r] > 0).map((r) =>
                                `${RESOURCE_SHORT[r]} +${fmt(r === "water_litres" ? e.change[r] / 1000 : e.change[r], 1)}${r === "water_litres" ? "k L" : ""}`).join(", ")}</span>
                            ))}
                          </div></>}
                        {roads.length > 0 && <>
                          <b>{roads.length} road change{roads.length > 1 ? "s" : ""}</b>
                          <div className="chips" style={{ marginTop: 6 }}>
                            {roads.map((e, i) => (
                              <span key={i} className="chip static" style={{ borderColor: e.status === "blocked" ? "var(--high)" : e.status === "slowed" ? "var(--medium)" : "var(--teal)" }}>
                                {e.detail} · {e.status === "open" ? "reopened" : e.status}{e.closed_by_user ? " (scenario)" : ""}
                              </span>
                            ))}
                          </div></>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </>
        )}
      </div>
    </>
  );
}
