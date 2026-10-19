import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import {
  CATEGORY_LABEL, CLASS_LABEL, RESOURCES, RESOURCE_LABEL, RESOURCE_SHORT, RESOURCE_UNIT, dayLabel,
} from "../constants.js";
import { Card, DayPicker, Meter, PageHead, Stat, fmt, pct } from "../components/ui.jsx";

const NEED_WORD = { food: "Food", water: "Water", medicine: "Medicine", rescue: "Rescue", shelter: "Shelter" };
// Week coverage of the report's district, official week (Step 4), in this order
const COMPARE = [
  ["MAPPO + fairness (α=0.5, β=1)", "AI agents (MAPPO + fairness)", true],
  ["MAPPO, no fairness term (α=0, β=0)", "AI agents, no fairness term"],
  ["LP fair + rationing rule", "Optimiser + rationing"],
  ["LP: max coverage (OR-Tools)", "Optimiser, max coverage"],
  ["Greedy by severity", "Greedy by severity"],
  ["Local-first (nearest centre)", "Local-first"],
];

function byCentre(shipments) {
  const out = {};
  for (const s of shipments) {
    out[s.centre] = out[s.centre] || { ...s, items: [] };
    out[s.centre].items.push(s);
  }
  return Object.values(out).sort((a, b) => (a.travel_time_hr ?? 99) - (b.travel_time_hr ?? 99));
}

