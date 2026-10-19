import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { CLASS_COLOR, CLASS_LABEL } from "../constants.js";
import { Card, DayPicker, Meter, PageHead, fmt } from "../components/ui.jsx";

const W = 900, H = 790;
const SHORT = {
  Thiruvananthapuram: "TVM", Kollam: "KLM", Pathanamthitta: "PTA", Alappuzha: "ALP", Kottayam: "KTM",
  Idukki: "IDK", Ernakulam: "EKM", Thrissur: "TSR", Palakkad: "PKD", Malappuram: "MLP", Kozhikode: "KKD",
  Wayanad: "WYD", Kannur: "KNR", Kasaragod: "KSD",
};

// Hand-placed schematic: north at the top left, south at the bottom right, coast on the left,
// so the long, thin state fills the panel and neighbours don't overlap.
const POS = {
  Kasaragod: [120, 80], Kannur: [230, 170], Wayanad: [430, 150], Kozhikode: [310, 275], Malappuram: [430, 345],
  Palakkad: [640, 330], Thrissur: [470, 440], Ernakulam: [520, 530], Idukki: [740, 500], Kottayam: [650, 610],
  Alappuzha: [430, 625], Pathanamthitta: [800, 650], Kollam: [600, 705], Thiruvananthapuram: [770, 735],
};

function layout(nodes, centres) {
  const pos = Object.fromEntries(nodes.map((n) => [n.district, POS[n.district]]));
  // relief centres sit on a small ring around their host district
  const byHost = {};
  centres.forEach((c) => { (byHost[c.district] = byHost[c.district] || []).push(c); });
  Object.entries(byHost).forEach(([d, cs]) => {
    cs.forEach((c, i) => {
      const a = -Math.PI / 3 + i * (Math.PI / 2.4);
      pos[c.centre_id] = [pos[d][0] + 60 * Math.cos(a), pos[d][1] + 60 * Math.sin(a)];
    });
  });
  return pos;
}

function ZeroBar({ v, max }) {
  const w = Math.min(50, (Math.abs(v) / max) * 50);
  return (
    <div className="zero-meter">
      <span style={v >= 0 ? { left: "50%", width: `${w}%`, background: "var(--accent-2)" }
        : { right: "50%", width: `${w}%`, background: "var(--series-3)" }} />
    </div>
  );
}

