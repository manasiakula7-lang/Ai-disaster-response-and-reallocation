import React, { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axisProps, cssVar, gridProps, tooltipProps } from "../theme.js";

const SHORT = {
  "Local-first (nearest centre)": "Local-first",
  "Greedy by severity": "Greedy",
  "LP: max coverage (OR-Tools)": "LP max coverage",
  "LP: fairness-aware (OR-Tools)": "LP fair",
  "LP fair + rationing rule": "LP + rationing",
  "MAPPO, no fairness term (α=0, β=0)": "MAPPO α=0 β=0",
  "MAPPO + fairness (α=0.5, β=1)": "MAPPO α=.5 β=1",
  "MAPPO + strong fairness (α=1, β=3)": "MAPPO α=1 β=3",
  "Hindsight optimum (knows the whole week; upper bound)": "Hindsight (bound)",
};
const METRICS = [
  ["fulfilment", "Demand met", true],
  ["worst_district_fulfilment", "Worst-off district", true],
  ["gini", "Gini (lower = fairer)", false],
];

function HBar({ data, metric, isPct, color }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(140, data.length * 26 + 30)}>
      <BarChart data={data} layout="vertical" margin={{ left: 4, right: 40 }}>
        <CartesianGrid {...gridProps()} horizontal={false} vertical />
        <XAxis type="number" domain={isPct ? [0, 1] : [0, "auto"]} {...axisProps()}
          tickFormatter={(v) => (isPct ? `${Math.round(v * 100)}%` : v.toFixed(2))} />
        <YAxis type="category" dataKey="name" width={120} {...axisProps()} interval={0} />
        <Tooltip {...tooltipProps()} formatter={(v) => (isPct ? `${(v * 100).toFixed(1)}%` : v.toFixed(3))} />
        <Bar dataKey={metric} fill={color} radius={[0, 4, 4, 0]} barSize={14}>
          <LabelList dataKey={metric} position="right" fill={cssVar("--text-2")} fontSize={11}
            formatter={(v) => (isPct ? `${(v * 100).toFixed(1)}%` : v.toFixed(3))} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function ComparePanel({ metrics }) {
  const [metric, setMetric] = useState("fulfilment");
  const [, label, isPct] = METRICS.find((m) => m[0] === metric);
  const step4 = useMemo(() => (metrics || [])
    .filter((m) => m.step === "4" && m.evaluation.startsWith("mean"))
    .map((m) => ({ ...m, name: SHORT[m.policy] || m.policy })), [metrics]);
  const step5 = (metrics || []).filter((m) => m.step === "5" && m.evaluation.startsWith("mean"));
  const step6 = (metrics || []).filter((m) => m.step === "6" && m.evaluation.startsWith("mean"))
    .map((m) => ({ ...m, name: m.policy.replace("MAPPO (fair)", "MAPPO").replace("LP fair + rationing", "LP") }));
  if (!metrics) return <p className="note">Loading…</p>;
  return (
    <div>
      <div className="filters">
        {METRICS.map(([k, l]) => (
          <button key={k} className={metric === k ? "on" : ""} onClick={() => setMetric(k)}>
            {metric === k ? "✓ " : ""}{l}
          </button>
        ))}
      </div>

      <h2>Allocation strategies: {label.toLowerCase()}</h2>
      <p className="note">Steps 3-4, average over 50 unseen flood weeks.</p>
      <HBar data={step4} metric={metric} isPct={isPct} color={cssVar("--series-1")} />

      <h2>Value of replanning: {label.toLowerCase()}</h2>
      <p className="note">Step 6: fixed morning plan (static) vs reacting to roads, tweets, both (dynamic),
        and knowing everything (perfect).</p>
      <HBar data={step6} metric={metric} isPct={isPct} color={cssVar("--series-2")} />

      <h2>Federated learning (Step 5)</h2>
      <table className="t">
        <thead><tr><th>Model</th><th>Demand met</th><th>Worst district</th><th>Gini</th></tr></thead>
        <tbody>
          {step5.map((m) => (
            <tr key={m.policy}>
              <td>{m.policy}</td>
              <td>{(m.fulfilment * 100).toFixed(1)}%</td>
              <td>{(m.worst_district_fulfilment * 100).toFixed(1)}%</td>
              <td>{m.gini.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
