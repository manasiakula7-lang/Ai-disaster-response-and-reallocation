import React from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { RESOURCES, RESOURCE_LABEL, severityColor } from "../constants.js";
import { axisProps, cssVar, gridProps, tooltipProps } from "../theme.js";

const fmt = (v) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });

export default function OverviewPanel({ districts, events, planned }) {
  if (!districts) return <p className="note">Loading…</p>;
  const props = districts.features.map((f) => f.properties);
  const displaced = props.reduce((s, p) => s + (p.displaced_people || 0), 0);
  const severe = props.filter((p) => p.severity >= 0.5).length;
  const alerts = (events || []).filter((e) => e.type === "alert").length;
  const sev = [...props].sort((a, b) => b.severity - a.severity)
    .map((p) => ({ name: p.name, severity: Number(p.severity?.toFixed(3)) }));
  const byRes = RESOURCES.map((r) => {
    const need = props.reduce((s, p) => s + (p[r] || 0), 0);
    return { resource: RESOURCE_LABEL[r], share: need ? Math.min(1, (planned?.byResource[r] || 0) / need) : 0 };
  });

  return (
    <div>
      <div className="tiles">
        <div className="tile"><div className="v">{fmt(displaced)}</div><div className="k">people displaced</div></div>
        <div className="tile"><div className="v">{severe}</div><div className="k">districts at high severity</div></div>
        <div className="tile"><div className="v">{alerts}</div><div className="k">alerts raised</div></div>
      </div>

      <h2>Severity by district</h2>
      <p className="note">GAT severity score (0-1), same colours as the map.</p>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={sev} layout="vertical" margin={{ left: 10, right: 16 }}>
          <CartesianGrid {...gridProps()} horizontal={false} vertical />
          <XAxis type="number" domain={[0, 1]} {...axisProps()} />
          <YAxis type="category" dataKey="name" width={118} {...axisProps()} interval={0} />
          <Tooltip {...tooltipProps()} />
          <Bar dataKey="severity" name="Severity" radius={[0, 4, 4, 0]} barSize={12}>
            {sev.map((d) => <Cell key={d.name} fill={severityColor(d.severity)} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <h2>Share of today's need covered by the plan</h2>
      <p className="note">Shipments the reallocation loop (Step 6, AI agents) planned today, as a share of demand.
        Planned, not delivered: a shipment on a road that turns out blocked does not arrive.</p>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={byRes} margin={{ right: 16 }}>
          <CartesianGrid {...gridProps()} />
          <XAxis dataKey="resource" {...axisProps()} interval={0} />
          <YAxis domain={[0, 1]} tickFormatter={(v) => `${v * 100}%`} {...axisProps()} width={42} />
          <Tooltip {...tooltipProps()} formatter={(v) => `${(v * 100).toFixed(1)}%`} />
          <Bar dataKey="share" name="Planned share of need" fill={cssVar("--series-1")} radius={[4, 4, 0, 0]} barSize={34} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
