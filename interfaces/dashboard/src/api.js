const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:10000";

async function request(method, path, { body, params } = {}) {
  let url = `${API_BASE}${path}`;
  if (params) {
    const qs = new URLSearchParams(params).toString();
    if (qs) url += `?${qs}`;
  }

  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(url, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

// Auth
export const verifyPin = (pin) => request("POST", "/auth/verify", { body: { pin } });

// Health
export const getHealth = () => request("GET", "/health");
export const getAgents = () => request("GET", "/agents");

// Briefings
export const getBriefing = (type, profileId) =>
  request("GET", `/briefing/${type}`, { params: profileId ? { profile_id: profileId } : {} });

// Tickets
export const getTickets = (profileId) =>
  request("GET", "/briefing/tickets", { params: profileId ? { profile_id: profileId } : {} });

// Query
export const sendQuery = (query, profileId) =>
  request("POST", "/query", { body: { query, profile_id: profileId || "" } });

// Context
export const switchContext = (profileId) => request("GET", `/context/${profileId}`);

// Scheduler
export const getSchedulerStatus = () => request("GET", "/scheduler/status");
export const triggerSchedule = (name) => request("POST", `/scheduler/trigger/${name}`);
export const getLatestReports = () => request("GET", "/reports/latest");

export default API_BASE;
