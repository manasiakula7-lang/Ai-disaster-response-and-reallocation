import React, { useEffect, useMemo, useState } from "react";
import { API, api } from "../api.js";
import { CATEGORY_LABEL, CLASS_LABEL, RESOURCES, RESOURCE_SHORT, dayLabel } from "../constants.js";
import MapView from "../components/MapView.jsx";
import { Card, Meter, PageHead, fmt, pct } from "../components/ui.jsx";
import { summarisePlan } from "../App.jsx";

const POLICIES = [["mappo", "AI agents (MAPPO + fairness)"], ["lp_rationed", "Optimiser (LP fair + rationing)"]];
const STEPS = ["Supply", "Reports", "Dispatch", "Team reports", "Day report"];
const EDIT_COLS = [...RESOURCES, "vehicles"];
const COL_LABEL = { ...RESOURCE_SHORT, water_litres: "Water (L)", vehicles: "Vehicles" };
const amt = (r, v) => (r === "water_litres" ? `${fmt(v / 1000, 1)}k L` : fmt(v, r === "rescue_teams" ? 1 : 0));
const items = (it) => RESOURCES.filter((r) => it[r] > 0).map((r) => `${RESOURCE_SHORT[r]} ${amt(r, it[r])}`).join(" · ");

function Stepper({ active }) {
  return (
    <div className="stepper">
      {STEPS.map((s, i) => (
        <div key={s} className={`step ${i === active ? "on" : i < active ? "done" : ""}`}>
          <span>{i < active ? "✓" : i + 1}</span>{s}
        </div>
      ))}
    </div>
  );
}

function DayReport({ r, sessionId }) {
  return (
    <div>
      <div className="mini-stats">
        <div><div className="k">Need met</div><div className="v">{pct(r.need_met, 1)}</div></div>
        <div><div className="k">Worst-off district</div><div className="v">{pct(r.worst_need_met)}</div><div className="s">{r.worst_district}</div></div>
        <div><div className="k">Fairness gap (Gini)</div><div className="v">{r.gini.toFixed(3)}</div></div>
        <div><div className="k">Operations succeeded</div><div className="v">{r.ops.success}/{r.ops.total}</div>
          <div className="s">{r.ops.success_rate == null ? "none sent" : pct(r.ops.success_rate)}</div></div>
      </div>
      <div className="grid-2 even" style={{ gap: 24, marginTop: 16 }}>
        <div>
          <h3 className="h3">Need met by resource</h3>
          {RESOURCES.map((x) => (
            <div className="bar-row" key={x} style={{ gridTemplateColumns: "90px 1fr 48px" }}>
              <span>{RESOURCE_SHORT[x]}</span><Meter value={r.need_met_by_resource[x]} thin /><b>{pct(r.need_met_by_resource[x])}</b>
            </div>
          ))}
          <p className="note" style={{ marginTop: 10 }}>
            Supply: {r.supply?.label || "–"}. Reports used: {r.reports.dataset} from the dataset, {r.reports.typed} typed.
            {r.neglected.length > 0 && <> Neglected (priority district under 25%): <b>{r.neglected.join(", ")}</b>.</>}
          </p>
        </div>
        <div>
          <h3 className="h3">Failed operations</h3>
          {r.ops.fail === 0 ? <p className="note">None.</p> : (
            <table className="t compact">
              <tbody>{Object.entries(r.ops.fail_reasons).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>
              ))}</tbody>
            </table>
          )}
          {Object.keys(r.not_delivered_after_failures).length > 0 && <p className="note">Returned to centres after failures:{" "}
            {items(r.not_delivered_after_failures)}.</p>}
        </div>
      </div>
      <h3 className="h3" style={{ marginTop: 16 }}>Districts, lowest need met first</h3>
      <table className="t compact">
        <thead><tr><th>District</th><th>Priority</th><th style={{ width: "26%" }}>Need met</th><th className="num">Food sent / need</th>
          <th className="num">Operations ✓ / ✗</th></tr></thead>
        <tbody>{r.districts.map((d) => (
          <tr key={d.district}><td><b>{d.district}</b></td><td><span className={`tag ${d.priority}`}>{CLASS_LABEL[d.priority]}</span></td>
            <td><div style={{ display: "flex", gap: 8, alignItems: "center" }}><div style={{ flex: 1 }}><Meter value={d.need_met} thin /></div><b>{pct(d.need_met)}</b></div></td>
            <td className="num">{fmt(d.delivered.food_kits)} / {fmt(d.need.food_kits)}</td>
            <td className="num">{d.ops_success} / {d.ops_fail}</td></tr>
        ))}</tbody>
      </table>
      <p className="note" style={{ marginTop: 10 }}>
        <a href={`${API}/ops/${sessionId}/log.csv`}>Download the operations log (CSV)</a>
      </p>
    </div>
  );
}

