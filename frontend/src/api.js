// Thin wrapper around the Step 7 FastAPI backend.
export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  } catch {
    // The browser hides the reason: either the backend isn't running or it crashed on this request.
    throw new Error(`Couldn't get ${path.split("?")[0]} from the backend. Check the uvicorn terminal for an error, ` +
      "and run python -m backend.app.load if you updated the project.");
  }
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

const qs = (params) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null)).toString();

export const api = {
  districts: (day) => request(`/districts?${qs({ day })}`),
  centres: () => request("/centres"),
  roads: (day) => request(`/roads?${qs({ day })}`),
  events: (day) => request(`/events?${qs({ day })}`),
  allocations: (day) => request(`/allocations?${qs({ day })}`),
  metrics: (step) => request(`/metrics?${qs({ step })}`),
  policies: () => request("/policies"),
  startSim: (body) => request("/simulate", { method: "POST", body: JSON.stringify(body) }),
  stepSim: (id) => request(`/simulate/${id}/step`, { method: "POST" }),
  closeRoad: (id, edge_id) =>
    request(`/simulate/${id}/close_road`, { method: "POST", body: JSON.stringify({ edge_id }) }),
  whatIf: (body) => request("/whatif", { method: "POST", body: JSON.stringify(body) }),
  graph: (day) => request(`/graph?${qs({ day })}`),
  analytics: () => request("/analytics"),
  decisions: (day) => request(`/decisions?${qs({ day })}`),
  decision: (id) => request(`/decision/${id}`),
  evaluate: (body) => request("/evaluate", { method: "POST", body: JSON.stringify(body) }),
  route: (params) => request(`/route?${qs(params)}`),
  // Street-level geometry through the given waypoints ([lat, lon]) from the public OSRM router (no key).
  streets: async (waypoints) => {
    const pts = waypoints.map(([lat, lon]) => `${lon.toFixed(5)},${lat.toFixed(5)}`).join(";");
    const res = await fetch(`https://router.project-osrm.org/route/v1/driving/${pts}?overview=full&geometries=geojson`);
    if (!res.ok) throw new Error(`router ${res.status}`);
    const r = (await res.json()).routes?.[0];
    if (!r) throw new Error("no route");
    return { coords: r.geometry.coordinates.map(([lon, lat]) => [lat, lon]), km: r.distance / 1000, hours: r.duration / 3600 };
  },
  opsStart: (policy) => request("/ops", { method: "POST", body: JSON.stringify({ policy }) }),
  opsSupplyOptions: (id) => request(`/ops/${id}/supply`),
  opsSupply: (id, option, overrides) => request(`/ops/${id}/supply`, { method: "POST", body: JSON.stringify({ option, overrides }) }),
  opsDataset: (id, district, search) => request(`/ops/${id}/dataset?${qs({ district: district || null, search: search || null })}`),
  opsReport: (id, body) => request(`/ops/${id}/report`, { method: "POST", body: JSON.stringify(body) }),
  opsDispatch: (id) => request(`/ops/${id}/dispatch`, { method: "POST" }),
  opsOutcome: (id, op, body) => request(`/ops/${id}/operations/${op}`, { method: "POST", body: JSON.stringify(body) }),
  opsSimulate: (id, allSuccess) => request(`/ops/${id}/simulate_outcomes?${qs({ all_success: allSuccess })}`, { method: "POST" }),
  opsClose: (id, force) => request(`/ops/${id}/close_day?${qs({ force })}`, { method: "POST" }),
  liveStart: (policy) => request("/live", { method: "POST", body: JSON.stringify({ policy }) }),
  liveState: (id, since = 0) => request(`/live/${id}?${qs({ since })}`),
  liveAdvance: (id, body) => request(`/live/${id}/advance`, { method: "POST", body: JSON.stringify(body) }),
  liveReport: (id, text, district) =>
    request(`/live/${id}/report`, { method: "POST", body: JSON.stringify({ text, district: district || null }) }),
};
