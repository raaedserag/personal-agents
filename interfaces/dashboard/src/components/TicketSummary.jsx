import { useCallback } from "react";
import { getTickets } from "../api";
import { usePolling } from "../hooks/usePolling";
import { Ticket, RefreshCw, AlertTriangle, Clock } from "lucide-react";

export default function TicketSummary({ profileId }) {
  const fetchTickets = useCallback(() => getTickets(profileId), [profileId]);
  const { data, loading, error, refresh } = usePolling(fetchTickets, 60000, [profileId]);

  const { myTickets, blockedTickets, staleTickets } = extractAll(data);

  return (
    <div className="panel jira-panel">
      <div className="panel-header">
        <h2><Ticket size={18} /> Jira Summary</h2>
        <button className="btn-sm btn-icon" onClick={refresh} title="Refresh">
          <RefreshCw size={14} className={loading ? "spin" : ""} />
        </button>
      </div>
      <div className="panel-body">
        {loading && !data && <div className="loading">Loading tickets...</div>}
        {error && <div className="error-msg">Error: {error}</div>}
        {data ? (
          <div className="ticket-digest-content">
            {myTickets.length > 0 && (
              <section>
                <h3 className="section-label">
                  <Ticket size={14} /> My Tickets ({myTickets.length})
                </h3>
                {myTickets.map((t) => <TicketRow key={t.key} ticket={t} />)}
              </section>
            )}
            {blockedTickets.length > 0 && (
              <section>
                <h3 className="section-label danger">
                  <AlertTriangle size={14} /> Blocked ({blockedTickets.length})
                </h3>
                {blockedTickets.map((t) => <TicketRow key={t.key} ticket={t} />)}
              </section>
            )}
            {staleTickets.length > 0 && (
              <section>
                <h3 className="section-label warning">
                  <Clock size={14} /> Stale ({staleTickets.length})
                </h3>
                {staleTickets.map((t) => <TicketRow key={t.key} ticket={t} />)}
              </section>
            )}
            {myTickets.length === 0 && blockedTickets.length === 0 && staleTickets.length === 0 && (
              <div className="empty-state">No ticket data available</div>
            )}
          </div>
        ) : !loading ? (
          <div className="empty-state">No ticket data available</div>
        ) : null}
      </div>
    </div>
  );
}

function TicketRow({ ticket }) {
  const t = ticket;
  return (
    <div className="pr-row">
      <div className="pr-main">
        <span className="ticket-key-badge">{t.key}</span>
        <span className="pr-title">{t.summary}</span>
      </div>
      <div className="pr-meta">
        <span className={`status-badge ${statusClass(t.status)}`}>{t.status}</span>
        <span className={`priority-badge ${priorityClass(t.priority)}`}>{t.priority}</span>
        <span className="ticket-assignee-sm">{t.assignee}</span>
      </div>
    </div>
  );
}

function extractAll(data) {
  const myTickets = [];
  const blockedTickets = [];
  const staleTickets = [];
  if (!data?.data) return { myTickets, blockedTickets, staleTickets };

  for (const [, agentResult] of Object.entries(data.data)) {
    const inner = agentResult?.data;
    if (typeof inner !== "object") continue;
    if (Array.isArray(inner.my_tickets)) myTickets.push(...inner.my_tickets);
    if (Array.isArray(inner.blocked_tickets)) blockedTickets.push(...inner.blocked_tickets);
    if (Array.isArray(inner.stale_tickets)) staleTickets.push(...inner.stale_tickets);
  }
  return { myTickets, blockedTickets, staleTickets };
}

function statusClass(s) {
  const l = (s || "").toLowerCase();
  if (l.includes("done") || l.includes("closed") || l.includes("resolved")) return "done";
  if (l.includes("progress")) return "in-progress";
  if (l.includes("blocked")) return "blocked";
  if (l.includes("review")) return "review";
  return "open";
}

function priorityClass(p) {
  const l = (p || "").toLowerCase();
  if (l.includes("high") || l.includes("critical") || l.includes("blocker")) return "high";
  if (l.includes("medium")) return "medium";
  return "low";
}