export default function DecisionPage({ day, setDay, reports, districts, params }) {
  const [id, setId] = useState(params.tweet || null);
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => { if (params.tweet) setId(params.tweet); }, [params.tweet]);
  useEffect(() => {   // default to the most urgent report of the day
    if (reports?.length && (!id || (!params.tweet && !reports.some((r) => r.tweet_id === id)))) setId(reports[0].tweet_id);
  }, [reports]);
  useEffect(() => {
    if (!id) return;
    setErr(null);
    api.decision(id).then((x) => { setD(x); if (x.report.day !== day) setDay(x.report.day); }).catch((e) => setErr(String(e)));
  }, [id]);

  const options = reports || [];
  const rep = d?.report;
  const rank = d && districts ? [...districts.features].sort((a, b) => b.properties.severity - a.properties.severity)
    .findIndex((f) => f.properties.name === rep.district) + 1 : null;
  const centres = d ? byCentre(d.shipments) : [];
  const needs = rep ? (rep.resources || "").split("|").filter(Boolean) : [];
  const cov = d?.week_coverage_by_policy || {};

  return (
    <>
      <PageHead eyebrow="Decision intelligence" title="Response Recommendations"
        subtitle="Follow one crisis report from tweet to trucks: what the system understood, and what it sent">
        <span className="region">KERALA · AUG 2018</span>
        <DayPicker day={day} setDay={(x) => { setId(null); setDay(x); }} />
      </PageHead>
      <div className="page">
        <Card eyebrow="Input" title="Select a crisis report"
          subtitle="Real tweets from the 2018 floods that the reallocation loop acted on, most urgent first."
          right={<span className="pill">{options.length} reports on {dayLabel(day).split(" · ")[1]}</span>}>
          <label className="field" style={{ marginBottom: 16 }}>
            Crisis report
            <select value={id || ""} onChange={(e) => setId(e.target.value)}>
              {options.map((r) => (
                <option key={r.tweet_id} value={r.tweet_id}>
                  {r.time} · {r.district} · {CATEGORY_LABEL[r.category] || r.category} · urgency {r.urgency.toFixed(2)}
                </option>
              ))}
              {id && !options.some((r) => r.tweet_id === id) && <option value={id}>Selected report</option>}
            </select>
          </label>
          {err && <p className="error-box">{err}</p>}
          {rep && (
            <div className="report-box">
              <div className="id">{rep.time} IST · {rep.district}</div>
              <div className="txt">{rep.text}</div>
              <div className="chips">
                {needs.map((n) => <span key={n} className="chip static">{NEED_WORD[n] || n}</span>)}
                <span className="chip static" style={{ borderColor: "var(--series-3)" }}>{CATEGORY_LABEL[rep.category]} · {pct(rep.confidence)} sure</span>
                <span className="chip static" style={{ borderColor: rep.urgency >= 0.7 ? "var(--high)" : "var(--medium)" }}>Urgency {rep.urgency.toFixed(2)}</span>
              </div>
            </div>
          )}
        </Card>

        {d && (
          <>
            <div className="stats">
              <Stat label="Affected district" value={rep.district} sub={`${fmt(d.demand.displaced_people)} people displaced today`} />
              <Stat label="Flood priority score" value={d.severity.severity.toFixed(4)} sub={`${CLASS_LABEL[d.severity.severity_class]} priority · rank ${rank} of 14`} />
              <Stat label="Resource types asked" value={d.asked.length} sub={d.asked.map((r) => RESOURCE_SHORT[r]).join(", ")} />
              <Stat label="Centres contributing" value={centres.length} sub={`at the ${d.wave} dispatch wave`} />
            </div>

            <Card eyebrow="Demand estimation" title="Today's need vs planned"
              subtitle={`Everything ${rep.district} needs on ${dayLabel(rep.day).split(" · ")[1]} and what the plan ships across all four dispatch waves.`}>
              <div className="grid-2 even" style={{ gap: 14 }}>
                {RESOURCES.map((r) => {
                  const need = d.demand[r], got = d.planned_today[r] || 0;
                  return (
                    <div key={r} className="res-card">
                      <div className="head"><b>{RESOURCE_LABEL[r]} {d.asked.includes(r) && <span className="tag" style={{ marginLeft: 6 }}>asked</span>}</b>
                        <span>Need {fmt(need)} {RESOURCE_UNIT[r]}</span></div>
                      <div className="bar-row"><span>Planned</span><Meter value={need ? got / need : 1} color="var(--accent)" /><b>{need ? pct(Math.min(1, got / need)) : "–"}</b></div>
                      <div className="foot">{fmt(got, r === "rescue_teams" ? 1 : 0)} {RESOURCE_UNIT[r]} planned · {fmt(Math.max(0, need - got))} short</div>
                    </div>
                  );
                })}
              </div>
            </Card>

            <Card eyebrow="Allocation recommendation" title="Shipments at the next wave"
                subtitle={`What the AI agents sent to ${rep.district} at ${d.wave}, the first dispatch after this report. Nearest centres first.`}
                right={<span className="pill">{d.shipments.length} allocations</span>}>
                <div className="grid-3" style={{ marginBottom: 14 }}>
                  {centres.length === 0 && <p className="note">No shipments to {rep.district} at this wave. Stock was already committed or
                    roads were cut; the next waves pick it up.</p>}
                  {centres.map((c) => (
                    <div className="alloc-card" key={c.centre}>
                      <div className="row1"><span className="rc">RC</span>{c.centre} → {rep.district}
                        <span className="pill" style={{ marginLeft: "auto", fontSize: 11 }}>
                          {c.hops === 0 ? "same district" : `${c.hops} road hop${c.hops > 1 ? "s" : ""}`}{c.travel_time_hr ? ` · ${c.travel_time_hr} h` : ""}
                        </span>
                      </div>
                      <div className="chips" style={{ margin: "12px 0 8px" }}>
                        {c.items.map((s) => (
                          <span key={s.resource} className="alloc-amt">
                            <b style={{ fontSize: 22 }}>{fmt(s.amount, s.resource === "rescue_teams" ? 1 : 0)}</b>
                            <span className="muted" style={{ marginLeft: 6, marginRight: 14 }}>{RESOURCE_UNIT[s.resource]} {RESOURCE_SHORT[s.resource].toLowerCase()}</span>
                          </span>
                        ))}
                      </div>
                      <p>{c.centre_name}{c.hops === 0 ? "" : `, ${c.centre_district}`}. Fastest open route today.</p>
                    </div>
                  ))}
                </div>
                  <div className="explain">
                    <b>How this recommendation is made</b><br />
                    Every relief centre is an agent with the same trained policy (multi-agent PPO). Each wave it looks at district
                    priority, estimated need, its own stock and travel times, then decides how much to release and where to send it.
                    The reward included a fairness term, so no district is left far behind.
                  </div>
              </Card>

            <div className="grid-2 even">

              <Card eyebrow="Model evaluation" title={`How ${rep.district} fares under each strategy`}
                subtitle="Share of the district's need met over the whole official flood week (Step 4)."
                right={<span className="pill">{rep.district}</span>}>
                <table className="t">
                  <thead><tr><th>Strategy</th><th style={{ width: "42%" }}>Need met (week)</th><th className="num"></th></tr></thead>
                  <tbody>
                    {COMPARE.map(([k, label, ours]) => (
                      <tr key={k}>
                        <td>{ours ? <b>{label}</b> : label}</td>
                        <td><Meter value={cov[k]} color={ours ? "var(--accent)" : "var(--series-2)"} thin /></td>
                        <td className="num"><b>{pct(cov[k])}</b></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="note" style={{ marginTop: 12 }}>Across all 14 districts the AI agents keep the worst-off district near 70%,
                  while the max-coverage optimiser lets some fall to about 50%. See Model Analytics for the full comparison.</p>
              </Card>
            <Card eyebrow="Explainable decision support" title="Why was this decision recommended?"
              subtitle="The chain of models this report went through.">
              <ol className="steps">
                <li><span className="num">1</span><div><b>Report interpretation (NLP, Step 1)</b>
                  <p>The tweet classifier (TF-IDF + logistic regression, trained on HumAID) labelled it "{CATEGORY_LABEL[rep.category]}"
                    with {pct(rep.confidence)} confidence. Keyword rules found these needs: {needs.map((n) => NEED_WORD[n]).join(", ") || "none named, so all resources"}.
                    Its urgency score is {rep.urgency.toFixed(2)} on a 0-1 scale.</p></div></li>
                <li><span className="num">2</span><div><b>Location</b>
                  <p>A place name in the text matched the Kerala gazetteer, which placed the report in {rep.district}.</p></div></li>
                <li><span className="num">3</span><div><b>Demand update (Step 6)</b>
                  <p>The reallocation loop moved {rep.district}'s estimated need halfway towards the reported situation for{" "}
                    {d.asked.map((r) => RESOURCE_SHORT[r].toLowerCase()).join(", ")}, so the next plan sees the change.</p></div></li>
                <li><span className="num">4</span><div><b>District priority (GAT, Step 2)</b>
                  <p>{rep.district} has a flood-priority score of {d.severity.severity.toFixed(3)} ({CLASS_LABEL[d.severity.severity_class].toLowerCase()}),
                    rank {rank} of 14 today. The score combines the graph attention network's predicted demand (50%), 100-year flood
                    exposure (30%) and social vulnerability (20%). Neighbours on the graph: {d.neighbours.join(", ")}.</p></div></li>
                <li><span className="num">5</span><div><b>Allocation (multi-agent PPO, Steps 4-5)</b>
                  <p>At the {d.wave} wave, {centres.length ? `${centres.length} centre${centres.length > 1 ? "s" : ""} (${centres.map((c) => c.centre).join(", ")}) sent supplies` : "no centre sent supplies"} to {rep.district}.
                    Across the day the plan covers {pct(Math.min(1, (d.planned_today.food_kits || 0) / (d.demand.food_kits || 1)))} of its food need.</p></div></li>
                <li><span className="num">6</span><div><b>Fairness check</b>
                  <p>Over the week, the AI agents met {pct(cov[COMPARE[0][0]])} of {rep.district}'s need, against {pct(cov[COMPARE[3][0]])} for
                    the max-coverage optimiser.{d.alerts.length ? ` After this report the loop raised ${d.alerts.length} alert(s) for ${rep.district}: ${d.alerts.map((a) => a.detail).join("; ")}.` : ""}</p></div></li>
              </ol>
            </Card>
            </div>

          </>
        )}
      </div>
    </>
  );
}
