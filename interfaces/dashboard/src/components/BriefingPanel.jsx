import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { getBriefing } from "../api";
import { usePolling } from "../hooks/usePolling";
import { Sun, Moon, AlertTriangle, RefreshCw } from "lucide-react";

const TYPES = [
  { id: "morning", label: "Morning", icon: Sun },
  { id: "eod", label: "EOD", icon: Moon },
  { id: "blockers", label: "Blockers", icon: AlertTriangle },
];

export default function BriefingPanel({ profileId }) {
  const [briefingType, setBriefingType] = useState("morning");

  const fetchBriefing = useCallback(
    () => getBriefing(briefingType, profileId),
    [briefingType, profileId]
  );

  const { data, loading, error, refresh } = usePolling(fetchBriefing, 0, [briefingType, profileId]);

  const markdown = extractMarkdown(data);

  return (
    <div className="panel briefing-panel">
      <div className="panel-header">
        <h2>Briefing</h2>
        <div className="briefing-tabs">
          {TYPES.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`btn-sm ${briefingType === id ? "active" : ""}`}
              onClick={() => setBriefingType(id)}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
          <button className="btn-sm btn-icon" onClick={refresh} title="Refresh">
            <RefreshCw size={14} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>
      <div className="panel-body">
        {loading && !data && <div className="loading">Generating briefing...</div>}
        {error && <div className="error-msg">Error: {error}</div>}
        {markdown ? (
          <div className="markdown-content">
            <ReactMarkdown>{markdown}</ReactMarkdown>
          </div>
        ) : data && !loading ? (
          <pre className="raw-data">{JSON.stringify(data, null, 2)}</pre>
        ) : null}
      </div>
    </div>
  );
}

function extractMarkdown(data) {
  if (!data) return null;
  // Planner response: { data: { data: { markdown: "..." } } }
  const d = data?.data;
  if (typeof d === "object") {
    if (d?.markdown) return d.markdown;
    if (d?.data?.markdown) return d.data.markdown;
  }
  return null;
}
