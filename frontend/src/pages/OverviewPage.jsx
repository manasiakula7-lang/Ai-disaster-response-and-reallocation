import React from "react";
import { CATEGORY_LABEL, CLASS_COLOR, CLASS_LABEL, dayLabel } from "../constants.js";
import Icon from "../components/icons.jsx";
import MapView from "../components/MapView.jsx";
import { Card, DayPicker, PageHead, Stat, fmt } from "../components/ui.jsx";

const LAYERS = { basemap: true, roads: false, centres: true, flows: false };

export function urgencyTone(u) {
  return u >= 0.7 ? "" : u >= 0.5 ? "mid" : "low";
}

export function ReportFeed({ reports, go, limit }) {
  if (!reports) return <p className="note">Loading…</p>;
  if (!reports.length) return <p className="note">No reports this day.</p>;
  return (
    <div className="feed">
      {reports.slice(0, limit).map((r) => (
        <button key={r.tweet_id} className="feed-item" onClick={() => go("decision", { tweet: r.tweet_id })}
          title="Open in Decision Support">
          <span className={`ico ${urgencyTone(r.urgency)}`}><Icon name="pulse" size={18} /></span>
          <div className="body">
            <div className="top">{r.time} · {r.district}<span>{CATEGORY_LABEL[r.category] || r.category}</span></div>
            <div className="txt">{r.text}</div>
          </div>
          <span className="go"><Icon name="arrow" size={16} /></span>
        </button>
      ))}
    </div>
  );
}

export default function OverviewPage({ day, setDay, districts, centres, roads, reports, events, go }) {
  const props = districts?.features.map((f) => f.properties) || [];
  const counts = { high: 0, medium: 0, low: 0 };
  props.forEach((p) => { counts[p.severity_class] += 1; });
  const blocked = roads?.features.filter((f) => f.properties.status === "blocked").length;
  const displaced = props.reduce((s, p) => s + (p.displaced_people || 0), 0);
  const alerts = (events || []).filter((e) => e.type === "alert").length;
  return (
    <>
      <PageHead title="Kerala Command Centre" subtitle={`Flood intelligence at a glance · ${dayLabel(day)}`}>
        <span className="region">KERALA · AUG 2018</span>
        <DayPicker day={day} setDay={setDay} />
      </PageHead>
      <div className="page">
        <div className="stats">
          <Stat icon="map" label="Mapped districts" value="14" sub={`${counts.high} high · ${counts.medium} moderate priority`} />
          <Stat icon="shield" tone="teal" label="Relief centres" value={centres ? centres.features.length : "–"} sub="Simulated locations with stock and trucks" />
          <Stat icon="pulse" tone="red" label="Crisis reports today" value={reports ? reports.length : "–"} sub={`Real tweets · ${alerts} alerts raised`} />
          <Stat icon="network" tone="violet" label="Road links" value={roads ? roads.features.length : "–"} sub={`${blocked ?? "–"} blocked today`} />
        </div>

        <div className="grid-2">
          <Card eyebrow="Geospatial view" title="Flood priority map"
            right={<span className="pill">{fmt(displaced)} displaced</span>}>
            <div className="legend-row">
              {["high", "medium", "low"].map((c) => (
                <span key={c}><span className="dot" style={{ background: CLASS_COLOR[c] }} />{CLASS_LABEL[c]} ({counts[c]})</span>
              ))}
            </div>
            <MapView districts={districts} centres={centres} roads={roads} layers={LAYERS} colorMode="class"
              dayKey={day} onPick={() => go("gis")} />
          </Card>

          <Card eyebrow="Incident feed" title="Disaster reports"
            right={<button className="link-btn" onClick={() => go("decision")}>Explore <Icon name="arrow" size={15} /></button>}>
            <p className="note">Tweets the NLP model read, placed in a district and flagged as needing action. Most urgent first.</p>
            <div className="scroll-list"><ReportFeed reports={reports} go={go} limit={40} /></div>
          </Card>
        </div>
      </div>
    </>
  );
}
