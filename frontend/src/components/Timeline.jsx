import React, { useEffect } from "react";
import { DAYS, dayDate } from "../constants.js";
import Icon from "./icons.jsx";

// Floating day picker at the bottom of the map, with a play button that steps through the week.
export default function Timeline({ day, setDay, playing, setPlaying, locked, lockedLabel }) {
  useEffect(() => {
    if (!playing) return undefined;
    const t = setInterval(() => setDay((d) => (d >= DAYS.length ? 1 : d + 1)), 1600);
    return () => clearInterval(t);
  }, [playing, setDay]);

  if (locked) {
    return <div className="timeline glass"><span className="timeline-locked">{lockedLabel}</span></div>;
  }
  return (
    <div className="timeline glass" role="group" aria-label="Scenario day">
      <button className="play" onClick={() => setPlaying(!playing)} title={playing ? "Pause" : "Play the week"}
        aria-label={playing ? "Pause" : "Play the week"}>
        <Icon name={playing ? "pause" : "play"} size={16} />
      </button>
      <div className="days">
        {DAYS.map((d) => (
          <button key={d} className={d === day ? "on" : ""} onClick={() => { setPlaying(false); setDay(d); }}>
            <span className="d">Day {d}</span>
            <span className="date">{dayDate(d)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
