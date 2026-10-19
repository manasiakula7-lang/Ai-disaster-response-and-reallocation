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
};
