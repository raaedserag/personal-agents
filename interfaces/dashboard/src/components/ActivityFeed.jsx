import { useCallback } from "react";
import { getNotifications } from "../api";
import { usePolling } from "../hooks/usePolling";
import { Bell, RefreshCw, MessageSquare, AtSign } from "lucide-react";

export default function ActivityFeed({ profileId }) {
  const fetchNotifs = useCallback(() => getNotifications(profileId), [profileId]);
  const { data, loading, error, refresh } = usePolling(fetchNotifs, 120000, [profileId]);

  const { activity, mentioned } = extractNotifs(data);

  return (
    <div className="panel activity-panel">
      <div className="panel-header">
        <h2><Bell size={18} /> Activity Feed</h2>
        <button className="btn-sm btn-icon" onClick={refresh} title="Refresh">
          <RefreshCw size={14} className={loading ? "spin" : ""} />
        </button>
      </div>
      <div className="panel-body">
        {loading && !data && <div className="loading">Loading activity...</div>}
        {error && <div className="error-msg">Error: {error}</div>}
        {data ? (
          <div className="activity-feed-content">
            {mentioned.length > 0 && (
              <section>
                <h3 className="section-label warning">
                  <AtSign size={14} /> Mentions ({mentioned.length})
                </h3>
                {mentioned.map((item) => (
                  <ActivityRow key={item.key} item={item} isMention />
                ))}
              </section>
            )}
            {activity.length > 0 && (
              <section>
                <h3 className="section-label">
                  <MessageSquare size={14} /> Recent Updates ({activity.length})
                </h3>
                {activity.map((item) => (
                  <ActivityRow key={item.key} item={item} />
                ))}
              </section>
            )}
            {activity.length === 0 && mentioned.length === 0 && (
              <div className="empty-state">No recent activity</div>
            )}
          </div>
        ) : !loading ? (
          <div className="empty-state">No activity data</div>
        ) : null}
      </div>
    </div>
  );
}

function ActivityRow({ item, isMention }) {
  const comment = item.latest_comment;
  return (
    <div className={`activity-row ${isMention ? "mention" : ""}`}>
      <div className="activity-header">
        <span className="ticket-key-badge">{item.key}</span>
        <span className="activity-summary">{item.summary}</span>
      </div>
      {comment && (
        <div className="activity-comment">
          <span className="activity-author">{comment.author}:</span>
          <span className="activity-body">{comment.body}</span>
        </div>
      )}
      <div className="activity-meta">
        <span className={`status-badge ${statusClass(item.status)}`}>{item.status}</span>
        <span className="activity-project">{item.project}</span>
      </div>
    </div>
  );
}

function extractNotifs(data) {
  const activity = [];
  const mentioned = [];
  if (!data?.data) return { activity, mentioned };

  for (const [, agentResult] of Object.entries(data.data)) {
    const inner = agentResult?.data;
    if (typeof inner !== "object") continue;
    if (Array.isArray(inner.recent_activity)) activity.push(...inner.recent_activity);
    if (Array.isArray(inner.mentioned)) mentioned.push(...inner.mentioned);
  }
  return { activity, mentioned };
}

function statusClass(s) {
  const l = (s || "").toLowerCase();
  if (l.includes("done") || l.includes("closed") || l.includes("resolved")) return "done";
  if (l.includes("progress")) return "in-progress";
  if (l.includes("blocked")) return "blocked";
  if (l.includes("review")) return "review";
  return "open";
}
