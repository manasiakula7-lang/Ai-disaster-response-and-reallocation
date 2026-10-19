import React, { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { CATEGORY_LABEL } from "../constants.js";
import { axisProps, cssVar, gridProps, tooltipProps } from "../theme.js";
import ComparePanel from "../components/ComparePanel.jsx";
import { Card, Meter, PageHead, Stat, fmt, pct } from "../components/ui.jsx";

const NEED_COLOR = { food: "var(--series-1)", rescue: "var(--series-2)", shelter: "var(--series-3)", medicine: "var(--series-4)", water: "var(--series-5)" };
const NEED_WORD = { food: "Food", water: "Water", medicine: "Medicine", rescue: "Rescue", shelter: "Shelter" };
const MODEL_COLOR = { "Persistence (tomorrow = today)": "var(--series-4)", "MLP (no graph)": "var(--series-3)", GCN: "var(--series-2)", GAT: "var(--series-1)" };

function ErrorDots({ rows, split }) {
  const data = rows.filter((r) => r.split === split).map((r) => ({ ...r, v: parseFloat(r.mae) }));
  const max = Math.max(...data.map((r) => r.v)) * 1.15;
  return (
    <div>
      {data.map((r) => (
        <div className="dot-row" key={r.model}>
          <span>{r.model.replace(" (tomorrow = today)", "")}</span>
          <div className="dot-track"><span style={{ left: `${(r.v / max) * 100}%`, background: MODEL_COLOR[r.model] }} /></div>
          <b style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{r.mae.split(" ")[0]}</b>
        </div>
      ))}
    </div>
  );
}

export default function AnalyticsPage() {
  const [a, setA] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [split, setSplit] = useState("temporal");
  useEffect(() => {
    api.analytics().then(setA).catch(() => {});
    api.metrics().then(setMetrics).catch(() => {});
  }, []);
  if (!a) return <PageHead eyebrow="Model analytics" title="Model Analytics" subtitle="Loading…" />;

  const nlp = a.nlp;
  const maxMention = Math.max(...nlp.resource_mentions.map(([, n]) => n));
  const fed = (metrics || []).filter((m) => m.step === "5" && m.evaluation.startsWith("mean"));
  const fedRow = fed.find((m) => m.policy.startsWith("Federated"));
  const cenRow = fed.find((m) => m.policy.startsWith("Centralised"));
  const rounds = a.fl.rounds.map((r) => ({ ...r, label: `R${r.round}` }));
  const lastRounds = [0, 0.25, 0.5, 0.75, 1].map((f) => rounds[Math.round(f * (rounds.length - 1))]).filter(Boolean);
  const curves = a.marl.learning_curves.map((r) => ({ ...r, it: r.iteration }));

  return (
    <>
      <PageHead eyebrow="Model analytics" title="How the AI performs"
        subtitle="Results of every model in the pipeline: NLP, GAT, multi-agent PPO and federated learning">
        <span className="region">TESTED ON HELD-OUT DATA</span>
      </PageHead>
      <div className="page">
        <div className="grid-2 even">
          <Card eyebrow="Incident intelligence (Step 1)" title="Disaster report analytics"
            right={<span className="pill">{fmt(nlp.tweets_total)} tweets</span>}>
            <div className="grid-2 even" style={{ gap: 12, marginBottom: 18 }}>
              <div className="stat plain"><div className="k">Macro-F1 (9 categories)</div><div className="v">{nlp.macro_f1.toFixed(3)}</div><div className="s">accuracy {pct(nlp.accuracy, 1)}</div></div>
              <div className="stat plain"><div className="k">Urgency score AUROC</div><div className="v">{nlp.urgency_auroc?.toFixed(3)}</div><div className="s">spots urgent requests</div></div>
              <div className="stat plain"><div className="k">Reports used in the flood week</div><div className="v">{nlp.week_reports}</div><div className="s">actionable and placed in a district</div></div>
              <div className="stat plain"><div className="k">Tweets placed in a district</div><div className="v">{fmt(nlp.tweets_located)}</div><div className="s">{pct(nlp.tweets_located / nlp.tweets_total)} of all tweets</div></div>
            </div>
            <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>Needs mentioned (flood-week reports)</h3>
            <div className="card" style={{ padding: 16, marginBottom: 18 }}>
              {nlp.resource_mentions.map(([k, n]) => (
                <div className="bar-row" key={k} style={{ gridTemplateColumns: "90px 1fr 40px" }}>
                  <b style={{ textAlign: "left" }}>{NEED_WORD[k] || k}</b>
                  <Meter value={n / maxMention} color={NEED_COLOR[k]} />
                  <b>{n}</b>
                </div>
              ))}
            </div>
            <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>Report locations</h3>
            <div className="chips">
              {nlp.by_district.map(([d, n]) => <span key={d} className="chip static">{d} <span className="pill" style={{ padding: "1px 8px", marginLeft: 6 }}>{n}</span></span>)}
            </div>
          </Card>

          <Card eyebrow="Classifier quality" title="F1 score by tweet category"
            subtitle="TF-IDF + logistic regression on the HumAID Kerala test split (n = 1,582).">
            {[...nlp.classes].sort((x, y) => y.f1 - x.f1).map((c) => (
              <div className="bar-row" key={c.label} style={{ gridTemplateColumns: "170px 1fr 50px" }}>
                <span>{CATEGORY_LABEL[c.label] || c.label}</span>
                <Meter value={c.f1} color="var(--accent-grad)" />
                <b>{c.f1.toFixed(2)}</b>
              </div>
            ))}
            <p className="note" style={{ marginTop: 12 }}>Strongest on rescue/donation and injured or dead people; weakest on
              "not humanitarian" and "other information", which are vague by nature.</p>
          </Card>
        </div>

        <div className="grid-2 even">
          <Card eyebrow="Graph intelligence (Step 2)" title="GAT demand forecast error"
            subtitle="Mean absolute error predicting tomorrow's demand per district. Lower is better."
            right={<div className="chips">
              <button className={`chip ${split === "temporal" ? "on" : ""}`} onClick={() => setSplit("temporal")}>Later days</button>
              <button className={`chip ${split === "spatial" ? "on" : ""}`} onClick={() => setSplit("spatial")}>Unseen districts</button>
            </div>}>
            <ErrorDots rows={a.gnn.table} split={split} />
            <p className="note" style={{ marginTop: 12 }}>{split === "temporal"
              ? "On later days, simply repeating today's demand is hard to beat with 14 districts and 26 days of data."
              : "On districts it never saw, the GAT beats persistence and the GCN; the plain MLP is close."}</p>
            <h3 style={{ margin: "16px 0 8px", fontSize: 15 }}>Strongest learned attention</h3>
            {a.gnn.top_attention.slice(0, 6).map((e) => (
              <div className="bar-row" key={`${e.source}${e.target}`} style={{ gridTemplateColumns: "230px 1fr 50px" }}>
                <span>{e.source} → {e.target}</span><Meter value={e.attention} color="var(--series-3)" thin /><b>{e.attention.toFixed(2)}</b>
              </div>
            ))}
          </Card>

          <Card eyebrow="Multi-agent PPO (Step 4)" title="Training reward"
            subtitle="Average reward per training iteration for the three fairness settings.">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={curves} margin={{ top: 10, right: 16, left: 0 }}>
                <CartesianGrid {...gridProps()} />
                <XAxis dataKey="it" {...axisProps()} />
                <YAxis {...axisProps()} width={40} />
                <Tooltip {...tooltipProps()} labelFormatter={(v) => `Iteration ${v}`} formatter={(v) => v.toFixed(2)} />
                <Legend wrapperStyle={{ fontSize: 12, color: cssVar("--text-2") }} />
                <Line dataKey="plain" name="No fairness (α=0, β=0)" stroke={cssVar("--series-4")} strokeWidth={2} dot={false} />
                <Line dataKey="fair" name="Fairness (α=0.5, β=1)" stroke={cssVar("--series-1")} strokeWidth={2} dot={false} />
                <Line dataKey="strong" name="Strong fairness (α=1, β=3)" stroke={cssVar("--series-2")} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
            <p className="note">The fairness settings add a reward for covering vulnerable districts, so their reward is on a higher
              scale; what matters is that each curve rises and levels off.</p>
          </Card>
        </div>

        <Card eyebrow="Strategy comparison (Steps 3-6)" title="Which allocation strategy works best?"
          subtitle="Average over 50 flood weeks the models never saw in training.">
          <ComparePanel metrics={metrics} />
        </Card>

        <Card eyebrow="Decentralised intelligence (Step 5)" title="Federated learning performance" right={<span className="pill">Flower · FedAvg</span>}>
          <div className="grid-3" style={{ marginBottom: 18 }}>
            <Stat label="Participating centres" value="19" sub="each trains on its own data" />
            <Stat label="Training rounds" value={rounds.length ? rounds[rounds.length - 1].round : "–"} sub="local SGD, then averaging" />
            <Stat label="Federated demand met" value={fedRow ? pct(fedRow.fulfilment, 1) : "–"} sub={cenRow ? `centralised: ${pct(cenRow.fulfilment, 1)}` : ""} />
          </div>
          <div className="grid-2 even">
            <div className="card">
              <h3 style={{ margin: "0 0 4px", fontSize: 16 }}>Model comparison</h3>
              <p className="note">Same 50 test weeks. Sharing only model weights costs about one point of fulfilment.</p>
              <table className="t">
                <thead><tr><th>Model</th><th className="num">Demand met</th><th className="num">Worst district</th><th className="num">Gini</th></tr></thead>
                <tbody>{fed.map((m) => (
                  <tr key={m.policy}><td>{m.policy}</td><td className="num">{pct(m.fulfilment, 1)}</td>
                    <td className="num">{pct(m.worst_district_fulfilment, 1)}</td><td className="num">{m.gini.toFixed(3)}</td></tr>
                ))}</tbody>
              </table>
            </div>
            <div className="card">
              <h3 style={{ margin: "0 0 4px", fontSize: 16 }}>Fairness during federated training</h3>
              <p className="note">Worst-off district's coverage on the official week, every 10 rounds.</p>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={rounds} margin={{ top: 10, right: 16, left: 0 }}>
                  <CartesianGrid {...gridProps()} />
                  <XAxis dataKey="round" {...axisProps()} />
                  <YAxis domain={[0.5, 0.8]} tickFormatter={(v) => `${Math.round(v * 100)}%`} {...axisProps()} width={44} />
                  <Tooltip {...tooltipProps()} labelFormatter={(v) => `Round ${v}`} formatter={(v) => `${(v * 100).toFixed(1)}%`} />
                  <Line dataKey="worst_district" name="Worst-off district" stroke={cssVar("--series-2")} strokeWidth={2} dot={false} />
                  <Line dataKey="fulfilment" name="Demand met" stroke={cssVar("--series-1")} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
              <div className="round-cards">
                {lastRounds.map((r) => <div key={r.round}>Round {r.round}<b>{pct(r.worst_district, 1)}</b></div>)}
              </div>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