export default function OpsDeskPage({ centres, setDay }) {
  const [policy, setPolicy] = useState("mappo");
  const [st, setSt] = useState(null);
  const [options, setOptions] = useState(null);
  const [choice, setChoice] = useState("none");
  const [editing, setEditing] = useState(false);
  const [edits, setEdits] = useState({});
  const [dataset, setDataset] = useState([]);
  const [filterD, setFilterD] = useState("");
  const [search, setSearch] = useState("");
  const [text, setText] = useState("");
  const [typedD, setTypedD] = useState("");
  const [reasons, setReasons] = useState({});
  const [onlyPending, setOnlyPending] = useState(true);
  const [shownReport, setShownReport] = useState(null);
  const [map, setMap] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const call = async (f) => {
    setBusy(true); setErr(null);
    try { await f(); } catch (e) { setErr(String(e.message || e)); } finally { setBusy(false); }
  };
  const take = (r) => { setSt(r.state); return r.result; };
  const start = () => call(async () => {
    take(await api.opsStart(policy)); setShownReport(null); setEdits({}); setEditing(false);
  });
  useEffect(() => { start(); }, []);

  // New day: fresh supply options, dataset reports and map.
  useEffect(() => {
    if (!st || st.done) return;
    setDay?.(st.day);
    api.opsSupplyOptions(st.session_id).then(setOptions).catch((e) => setErr(String(e)));
    Promise.all([api.districts(st.day), api.roads(st.day)]).then(([districts, roads]) => setMap({ districts, roads }));
    setEdits({}); setChoice("none");
  }, [st?.session_id, st?.day]);
  useEffect(() => {
    if (!st || st.phase !== "operate") return;
    api.opsDataset(st.session_id, filterD, search).then(setDataset).catch((e) => setErr(String(e)));
  }, [st?.session_id, st?.day, st?.phase, filterD, search, st?.used_reports.length]);

  const confirmSupply = () => call(async () => {
    const overrides = Object.fromEntries(Object.entries(edits).map(([c, v]) => [c, Object.fromEntries(
      Object.entries(v).filter(([, x]) => x !== "" && x != null).map(([k, x]) => [k, Number(x)]))]));
    take(await api.opsSupply(st.session_id, choice, overrides)); setEditing(false);
  });
  const addReport = (body) => call(async () => { take(await api.opsReport(st.session_id, body)); });
  const dispatch = () => call(async () => { take(await api.opsDispatch(st.session_id)); });
  const outcome = (op, status) => call(async () => {
    take(await api.opsOutcome(st.session_id, op, { status, reason: status === "fail" ? (reasons[op] || st.fail_reasons[0]) : null }));
  });
  const bulk = (allSuccess) => call(async () => { take(await api.opsSimulate(st.session_id, allSuccess)); });
  const closeDay = () => call(async () => {
    const force = st.pending > 0 && window.confirm(`${st.pending} operations have no team report. Count them as failed and close the day?`);
    if (st.pending > 0 && !force) return;
    const r = take(await api.opsClose(st.session_id, force));
    setShownReport(r.day);
  });

  const opt = options?.find((o) => o.key === choice);
  const names = map.districts?.features.map((f) => f.properties.name).sort() || [];
  const roads = useMemo(() => map.roads && st ? {
    ...map.roads,
    features: map.roads.features.map((f) => ({ ...f, properties: { ...f.properties, status: st.roads[String(f.properties.edge_id)] || f.properties.status } })),
  } : map.roads, [map.roads, st]);
  const flows = useMemo(() => {
    if (!st || !map.districts) return null;
    const ships = st.plan.flatMap((p) => Object.entries(p.items).map(([resource, amount]) => ({ centre: p.centre, district: p.district, resource, amount })));
    return summarisePlan(ships, map.districts, centres)?.flows;
  }, [st, map.districts, centres]);
  const preview = useMemo(() => {
    const by = {};
    for (const p of st?.plan || []) {
      const d = (by[p.district] = by[p.district] || { district: p.district, centres: 0, hours: 0, items: {} });
      d.centres += 1; d.hours = Math.max(d.hours, p.hours);
      for (const [r, a] of Object.entries(p.items)) d.items[r] = (d.items[r] || 0) + a;
    }
    return Object.values(by).sort((a, b) => (st.districts[b.district]?.severity || 0) - (st.districts[a.district]?.severity || 0));
  }, [st]);
  const coverage = st ? Object.fromEntries(Object.entries(st.districts).map(([d, v]) => [d, v.need_met_so_far])) : null;

  const step = !st ? 0 : st.done ? 4 : st.phase === "supply" ? 0 : st.operations.length === 0 ? (st.reports.length ? 2 : 1)
    : st.pending > 0 ? 3 : st.waves_left > 0 ? 2 : 4;
  const report = st?.day_reports.find((r) => r.day === shownReport) || (st?.done ? st.day_reports[st.day_reports.length - 1] : null);
  const ops = (st?.operations || []).filter((o) => !onlyPending || o.status === "in_progress");

  return (
    <>
      <PageHead eyebrow="Run the week by hand" title="Operations Desk"
        subtitle="Choose the supply, add reports, send convoys, log what the teams report, then close the day">
        <span className="region">{st ? (st.done ? "WEEK FINISHED" : dayLabel(st.day).toUpperCase()) : "STARTING"}</span>
      </PageHead>
      <div className="page">
        <Card>
          <div className="controls" style={{ gridTemplateColumns: "minmax(220px, 1fr) auto 2fr" }}>
            <label className="field">Allocation strategy
              <select value={policy} onChange={(e) => setPolicy(e.target.value)} disabled={busy}>
                {POLICIES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <button className="btn ghost" onClick={start} disabled={busy}>Start a new week</button>
            <Stepper active={step} />
          </div>
          {err && <p className="error-box" style={{ marginTop: 14 }}>{err}</p>}
        </Card>

        {st && !st.done && (
          <Card eyebrow={`Step 1 · ${dayLabel(st.day)}`} title="Today's supply"
            right={st.supply && <span className="pill">{st.supply.label}{st.supply.edited_centres.length ? ` · ${st.supply.edited_centres.length} centres edited` : ""}</span>}>
            {st.phase === "operate" && st.waves_left < 4 ? (
              <p className="note" style={{ margin: 0 }}>Fixed for today: {RESOURCES.map((r) => `${RESOURCE_SHORT[r]} ${amt(r, st.supply.totals[r])}`).join(" · ")}.
                Stock left now: {RESOURCES.map((r) => `${RESOURCE_SHORT[r]} ${amt(r, st.stock_left[r])}`).join(" · ")}.</p>
            ) : (
              <>
                <div className="option-grid">
                  {options?.map((o) => (
                    <button key={o.key} className={`option ${choice === o.key ? "on" : ""}`} onClick={() => setChoice(o.key)}>
                      <b>{o.label}</b><span>{o.detail}</span>
                      <small>Food {fmt(o.totals.food_kits)} · Water {fmt(o.totals.water_litres / 1000)}k L · Medicine {fmt(o.totals.medicine_kits)} · {fmt(o.totals.rescue_teams)} teams</small>
                    </button>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
                  <button className="btn" onClick={confirmSupply} disabled={busy || !opt}>{st.supply ? "Change supply" : "Confirm supply"}</button>
                  <button className="btn ghost" onClick={() => setEditing(!editing)}>{editing ? "Hide centre numbers" : "Edit centre numbers"}</button>
                </div>
                {editing && opt && (
                  <div className="table-scroll" style={{ marginTop: 14 }}>
                    <table className="t compact">
                      <thead><tr><th>Centre</th>{EDIT_COLS.map((k) => <th key={k} className="num">{COL_LABEL[k]}</th>)}</tr></thead>
                      <tbody>{Object.entries(opt.centres).map(([c, row]) => (
                        <tr key={c}><td><b>{c}</b> <span className="muted">{centres?.features.find((f) => f.properties.centre_id === c)?.properties.district}</span></td>
                          {EDIT_COLS.map((k) => (
                            <td key={k} className="num"><input className="cell-input" type="number" min="0" aria-label={`${c} ${COL_LABEL[k]}`}
                              value={edits[c]?.[k] ?? Math.round(row[k])}
                              onChange={(e) => setEdits({ ...edits, [c]: { ...edits[c], [k]: e.target.value } })} /></td>
                          ))}</tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </Card>
        )}

        {st && st.phase === "operate" && (
          <div className="grid-2 even">
            <Card eyebrow="Step 2" title="Add disaster reports" right={<span className="pill">{dataset.length} from the dataset</span>}>
              <div className="controls" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <label className="field">District
                  <select value={filterD} onChange={(e) => setFilterD(e.target.value)}>
                    <option value="">All districts</option>
                    {names.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <label className="field">Search
                  <input className="text-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="e.g. water, rescue, Aluva" />
                </label>
              </div>
              <div className="scroll-list" style={{ maxHeight: 360, marginTop: 12 }}>
                {dataset.length === 0 && <p className="note">No dataset reports match.</p>}
                {dataset.map((x) => (
                  <div key={x.tweet_id} className="pick-row">
                    <div>
                      <div className="top">{x.time} · <b>{x.district}</b> · {CATEGORY_LABEL[x.category] || x.category} · urgency {x.urgency.toFixed(2)}</div>
                      <div className="txt">{x.text}</div>
                    </div>
                    <button className="btn ghost sm" onClick={() => addReport({ tweet_id: x.tweet_id })} disabled={busy || x.added}>{x.added ? "Added" : "Add"}</button>
                  </div>
                ))}
              </div>
              <label className="field" style={{ marginTop: 14 }}>Or type a new report
                <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. 30 families stranded in Kuttanad, need food and water" />
              </label>
              <div className="controls" style={{ gridTemplateColumns: "1fr auto", marginTop: 10 }}>
                <label className="field">District
                  <select value={typedD} onChange={(e) => setTypedD(e.target.value)}>
                    <option value="">Find it from the text</option>
                    {names.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <button className="btn" disabled={busy || text.trim().length < 3}
                  onClick={() => { addReport({ text, district: typedD || null }); setText(""); }}>Add typed report</button>
              </div>
            </Card>

            <Card eyebrow="Added today" title={`${st.reports.length} reports`}
              subtitle="A dataset report corrects its district's need estimate halfway toward the true need, so it can go up or down. A typed report adds the people it mentions as new need.">
              {st.reports.length === 0 ? <p className="note">Reports you add appear here with what they changed. Without reports the planner works from the morning forecast.</p> : (
                <div className="scroll-list" style={{ maxHeight: 520 }}>
                  {[...st.reports].reverse().map((x) => (
                    <div key={x.seq} className="pick-row">
                      <div>
                        <div className="top"><b>{x.district || "No district"}</b> · {x.source === "dataset" ? `dataset, ${x.posted}` : "typed"} · {CATEGORY_LABEL[x.category] || x.category} · urgency {x.urgency.toFixed(2)}</div>
                        <div className="txt">{x.text.slice(0, 160)}</div>
                        <div className="txt muted">{x.estimate_change && Object.keys(x.estimate_change).length
                          ? `Need estimate ${Object.entries(x.estimate_change).map(([r, v]) => `${RESOURCE_SHORT[r]} ${v > 0 ? "+" : "−"}${amt(r, Math.abs(v))}`).join(", ")}`
                          : x.outcome}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}

        {st && st.phase === "operate" && (
          <div className="grid-2">
            <Card eyebrow="Step 3" title={st.waves_left ? `Next convoys: ${st.next_wave} wave` : "All four waves sent"}
              subtitle={st.waves_left ? `${st.policy_label} plans each wave with the stock, trucks and need estimate at that moment. One convoy per district.` : "Close the day once the teams have reported."}
              right={st.waves_left > 0 && <button className="btn" onClick={dispatch} disabled={busy || preview.length === 0}>Send {st.next_wave} wave</button>}>
              {st.waves_left > 0 && (preview.length === 0 ? <p className="note">Nothing to send: no stock or trucks left, or no remaining need.</p> : (
                <div className="table-scroll">
                  <table className="t compact">
                    <thead><tr><th>District</th><th className="num">Centres</th>{RESOURCES.map((r) => <th key={r} className="num">{RESOURCE_SHORT[r]}</th>)}<th className="num">Arrives in</th></tr></thead>
                    <tbody>{preview.map((p) => (
                      <tr key={p.district}><td><b>{p.district}</b></td><td className="num">{p.centres}</td>
                        {RESOURCES.map((r) => <td key={r} className="num">{p.items[r] ? amt(r, p.items[r]) : "–"}</td>)}
                        <td className="num">{p.hours.toFixed(1)} h</td></tr>
                    ))}</tbody>
                  </table>
                </div>
              ))}
            </Card>
            <Card eyebrow="Today" title="Need met so far" subtitle="Districts coloured by the share of today's need confirmed delivered. Blue lines: the next wave.">
              <MapView districts={map.districts} centres={centres} roads={roads} flows={flows} colorMode="coverage" coverage={coverage}
                layers={{ basemap: true, roads: true, centres: true, flows: true }} dayKey={`ops-${st.day}-${st.last_seq}`} />
            </Card>
          </div>
        )}

        {st && st.phase === "operate" && st.operations.length > 0 && (
          <Card eyebrow="Step 4" title="Team reports" subtitle="Each convoy's team reports success or failure. A failed convoy's supplies go back to the centres and the next wave plans that need again."
            right={<span className="pill">{st.pending} waiting</span>}>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
              <button className="btn ghost sm" onClick={() => bulk(true)} disabled={busy || !st.pending}>Mark all waiting as succeeded</button>
              <button className="btn ghost sm" onClick={() => bulk(false)} disabled={busy || !st.pending}>Simulate team reports</button>
              <label className="check"><input type="checkbox" checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} /> Waiting only</label>
            </div>
            <div className="table-scroll">
              <table className="t compact">
                <thead><tr><th>Operation</th><th>District</th><th>Supplies</th><th>From</th><th className="num">Arrives in</th><th>Team report</th></tr></thead>
                <tbody>{ops.map((o) => (
                  <tr key={o.op_id}>
                    <td><b>{o.op_id}</b><div className="muted">{o.wave}</div></td>
                    <td><b>{o.district}</b></td>
                    <td>{items(o.items)}</td>
                    <td title={o.sources.map((x) => `${x.centre}: ${x.path.join(" → ")}`).join("\n")}>{o.centres.length} centres{o.slowed_legs ? <div className="muted">{o.slowed_legs} slowed road legs</div> : null}</td>
                    <td className="num">{o.hours.toFixed(1)} h</td>
                    <td>{o.status === "in_progress" ? (
                      <div className="outcome">
                        <button className="btn sm ok" onClick={() => outcome(o.op_id, "success")} disabled={busy}>✓ Success</button>
                        <select aria-label={`Failure reason for ${o.op_id}`} value={reasons[o.op_id] || st.fail_reasons[0]}
                          onChange={(e) => setReasons({ ...reasons, [o.op_id]: e.target.value })}>
                          {st.fail_reasons.filter((r) => r !== "No report from team").map((r) => <option key={r}>{r}</option>)}
                        </select>
                        <button className="btn sm bad" onClick={() => outcome(o.op_id, "fail")} disabled={busy}>✗ Fail</button>
                      </div>
                    ) : <span className={`tag ${o.status === "success" ? "low" : "high"}`}>{o.status === "success" ? "Succeeded" : `Failed: ${o.reason}`}</span>}</td>
                  </tr>
                ))}</tbody>
              </table>
              {ops.length === 0 && <p className="note">All teams have reported.</p>}
            </div>
          </Card>
        )}

        {st && (st.phase === "operate" || st.day_reports.length > 0) && (
          <Card eyebrow="Step 5" title={report ? `Day ${report.day} report` : "Close the day"}
            subtitle={report ? `${report.policy}. Delivered means confirmed by a team's success report; the need is the simulated true need.` : "When the teams have reported, close the day to get its report. Leftover stock carries over to tomorrow."}
            right={<div className="chips">
              {st.day_reports.map((r) => <button key={r.day} className={`chip ${report?.day === r.day ? "on" : ""}`} onClick={() => setShownReport(r.day)}>Day {r.day}</button>)}
              {st.phase === "operate" && <button className="btn" onClick={closeDay} disabled={busy || st.operations.length === 0}>Close day {st.day}</button>}
            </div>}>
            {report ? <DayReport r={report} sessionId={st.session_id} /> : <p className="note" style={{ margin: 0 }}>No day closed yet.</p>}
          </Card>
        )}

        {st?.week && (
          <Card eyebrow="So far" title={st.done ? "Week report" : `Week so far (${st.day_reports.length} days)`}>
            <div className="mini-stats">
              <div><div className="k">Need met</div><div className="v">{pct(st.week.fulfilment, 1)}</div></div>
              <div><div className="k">Worst-off district</div><div className="v">{pct(st.week.worst_district_fulfilment)}</div></div>
              <div><div className="k">Fairness gap (Gini)</div><div className="v">{st.week.gini.toFixed(3)}</div></div>
              <div><div className="k">Operations succeeded</div><div className="v">
                {st.day_reports.reduce((a, r) => a + r.ops.success, 0)}/{st.day_reports.reduce((a, r) => a + r.ops.total, 0)}</div></div>
            </div>
            <table className="t compact" style={{ marginTop: 14 }}>
              <thead><tr><th>Day</th><th>Supply</th><th className="num">Reports</th><th className="num">Need met</th><th>Worst-off</th><th className="num">Gini</th><th className="num">Succeeded</th></tr></thead>
              <tbody>{st.day_reports.map((r) => (
                <tr key={r.day}><td>{dayLabel(r.day)}</td><td>{r.supply?.label}</td><td className="num">{r.reports.dataset + r.reports.typed}</td>
                  <td className="num">{pct(r.need_met, 1)}</td><td>{r.worst_district} {pct(r.worst_need_met)}</td><td className="num">{r.gini.toFixed(3)}</td>
                  <td className="num">{r.ops.success}/{r.ops.total}</td></tr>
              ))}</tbody>
            </table>
          </Card>
        )}
      </div>
    </>
  );
}
