import React, { useEffect } from "react";
import Icon from "./icons.jsx";

const STEPS = [
  ["Pick a day", "Use the timeline under the map, or press ▶ to play the whole flood week (18-24 Aug 2018)."],
  ["Read the map", "Darker orange districts are hit harder. Green, yellow and red lines are open, slowed and blocked roads. Glowing blue lines are relief shipments, and thicker means more trucks. Hover over anything for details."],
  ["Use the sections on the left", "Overview and Alerts explain the day. Results compares the strategies. Simulate and What-if let you try things yourself."],
  ["Watch the right-hand column", "It always shows the headline numbers for the day, the worst-hit districts and the newest alerts."],
];

export default function HelpOverlay({ onClose }) {
  useEffect(() => {
    const f = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [onClose]);
  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={onClose}>
      <div className="help" onClick={(e) => e.stopPropagation()}>
        <button className="icon-btn help-close" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        <h2 id="help-title">Kerala Flood Relief: decision support</h2>
        <p className="note">An AI system that reads disaster tweets, scores how badly each district is hit and
          shares relief supplies fairly between them. Here's how to find your way around.</p>
        <ol className="help-steps">
          {STEPS.map(([t, d], i) => (
            <li key={t}><span className="num">{i + 1}</span><div><b>{t}</b><p>{d}</p></div></li>
          ))}
        </ol>
        <button className="btn" onClick={onClose}>Got it</button>
      </div>
    </div>
  );
}
