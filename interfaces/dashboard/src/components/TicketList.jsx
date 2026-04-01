import { useCallback } from "react";
import { getTickets } from "../api";
import { usePolling } from "../hooks/usePolling";
import { RefreshCw, Ticket } from "lucide-react";

export default function TicketList({ profileId }) {
  const fetchTickets = useCallback(() => getTickets(profileId), [profileId]);
  const { data, loading, error, refresh } = usePolling(fetchTickets, 60000, [profileId]);

  const tickets = extractTickets(data);

  return (
    <div className="panel ticket-panel">
      <div className="panel-header">
        <h2><Ticket size={18} /> Tickets</h2>
        <button className="btn-sm btn-icon" onClick={refresh} title="Refresh">
          <RefreshCw size={14} className={loading ? "spin" : ""} />
        </button>
      </div>
      <div className="panel-body">
        {loading && !data && <div className="loading">Loading tickets...</div>}
        {error && <div className="error-msg">Error: {error}</div>}
        {tickets.length > 0 ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Key</th>
                <th>Summary</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Assignee</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((t) => (
                <tr key={t.key}>
                  <td className="ticket-key">{t.key}</td>
                  <td className="ticket-summary">{t.summary}</td>
                  <td><span className={`status-badge ${statusClass(t.status)}`}>{t.status}</span></td>
                  <td><span className={`priority-badge ${priorityClass(t.priority)}`}>{t.priority}</span></td>
                  <td className="ticket-assignee">{t.assignee}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : !loading ? (
          <div className="empty-state">No open tickets</div>
        ) : null}
      </div>
    </div>
  );
}

function extractTickets(data) {
  if (!data?.data) return [];
  const tickets = [];
  for (const [, agentResult] of Object.entries(data.data)) {
    const inner = agentResult?.data;
    if (typeof inner === "object" && inner?.my_tickets) {
      tickets.push(...inner.my_tickets);
    }
  }
  return tickets;
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
