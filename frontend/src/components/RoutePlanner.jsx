import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { dayLabel } from "../constants.js";
import { Card, fmt } from "./ui.jsx";

const STATUS = { open: "Open", slowed: "Slowed", blocked: "Blocked" };

// Fastest open route from a relief centre to a district on the chosen day. The backend picks the
// route over the district road network (blocked links avoided, slowed links at their slower time);
// the public OSRM router then draws it along real streets through the district HQs on the way.
export default function RoutePlanner({ day, districts, centres, setRoute, preset }) {
  const [to, setTo] = useState(preset?.district || "");
  const [from, setFrom] = useState(preset?.centre || "");
  const [need, setNeed] = useState("rescue_teams");
  const [res, setRes] = useState(null);
  const [streets, setStreets] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const names = districts?.features.map((f) => f.properties.name).sort() || [];
  const plan = async (target = to, source = from) => {
    if (!target) return;
    setBusy(true); setErr(null); setStreets(null);
    try {
      const r = await api.route({ district: target, day, centre: source || null, need });
      setRes(r);
      if (!r.reachable) { setRoute(null); return; }
      const label = `${r.centre.name} → ${r.district}: ${r.hours} h`;
      const base = { key: `${r.centre.centre_id}-${r.district}-${day}`, from: r.centre.name, to: r.district, label };
      setRoute({ ...base, coords: r.waypoints, estimated: true });
      try {
        const s = await api.streets(r.waypoints);
        setStreets(s);
        setRoute({ ...base, coords: s.coords, estimated: false });
      } catch {
        setStreets({ failed: true });
      }
    } catch (e) { setErr(String(e.message || e)); } finally { setBusy(false); }
  };
  useEffect(() => { if (preset?.district) plan(preset.district, preset.centre || ""); }, [preset?.district, preset?.centre]);
  useEffect(() => { if (res) plan(); }, [day]);   // replan when the day changes

  return (
    <Card eyebrow="Rescue routing" title="Route planner"
      subtitle={`Fastest open route on ${dayLabel(day).split(" · ")[1]} from a relief centre to a district. Blocked roads are avoided and slowed roads count at their flood travel time.`}>
      <div className="controls" style={{ gridTemplateColumns: "1fr 1fr 1fr auto" }}>
        <label className="field">Destination district
          <select value={to} onChange={(e) => setTo(e.target.value)}>
            <option value="">Choose…</option>
            {names.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="field">From
          <select value={from} onChange={(e) => setFrom(e.target.value)}>
            <option value="">Fastest centre that has…</option>
            {centres?.features.map((f) => <option key={f.properties.centre_id} value={f.properties.centre_id}>{f.properties.centre_id} · {f.properties.name}</option>)}
          </select>
        </label>
        <label className="field">Sending
          <select value={need} onChange={(e) => setNeed(e.target.value)} disabled={!!from}>
            <option value="rescue_teams">Rescue teams</option>
            <option value="food_kits">Food kits</option>
            <option value="water_litres">Water</option>
            <option value="medicine_kits">Medicine kits</option>
          </select>
        </label>
        <button className="btn" onClick={() => plan()} disabled={busy || !to}>{busy ? "Planning…" : "Find route"}</button>
      </div>
      {err && <p className="error-box" style={{ marginTop: 14 }}>{err}</p>}
      {res && !res.reachable && <p className="error-box" style={{ marginTop: 14 }}>{res.detail} Try another centre or a later day.</p>}
      {res?.reachable && (
        <div style={{ marginTop: 18 }}>
          <div className="stats" style={{ marginBottom: 16 }}>
            <div className="stat plain"><div><div className="k">Send from</div><div className="v" style={{ fontSize: 20 }}>{res.centre.centre_id}</div>
              <div className="s">{res.centre.name} · {fmt(res.centre.rescue_teams)} rescue teams, {res.centre.vehicles} vehicles</div></div></div>
            <div className="stat plain"><div><div className="k">Travel time today</div><div className="v">{res.hours}<small>h</small></div>
              <div className="s">{res.hours > res.normal_hours ? <span className="down">+{(res.hours - res.normal_hours).toFixed(1)} h vs normal roads ({res.normal_hours} h)</span> : "same as on normal roads"}</div></div></div>
            <div className="stat plain"><div><div className="k">Road distance</div><div className="v">{streets?.km ? fmt(streets.km) : fmt(res.km)}<small>km</small></div>
              <div className="s">{streets?.km ? "along streets (OpenStreetMap)" : "estimated between district HQs"}</div></div></div>
            <div className="stat plain"><div><div className="k">Districts crossed</div><div className="v">{res.path.length}</div>
              <div className="s">{res.path.join(" → ")}</div></div></div>
          </div>
          {res.legs.length === 0 ? <p className="note">The centre is inside {res.district}: local delivery, about 1 hour.</p> : (
            <table className="t">
              <thead><tr><th>#</th><th>Road link</th><th>Status today</th><th className="num">Time today</th><th className="num">Normal</th><th className="num">km</th></tr></thead>
              <tbody>{res.legs.map((l, i) => (
                <tr key={i}><td>{i + 1}</td><td><b>{l.from}</b> → <b>{l.to}</b></td>
                  <td><span className={`tag ${l.status === "slowed" ? "medium" : "low"}`}>{STATUS[l.status]}</span></td>
                  <td className="num">{l.hours} h</td><td className="num muted">{l.normal_hours} h</td><td className="num">{fmt(l.km)}</td></tr>
              ))}</tbody>
            </table>
          )}
          <p className="note" style={{ marginTop: 12 }}>
            {res.path.join(" → ") !== res.normal_path.join(" → ")
              ? <>The usual route ({res.normal_path.join(" → ")}) is not usable today, so this detour is the fastest open one. </>
              : null}
            {res.blocked_today.length > 0 && <>Blocked today: {res.blocked_today.join(", ")}. </>}
            {res.alternatives.length > 0 && <>Next fastest centres: {res.alternatives.map((a) => `${a.centre_id} (${a.hours} h)`).join(", ")}. </>}
            {streets?.failed && <>The street router could not be reached, so the map shows the route as straight lines between district HQs. </>}
          </p>
        </div>
      )}
    </Card>
  );
}
