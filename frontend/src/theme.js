import { useEffect, useState } from "react";

// SVG presentation attributes (Leaflet, Recharts) can't resolve CSS variables,
// so read the current value of a token from the root element.
export const cssVar = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#2a78d6";

// Re-render when the OS switches between light and dark.
export function useColorScheme() {
  const q = window.matchMedia("(prefers-color-scheme: dark)");
  const [dark, setDark] = useState(q.matches);
  useEffect(() => {
    const f = (e) => setDark(e.matches);
    q.addEventListener("change", f);
    return () => q.removeEventListener("change", f);
  }, []);
  return dark;
}

export const axisProps = () => ({
  stroke: cssVar("--axis"),
  tick: { fill: cssVar("--text-2"), fontSize: 11 },
  tickLine: false,
});
export const gridProps = () => ({ stroke: cssVar("--grid"), strokeDasharray: "0", vertical: false });
export const tooltipProps = () => ({
  contentStyle: {
    background: cssVar("--surface"), border: `1px solid ${cssVar("--axis")}`, borderRadius: 6, fontSize: 12,
    color: cssVar("--text"),
  },
  labelStyle: { color: cssVar("--text"), fontWeight: 600 },
  itemStyle: { color: cssVar("--text") },
  cursor: { fill: cssVar("--surface-2") },
});
