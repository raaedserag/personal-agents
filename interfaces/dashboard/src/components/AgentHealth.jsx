import { useCallback } from "react";
import { getAgents } from "../api";
import { usePolling } from "../hooks/usePolling";
import { Activity, RefreshCw } from "lucide-react";

export default function AgentHealth() {
  const fetchAgents = useCallback(() => getAgents(), []);
  const { data, loading, error, refresh } = usePolling(fetchAgents, 15000);

  const agents = data?.agents || {};

  return (
    <div className="panel agent-panel">
      <div className="panel-header">
        <h2><Activity size={18} /> Agents</h2>
        <button className="btn-sm btn-icon" onClick={refresh} title="Refresh">
          <RefreshCw size={14} className={loading ? "spin" : ""} />
        </button>
      </div>
      <div className="panel-body">
        {error && <div className="error-msg">Error: {error}</div>}
        <div className="agent-grid">
          {Object.entries(agents).map(([id, info]) => {
            const h = info?.health || {};
            const ok = h.status === "ok";
            return (
              <div key={id} className={`agent-card ${ok ? "healthy" : "unhealthy"}`}>
                <div className="agent-status-dot" />
                <div className="agent-info">
                  <div className="agent-id">{id}</div>
                  <div className="agent-meta">
                    {h.profile && <span>{h.profile}</span>}
                    {h.scope && <span>{h.scope}</span>}
                    {h.version && <span>v{h.version}</span>}
                  </div>
                </div>
              </div>
            );
          })}
          {Object.keys(agents).length === 0 && !loading && (
            <div className="empty-state">No agents registered</div>
          )}
        </div>
      </div>
    </div>
  );
}
