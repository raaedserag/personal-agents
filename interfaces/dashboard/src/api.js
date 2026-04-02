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

// Notifications / Activity Feed
export const getNotifications = (profileId) =>
  request("GET", "/notifications", { params: profileId ? { profile_id: profileId } : {} });

// Query
export const sendQuery = (query, profileId) =>
  request("POST", "/query", { body: { query, profile_id: profileId || "" } });

// Context
export const switchContext = (profileId) => request("GET", `/context/${profileId}`);

// Reminders
export const getReminders = (profileId) =>
  request("GET", "/reminders", { params: profileId ? { profile_id: profileId } : {} });
export const createReminder = (title, body, profileId, dueAt, priority) =>
  request("POST", "/reminders", { body: { title, body, profile_id: profileId || "", due_at: dueAt || null, priority: priority || "normal" } });
export const completeReminder = (id) => request("POST", `/reminders/${id}/complete`);
export const snoozeReminder = (id, hours) => request("POST", `/reminders/${id}/snooze`, { body: { hours } });
export const deleteReminder = (id) => request("DELETE", `/reminders/${id}`);

// Scheduler
export const getSchedulerStatus = () => request("GET", "/scheduler/status");
export const triggerSchedule = (name) => request("POST", `/scheduler/trigger/${name}`);
export const getLatestReports = () => request("GET", "/reports/latest");

export default API_BASE;
