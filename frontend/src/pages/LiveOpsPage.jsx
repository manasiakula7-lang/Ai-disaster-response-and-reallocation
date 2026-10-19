import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { CATEGORY_LABEL, RESOURCES, RESOURCE_SHORT, RESOURCE_UNIT, dayLabel } from "../constants.js";
import Icon from "../components/icons.jsx";
import MapView from "../components/MapView.jsx";
import { Card, Meter, PageHead, Stat, fmt, pct } from "../components/ui.jsx";
import { summarisePlan } from "../App.jsx";

const SPEEDS = [[0.25, "15 min / s"], [1, "1 hour / s"], [3, "3 hours / s"]];
const POLICIES = [["mappo", "AI agents (MAPPO + fairness)"], ["lp_rationed", "Optimiser + rationing"]];
const NEED_WORD = { food: "Food", water: "Water", medicine: "Medicine", rescue: "Rescue", shelter: "Shelter" };
const EXAMPLES = [
  "Urgent: 40 families stranded on rooftops in Chengannur, no food or drinking water since yesterday. Please send boats",
  "Relief camp at Aluva school has 600 people, running out of drinking water and medicines for children",
  "Elderly patients need insulin and dialysis at Ranni, roads cut off, please help",
  "Water level rising fast near Chalakudy, about 150 people trapped, need rescue teams immediately",
];
const LOOK = {
  report: ["tweet", "low", "Tweet"], manual: ["pulse", "", "Field report"], alert: ["alerts", "", "Alert"],
  dispatch: ["layers", "low", "Dispatch"], road: ["road", "mid", "Road"], day: ["home", "low", "Day"], day_end: ["chart", "low", "Day closed"],
};
const FILTER_LABEL = { report: "Tweets", manual: "Field reports", alert: "Alerts", road: "Roads", dispatch: "Dispatches", day: "Day start/end" };
const kindOf = (t) => (t.startsWith("road_") ? "road" : t);
const amt = (r, v) => (r === "water_litres" ? `${fmt(v / 1000, 1)}k L`
  : `${fmt(v, r === "rescue_teams" ? 1 : 0)} ${Math.abs(v - 1) < 1e-9 ? RESOURCE_UNIT[r].replace(/s$/, "") : RESOURCE_UNIT[r]}`);
const NEED_NAME = { food_kits: "food", water_litres: "water", medicine_kits: "medicine", rescue_teams: "rescue" };
const named = (r, v) => (r === "water_litres" ? `${amt(r, v)} of water` : `${amt(r, v).replace(" ", ` ${NEED_NAME[r]} `)}`);
const signed = (r, v) => `${v > 0 ? "+" : "−"}${amt(r, Math.abs(v))}`;

function ChangeList({ replan }) {
  if (!replan) return <p className="note">Pick a report or road change in the feed to see how it moved the plan.</p>;
  if (!replan.n_changes) return <p className="note">No shipment for the {replan.wave} wave changed: the plan already covered this, or
    stock and trucks were fully committed.</p>;
  return (
    <>
      <div className="chips" style={{ marginBottom: 12 }}>
        {Object.entries(replan.by_district).map(([d, v]) => (
          <span key={d} className="chip static">{d}: {Object.entries(v).map(([r, x]) => `${RESOURCE_SHORT[r]} ${signed(r, x)}`).join(", ")}</span>
        ))}
      </div>
      <table className="t">
        <thead><tr><th>Centre → district</th><th>Resource</th><th className="num">Before</th><th className="num">After</th></tr></thead>
        <tbody>{replan.changes.map((c, i) => (
          <tr key={i}><td><b>{c.centre}</b> → {c.district}</td><td>{RESOURCE_SHORT[c.resource]}</td>
            <td className="num muted">{amt(c.resource, c.before)}</td>
            <td className="num"><b className={c.after > c.before ? "up" : "down"}>{amt(c.resource, c.after)}</b></td></tr>
        ))}</tbody>
      </table>
      {replan.n_changes > replan.changes.length && <p className="note">…and {replan.n_changes - replan.changes.length} smaller changes.</p>}
    </>
  );
}

