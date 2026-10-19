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


export const RESOURCE_UNIT = { food_kits: "kits", water_litres: "litres", medicine_kits: "kits", rescue_teams: "teams" };
export const RESOURCE_SHORT = { food_kits: "Food", water_litres: "Water", medicine_kits: "Medicine", rescue_teams: "Rescue" };

// Severity classes from the GAT (Step 2): high >= 0.5, medium >= 0.3, else low.
export const CLASS_LABEL = { high: "High", medium: "Moderate", low: "Low" };
export const CLASS_COLOR = { high: "#f0566b", medium: "#f5a33b", low: "#22c3a0" };

export const STRATEGIES = [
  ["mappo", "AI agents (MAPPO + fairness)"],
  ["lp_rationed", "Optimiser + rationing"],
  ["lp_fair", "Optimiser, fairness-aware"],
  ["lp", "Optimiser, max coverage"],
  ["greedy", "Greedy by severity"],
  ["local_first", "Local-first (nearest centre)"],
];

export const CATEGORY_LABEL = {
  requests_or_urgent_needs: "Urgent request",
  rescue_volunteering_or_donation_effort: "Rescue / donation",
  infrastructure_and_utility_damage: "Infrastructure damage",
  injured_or_dead_people: "Injured or dead",
  displaced_people_and_evacuations: "Displaced / evacuation",
  caution_and_advice: "Caution and advice",
  other_relevant_information: "Other relevant info",
  sympathy_and_support: "Sympathy and support",
  not_humanitarian: "Not humanitarian",
};
