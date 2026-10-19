export const DAYS = [1, 2, 3, 4, 5, 6, 7];
export const dayLabel = (d) => `Day ${d} · ${17 + d} Aug 2018`;
export const dayDate = (d) => `${17 + d} Aug`;

export const RESOURCES = ["food_kits", "water_litres", "medicine_kits", "rescue_teams"];
export const RESOURCE_LABEL = {
  food_kits: "Food kits",
  water_litres: "Water (L)",
  medicine_kits: "Medicine kits",
  rescue_teams: "Rescue teams",
};
export const TRUCKLOAD = { food_kits: 1000, water_litres: 25000, medicine_kits: 500 };

export const POLICY_LABEL = {
  mappo: "AI agents (MAPPO + fairness)",
  lp_rationed: "Optimiser + rationing",
  lp_fair: "Optimiser, fairness-aware",
  lp: "Optimiser, max coverage",
  greedy: "Greedy by severity",
  local_first: "Local-first",
};

// Sequential ramp for severity / coverage (one hue, light -> dark).
// Severity uses the orange ramp, coverage the blue ramp (reference palette).
const ORANGE = ["#fde4d6", "#f9c4a6", "#f4a072", "#eb6834", "#c94f1f", "#9c3a14"];
const BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"];
const bin = (v, ramp) => ramp[Math.min(ramp.length - 1, Math.max(0, Math.floor(v * ramp.length)))];
export const severityColor = (v) => (v == null ? "#898781" : bin(Math.min(v / 0.8, 0.999), ORANGE));
export const coverageColor = (v) => (v == null ? "#898781" : bin(Math.min(v, 0.999), BLUE));
export const SEVERITY_STEPS = ORANGE;
export const COVERAGE_STEPS = BLUE;

// Status palette (reserved for road state); always shown with a label + dash style.
export const ROAD_STYLE = {
  open: { color: "#0ca30c", dashArray: null, label: "Open" },
  slowed: { color: "#fab219", dashArray: "6 4", label: "Slowed" },
  blocked: { color: "#d03b3b", dashArray: "2 6", label: "Blocked" },
};