export default function LiveOpsPage({ centres, go }) {
  const [policy, setPolicy] = useState("mappo");
  const [st, setSt] = useState(null);
  const [events, setEvents] = useState([]);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [map, setMap] = useState({});
  const [text, setText] = useState("");
  const [district, setDistrict] = useState("");
  const [result, setResult] = useState(null);
  const [picked, setPicked] = useState(null);
  const [filter, setFilter] = useState({ report: true, manual: true, alert: true, road: true, dispatch: true, day: true, day_end: true });
  const inFlight = useRef(false);

  const take = (r) => {
    setSt(r.state);
    if (r.events?.length) setEvents((ev) => [...ev, ...r.events].slice(-600));
  };
  const call = async (f, quiet) => {
    if (inFlight.current) return;
    inFlight.current = true; if (!quiet) setBusy(true); setErr(null);
    try { await f(); } catch (e) { setErr(String(e.message || e)); setPlaying(false); } finally { inFlight.current = false; setBusy(false); }
  };
  const start = () => call(async () => {
    setPlaying(false); setEvents([]); setResult(null); setPicked(null);
    take(await api.liveStart(policy));
  });
  useEffect(() => { start(); }, []);   // a session is ready when the page opens

  useEffect(() => {
    if (!playing || !st) return undefined;
    const t = setInterval(() => call(async () => {
      const r = await api.liveAdvance(st.session_id, { hours: speed });
      take(r);
      if (r.state.done) setPlaying(false);
    }, true), 1000);
    return () => clearInterval(t);
  }, [playing, speed, st?.session_id]);

  useEffect(() => {
    if (!st) return;
    Promise.all([api.districts(st.day), api.roads(st.day)]).then(([districts, roads]) => setMap({ districts, roads }))
      .catch((e) => setErr(String(e)));
  }, [st?.day]);

  const step = () => call(async () => take(await api.liveAdvance(st.session_id, { until: "event" })));
  const send = async () => {
    while (inFlight.current) await new Promise((ok) => setTimeout(ok, 60));   // let a clock tick finish
    const lastSeq = events.length ? events[events.length - 1].seq : 0;
    await call(async () => {
      const r = await api.liveReport(st.session_id, text, district);
      take(await api.liveState(st.session_id, lastSeq));
      setResult(r); setPicked(r.event);
    });
  };

  const roads = useMemo(() => map.roads && st ? {
    ...map.roads,
    features: map.roads.features.map((f) => ({ ...f, properties: { ...f.properties, status: st.roads[String(f.properties.edge_id)] || f.properties.status } })),
  } : map.roads, [map.roads, st]);
  const plan = useMemo(() => st && map.districts && summarisePlan(st.plan, map.districts, centres), [st, map.districts, centres]);
  const coverage = st ? Object.fromEntries(Object.entries(st.districts).map(([d, v]) => [d, v.coverage_so_far])) : null;
  const lastReport = [...events].reverse().find((e) => e.type === "report" || e.type === "manual");
  const focus = picked || [...events].reverse().find((e) => e.replan);
  const shown = [...events].reverse().filter((e) => filter[kindOf(e.type)]).slice(0, 120);
  const reportsIn = (st?.counts.report || 0) + (st?.counts.manual || 0);
  const replans = events.filter((e) => e.replan?.n_changes).length;
  const rows = st ? Object.entries(st.districts).map(([d, v]) => ({ d, ...v })).sort((a, b) => a.coverage_so_far - b.coverage_so_far) : [];
  const names = map.districts?.features.map((f) => f.properties.name).sort() || [];

  return (
    <>
      <PageHead eyebrow="Dynamic reallocation" title="Live Operations"
        subtitle="New crisis reports arrive while the week runs; each one is read by the NLP and the next dispatch is re-planned on the spot">
        <span className="region">{st ? (st.done ? "WEEK FINISHED" : `${dayLabel(st.day).toUpperCase()} · ${st.time}`) : "STARTING"}</span>
      </PageHead>
      <div className="page">
        <Card>
          <div className="controls" style={{ gridTemplateColumns: "1.1fr auto auto auto 1.2fr" }}>
            <label className="field">Allocation strategy
              <select value={policy} onChange={(e) => setPolicy(e.target.value)} disabled={busy}>
                {POLICIES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <button className="btn ghost" onClick={start} disabled={busy}>Restart week</button>
            <button className="btn" onClick={() => setPlaying(!playing)} disabled={!st || st.done}>
              <Icon name={playing ? "pause" : "play"} size={15} /> {playing ? "Pause" : "Play"}
            </button>
            <button className="btn ghost" onClick={step} disabled={busy || playing || !st || st.done}>⏭ Next event</button>
            <div className="field">Clock speed
              <div className="chips">
                {SPEEDS.map(([v, l]) => <button key={v} className={`chip ${speed === v ? "on" : ""}`} onClick={() => setSpeed(v)}>{l}</button>)}
              </div>
            </div>
          </div>
          {st && !st.done && <p className="note" style={{ margin: "14px 0 0" }}>
            Next dispatch wave at <b>{st.next_wave}</b>. {st.reports_left_today} more real tweets will arrive today
            {st.next_event ? <>, the next at <b>{st.next_event}</b></> : ""}. You can send your own report at any time below.</p>}
          {err && <p className="error-box" style={{ marginTop: 14 }}>{err}</p>}
        </Card>

        <div className="stats">
          <Stat icon="tweet" label="Reports received" value={fmt(reportsIn)} sub={`${st?.counts.manual || 0} typed in here`} />
          <Stat icon="layers" tone="teal" label="Plans changed" value={fmt(replans)} sub={`${st?.counts.dispatch || 0} waves dispatched`} />
          <Stat icon="alerts" tone="red" label="Alerts raised" value={fmt(st?.counts.alert || 0)} sub="need jumps, cut-off or neglected districts" />
          <Stat icon="chart" tone="violet" label="Need met (closed days)" value={st?.metrics ? pct(st.metrics.fulfilment, 1) : "–"}
            sub={st?.metrics ? `worst-off district ${pct(st.metrics.worst_district_fulfilment)}` : "after the first day closes"} />
        </div>

        <div className="grid-2">
          <Card eyebrow={st ? `${dayLabel(st.day)} · ${st.time}` : "Live map"} title="Live situation"
            subtitle={`Districts coloured by the share of today's need already delivered. Blue lines: the plan for the ${st?.next_wave || "next"} wave. Outlined: the district of the latest report.`}
            right={lastReport && <span className="pill">Latest: {lastReport.district || "unplaced"} · {lastReport.time}</span>}>
            <MapView districts={map.districts} centres={centres} roads={roads} flows={plan?.flows} colorMode="coverage" coverage={coverage}
              layers={{ basemap: true, roads: true, centres: true, flows: true }} dayKey={`live-${st?.day}-${st?.last_seq}`}
              highlight={lastReport?.district} tall />
          </Card>

          <Card eyebrow="New report" title="Submit a field report"
            subtitle="Type or paste a message as a field officer or citizen would send it. The Step 1 model reads it and the plan is redone straight away.">
            <label className="field" style={{ marginBottom: 12 }}>Message
              <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. 30 families stranded in Kuttanad, need food and water urgently" />
            </label>
            <div className="chips" style={{ marginBottom: 12 }}>
              {EXAMPLES.map((x, i) => <button key={i} className="chip" onClick={() => setText(x)} title={x}>Example {i + 1}</button>)}
            </div>
            <div className="controls" style={{ gridTemplateColumns: "1fr auto" }}>
              <label className="field">District
                <select value={district} onChange={(e) => setDistrict(e.target.value)}>
                  <option value="">Find it from the text</option>
                  {names.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <button className="btn" onClick={send} disabled={busy || !st || st.done || text.trim().length < 3}>Send report</button>
            </div>
            {result && (
              <div className="report-box" style={{ marginTop: 16 }}>
                <div className="id">{result.event.time} · {result.nlp.district || "district not found"}</div>
                <div className="chips" style={{ margin: "8px 0" }}>
                  <span className="chip static">{CATEGORY_LABEL[result.nlp.category] || result.nlp.category} · {pct(result.nlp.confidence)} sure</span>
                  <span className="chip static" style={{ borderColor: result.nlp.urgency >= 0.7 ? "var(--high)" : "var(--medium)" }}>Urgency {result.nlp.urgency.toFixed(2)}</span>
                  {result.nlp.needs.map((n) => <span key={n} className="chip static">{NEED_WORD[n] || n}</span>)}
                  {result.nlp.district && <span className="chip static">{result.nlp.district_source === "chosen" ? "District chosen by you" : "Place found in text"}</span>}
                </div>
                <p style={{ margin: "6px 0" }}><b>{result.nlp.outcome[0].toUpperCase() + result.nlp.outcome.slice(1)}.</b>
                  {result.nlp.added_need && <> About <b>{fmt(result.nlp.people_used)} people</b> ({result.nlp.people_source === "text"
                    ? "counted from the message" : "estimated from urgency, no number given"}), so {result.nlp.district}'s need rose by{" "}
                    {Object.entries(result.nlp.added_need).map(([r, v]) => named(r, v)).join(", ")}. The nearest centres released that much
                    extra stock from reserve, and the {result.event.replan?.wave} wave was re-planned.</>}
                </p>
              </div>
            )}
          </Card>
        </div>

        <div className="grid-2 even">
          <Card eyebrow="Incoming" title="Live feed" right={<span className="pill">{events.length} events</span>}>
            <div className="filters">
              {Object.keys(filter).filter((k) => k !== "day_end").map((k) => (
                <button key={k} className={filter[k] ? "on" : ""} onClick={() => setFilter({ ...filter, [k]: !filter[k], ...(k === "day" ? { day_end: !filter[k] } : {}) })}>
                  {filter[k] ? "✓ " : ""}{FILTER_LABEL[k]}
                </button>
              ))}
            </div>
            <div className="feed scroll-list">
              {shown.length === 0 && <p className="note">Press Play or Next event. Reports, road changes and dispatches appear here as they happen.</p>}
              {shown.map((e) => {
                const [icon, tone, word] = LOOK[kindOf(e.type)];
                const moved = e.replan?.n_changes;
                return (
                  <button key={e.seq} className={`feed-item log ${focus?.seq === e.seq ? "sel" : ""}`}
                    onClick={() => (e.type === "report" && e.tweet_id && !e.replan ? go("decision", { tweet: e.tweet_id }) : setPicked(e))}>
                    <span className={`ico ${tone}`}><Icon name={icon} size={18} /></span>
                    <div className="body">
                      <div className="top">Day {e.day} · {e.time}{e.district ? ` · ${e.district}` : ""}
                        <span>{e.type.startsWith("road_") ? `Road ${e.type.slice(5)}` : word}</span>
                        {moved ? <span className="tag low" style={{ marginLeft: "auto" }}>plan changed · {moved}</span> : null}
                      </div>
                      <div className="txt">{e.detail}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </Card>

          <Card eyebrow={focus ? `${focus.type === "manual" ? "Field report" : focus.type.startsWith("road_") ? "Road change" : "Tweet"} · Day ${focus.day} ${focus.time}` : "Reallocation"}
            title="How the plan changed"
            subtitle={focus?.replan ? `Shipments planned for the ${focus.replan.wave} wave, just before and just after this event.` : undefined}
            right={focus?.type === "report" && focus.tweet_id && <button className="chip" onClick={() => go("decision", { tweet: focus.tweet_id })}>Open in Decision Support</button>}>
            {focus && <p className="note" style={{ marginTop: 0 }}>“{focus.detail.slice(0, 220)}”</p>}
            <ChangeList replan={focus?.replan} />
          </Card>
        </div>

        {st && (
          <Card eyebrow={`${dayLabel(st.day)} · ${st.time}`} title="District picture right now"
            subtitle="What the planner believes each district needs (its estimate, updated by every report) against the true need, and what has been sent today. Food kits shown; lowest coverage first.">
            <table className="t">
              <thead><tr><th>District</th><th style={{ width: "22%" }}>Need met so far today</th><th className="num">Morning forecast</th>
                <th className="num">Current estimate</th><th className="num">True need</th><th className="num">Sent today</th><th className="num">Next wave</th></tr></thead>
              <tbody>{rows.map((x) => (
                <tr key={x.d} className={x.d === lastReport?.district ? "hl" : ""}>
                  <td><b>{x.d}</b></td>
                  <td><div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    <div style={{ flex: 1 }}><Meter value={x.coverage_so_far} color={x.coverage_so_far < 0.5 ? "var(--high)" : x.coverage_so_far < 0.75 ? "var(--medium)" : "var(--teal-grad)"} thin /></div>
                    <b style={{ minWidth: 40, textAlign: "right" }}>{pct(x.coverage_so_far)}</b></div></td>
                  <td className="num muted">{fmt(x.forecast.food_kits)}</td>
                  <td className="num">{fmt(x.estimate.food_kits)}</td>
                  <td className="num">{fmt(x.need.food_kits)}</td>
                  <td className="num">{fmt(x.sent.food_kits)}</td>
                  <td className="num">{fmt(x.next_wave.food_kits)}</td>
                </tr>
              ))}</tbody>
            </table>
            <div className="grid-2 even" style={{ gap: 24, marginTop: 18 }}>
              <div>
                <h3 style={{ margin: "0 0 8px", fontSize: 15 }}>Stock left in all centres</h3>
                {RESOURCES.map((r) => (
                  <div className="bar-row" key={r} style={{ gridTemplateColumns: "100px 1fr 50px" }}>
                    <span>{RESOURCE_SHORT[r]}</span><Meter value={st.stock_left[r] / (st.stock_start[r] || 1)} color="var(--accent-grad)" thin />
                    <b>{pct(st.stock_left[r] / (st.stock_start[r] || 1))}</b>
                  </div>
                ))}
              </div>
              <div>
                <h3 style={{ margin: "0 0 8px", fontSize: 15 }}>Closed days</h3>
                {st.days.length === 0 ? <p className="note">Each day closes at the 24:00 wave.</p> : (
                  <table className="t">
                    <tbody>{st.days.map((x) => (
                      <tr key={x.day}><td>Day {x.day}</td><td className="num">{pct(x.met, 1)} met</td><td>worst {x.worst_district} {pct(x.worst)}</td></tr>
                    ))}</tbody>
                  </table>
                )}
              </div>
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
