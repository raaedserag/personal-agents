import { useState } from "react";
import { sendQuery } from "../api";
import ReactMarkdown from "react-markdown";
import { Search, Loader } from "lucide-react";

export default function QueryBar({ profileId }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await sendQuery(query, profileId);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="query-bar-container">
      <form className="query-bar" onSubmit={handleSubmit}>
        <Search size={16} className="query-icon" />
        <input
          type="text"
          placeholder="Ask anything... (e.g., 'my blocked tickets', 'open PRs', 'morning briefing')"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? <Loader size={16} className="spin" /> : "Ask"}
        </button>
      </form>
      {error && <div className="error-msg">{error}</div>}
      {result && (
        <div className="query-results">
          {result.routed_to && (
            <div className="query-routed">
              Routed to: {Object.values(result.routed_to).flat().join(", ")}
            </div>
          )}
          {result.results &&
            Object.entries(result.results).map(([agentId, res]) => (
              <div key={agentId} className="query-result-card">
                <div className="query-result-agent">{agentId}</div>
                <div className="query-result-body">
                  {typeof res?.data === "string" ? (
                    <pre>{res.data}</pre>
                  ) : res?.data?.markdown ? (
                    <ReactMarkdown>{res.data.markdown}</ReactMarkdown>
                  ) : (
                    <pre>{JSON.stringify(res?.data || res, null, 2)}</pre>
                  )}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