export default function NetworkPage({ day, setDay }) {
  const [graph, setGraph] = useState(null);
  const [sel, setSel] = useState("Alappuzha");
  const [hover, setHover] = useState(null);
  useEffect(() => { api.graph(day).then(setGraph).catch(() => {}); }, [day]);
  const pos = useMemo(() => graph && layout(graph.nodes, graph.centres), [graph]);
  if (!graph || !pos) return <PageHead eyebrow="Graph intelligence" title="GAT District Network" subtitle="Loading…" />;

  const node = graph.nodes.find((n) => n.district === sel);
  const focus = hover || sel;
  const neigh = graph.edges.filter((e) => e.source === sel || e.target === sel)
    .map((e) => ({ name: e.source === sel ? e.target : e.source, attention: e.attention, status: e.status, time: e.travel_time_hr }))
    .sort((a, b) => b.attention - a.attention);
  const embMax = Math.max(...graph.nodes.flatMap((n) => (n.embedding || []).map(Math.abs)), 1);
  const maxAtt = Math.max(...graph.edges.map((e) => e.attention), 0.01);
  const ranked = [...graph.nodes].sort((a, b) => b.severity - a.severity).map((n) => n.district);

  return (
    <>
      <PageHead eyebrow="Graph intelligence" title="GAT District Network"
        subtitle="How the graph attention network sees Kerala: districts, road links and relief centres">
        <span className="region">KERALA · AUG 2018</span>
        <DayPicker day={day} setDay={setDay} />
      </PageHead>
      <div className="page">
        <div className="grid-2">
          <Card eyebrow="Graph view" title="District graph"
            right={<span className="pill">14 districts · 21 links</span>}>
            <div className="legend-row">
              {["high", "medium", "low"].map((c) => <span key={c}><span className="dot" style={{ background: CLASS_COLOR[c] }} />{CLASS_LABEL[c]} priority</span>)}
              <span><span className="dot" style={{ background: "#fff", border: "2px solid var(--teal)" }} />Relief centre</span>
            </div>
            <div className="net-wrap">
              <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="District graph">
                <defs>
                  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="6" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
                  </filter>
                </defs>
                {graph.centres.map((c) => (
                  <line key={`h-${c.centre_id}`} x1={pos[c.district][0]} y1={pos[c.district][1]} x2={pos[c.centre_id][0]} y2={pos[c.centre_id][1]}
                    stroke="#22c3a0" strokeWidth="2" strokeDasharray="5 5" opacity={c.district === focus ? 1 : 0.55} />
                ))}
                {graph.edges.map((e) => {
                  const on = e.source === focus || e.target === focus;
                  return (
                    <line key={e.edge_id} x1={pos[e.source][0]} y1={pos[e.source][1]} x2={pos[e.target][0]} y2={pos[e.target][1]}
                      stroke={e.status === "blocked" ? "#f0566b" : on ? "#62b0ff" : "#8fb3e8"}
                      strokeDasharray={e.status === "blocked" ? "4 6" : undefined}
                      strokeWidth={1 + (e.attention / maxAtt) * 6} opacity={on ? 0.95 : 0.4}>
                      <title>{`${e.source} – ${e.target}: attention ${e.attention.toFixed(2)}, ${e.status}`}</title>
                    </line>
                  );
                })}
                {graph.centres.map((c) => {
                  const [x, y] = pos[c.centre_id];
                  return (
                    <g key={c.centre_id} className="node" onClick={() => setSel(c.district)}>
                      <circle cx={x} cy={y} r="15" fill="#0c1f3f" stroke="#22c3a0" strokeWidth="2.5" />
                      <path d={`M${x - 6} ${y + 1}l6-5 6 5M${x - 4} ${y}v5h8v-5`} stroke="#fff" strokeWidth="1.6" fill="none" />
                      <title>{c.name}</title>
                    </g>
                  );
                })}
                {graph.nodes.map((n) => {
                  const [x, y] = pos[n.district];
                  const r = 15 + n.severity * 22;
                  const isSel = n.district === sel;
                  return (
                    <g key={n.district} className="node" onClick={() => setSel(n.district)}
                      onMouseEnter={() => setHover(n.district)} onMouseLeave={() => setHover(null)}>
                      {isSel && <circle cx={x} cy={y} r={r + 9} fill="none" stroke="#fff" strokeWidth="2" opacity="0.8" />}
                      <circle cx={x} cy={y} r={r} fill={CLASS_COLOR[n.severity_class]} opacity="0.35" filter="url(#glow)" />
                      <circle cx={x} cy={y} r={r - 3} fill={CLASS_COLOR[n.severity_class]} stroke="#e8f0ff" strokeWidth="2" />
                      <text x={x} y={y + 4} textAnchor="middle">{ranked.indexOf(n.district) + 1}</text>
                      <g className="label">
                        <rect x={x - 21} y={y - r - 24} width="42" height="18" rx="6" />
                        <text x={x} y={y - r - 11} textAnchor="middle">{SHORT[n.district]}</text>
                      </g>
                      <title>{`${n.district}: priority ${n.severity.toFixed(2)}`}</title>
                    </g>
                  );
                })}
              </svg>
              <div className="net-foot">
                <span><b>Line width</b> = GAT attention between neighbours</span>
                <span><b>Red dashed</b> = road blocked today</span>
                <span><b>Teal dashed</b> = relief centre's home district</span>
                <span><b>Number</b> = priority rank today. Click a district to explore</span>
              </div>
            </div>
          </Card>

          <Card eyebrow={node.district} title="District details">
            <div className="card" style={{ padding: 18, marginBottom: 14 }}>
              <div className="k" style={{ fontWeight: 700 }}>Flood priority (GAT severity)</div>
              <div className="big-num" style={{ margin: "6px 0 10px" }}>{node.severity.toFixed(4)}</div>
              <Meter value={node.severity} color={CLASS_COLOR[node.severity_class]} />
              <div style={{ marginTop: 8 }}><span className={`tag ${node.severity_class}`}>{CLASS_LABEL[node.severity_class]} priority</span> <span className="muted" style={{ fontSize: 12 }}>· rank {ranked.indexOf(sel) + 1} of 14</span></div>
            </div>
            <div className="grid-2 even" style={{ gap: 12, marginBottom: 16 }}>
              <div className="card" style={{ padding: 14 }}><div className="note" style={{ margin: 0 }}>Flood exposure (100-yr)</div><b style={{ fontSize: 22 }}>{node.flood_exposure_100yr.toFixed(4)}</b></div>
              <div className="card" style={{ padding: 14 }}><div className="note" style={{ margin: 0 }}>Vulnerability score</div><b style={{ fontSize: 22 }}>{node.vulnerability.toFixed(4)}</b></div>
              <div className="card" style={{ padding: 14 }}><div className="note" style={{ margin: 0 }}>Population (2018)</div><b style={{ fontSize: 22 }}>{fmt(node.population)}</b></div>
              <div className="card" style={{ padding: 14 }}><div className="note" style={{ margin: 0 }}>Rural share</div><b style={{ fontSize: 22 }}>{Math.round(node.rural_share * 100)}%</b></div>
            </div>

            <h3 style={{ margin: "0 0 8px", fontSize: 15, display: "flex" }}>Neighbouring districts <span className="muted" style={{ marginLeft: "auto" }}>{neigh.length}</span></h3>
            <div className="chips" style={{ marginBottom: 16 }}>
              {neigh.map((n) => (
                <button key={n.name} className="chip" onClick={() => setSel(n.name)}
                  title={`attention ${n.attention.toFixed(2)} · road ${n.status} · ${n.time} h`}
                  style={n.status === "blocked" ? { borderColor: "var(--high)" } : undefined}>
                  {n.name} <span className="muted">{n.attention.toFixed(2)}</span>
                </button>
              ))}
            </div>
            <p className="note" style={{ marginTop: -8 }}>Number = GAT attention on that link. Red outline = road blocked today.</p>
            <h3 style={{ margin: "0 0 8px", fontSize: 15 }}>Relief centres</h3>
            <div className="chips" style={{ marginBottom: 16 }}>
              {node.centres.length ? node.centres.map((c) => <span key={c} className="chip static">{c}</span>)
                : <span className="note">None in this district</span>}
            </div>
            <h3 style={{ margin: "0 0 6px", fontSize: 15, display: "flex" }}>GAT embedding <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>16 learned features</span></h3>
            {(node.embedding || []).map((v, i) => (
              <div className="feat-row" key={i}><span className="muted">F{i + 1}</span><ZeroBar v={v} max={embMax} /><b>{v.toFixed(2)}</b></div>
            ))}
            <p className="note" style={{ marginTop: 10 }}>The network's hidden layer for this district on this day, just before it predicts tomorrow's
              demand. Values are learned features, not probabilities.</p>
          </Card>
        </div>
      </div>
    </>
  );
}
