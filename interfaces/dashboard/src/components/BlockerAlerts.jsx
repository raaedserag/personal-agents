import { useCallback } from "react";
import { getBriefing } from "../api";
import { usePolling } from "../hooks/usePolling";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function BlockerAlerts({ profileId }) {
  const fetchBlockers = useCallback(() => getBriefing("blockers", profileId), [profileId]);
  const { data, loading, error, refresh } = usePolling(fetchBlockers, 60000, [profileId]);

  const blockers = extractBlockers(data);

  return (
    <div className={`panel blocker-panel ${blockers.length > 0 ? "has-blockers" : ""}`}>
      <div className="panel-header">
        <h2>
          <AlertTriangle size={18} />
          {" "}Blockers
          {blockers.length > 0 && <span className="badge danger">{blockers.length}</span>}
        </h2>
        <button className="btn-sm btn-icon" onClick={refresh} title="Refresh">
          <RefreshCw size={14} className={loading ? "spin" : ""} />
        </button>
      </div>
      <div className="panel-body">
        {loading && !data && <div className="loading">Checking blockers...</div>}
        {error && <div className="error-msg">Error: {error}</div>}
        {blockers.length > 0 ? (
          <div className="blocker-list">
            {blockers.map((b, i) => (
              <div key={i} className="blocker-item">
                <div className="blocker-key">{b.key}</div>
                <div className="blocker-summary">{b.summary}</div>
                <div className="blocker-meta">
                  <span>Assignee: {b.assignee}</span>
                  <span className={`priority-badge ${priorityClass(b.priority)}`}>{b.priority}</span>
                  {b.profile && <span className="blocker-profile">{b.profile}</span>}
                </div>
              </div>
            ))}
          </div>
        ) : !loading ? (
          <div className="empty-state success">No active blockers</div>
        ) : null}
      </div>
    </div>
  );
}

function extractBlockers(data) {
  if (!data) return [];
  const blockers = [];
  const d = data?.data;

  // Planner synthesized: { data: { data: { markdown } } } — use structured check instead
  // Raw conductor: { data: { jira-yassir: { status, data: "..." } } }
  if (typeof d === "object") {
    for (const [agentId, val] of Object.entries(d)) {
      const profile = agentId.replace("jira-", "");
      if (val?.status === "ok" && val?.data) {
        const inner = val.data;
        // Structured standup data
        if (typeof inner === "object" && inner?.blocked_tickets) {
          for (const t of inner.blocked_tickets) {
            blockers.push({ ...t, profile });
          }
        }
      }
    }
  }
  return blockers;
}

function priorityClass(p) {
  const l = (p || "").toLowerCase();
  if (l.includes("high") || l.includes("critical") || l.includes("blocker")) return "high";
  if (l.includes("medium")) return "medium";
  return "low";
}
