import { useCallback } from "react";
import { getBriefing } from "../api";
import { usePolling } from "../hooks/usePolling";
import { GitPullRequest, RefreshCw, ExternalLink } from "lucide-react";

export default function PRDigest({ profileId }) {
  const fetchPRs = useCallback(() => getBriefing("prs", profileId), [profileId]);
  const { data, loading, error, refresh } = usePolling(fetchPRs, 60000, [profileId]);

  const digest = extractDigest(data);

  return (
    <div className="panel pr-panel">
      <div className="panel-header">
        <h2><GitPullRequest size={18} /> Pull Requests</h2>
        <button className="btn-sm btn-icon" onClick={refresh} title="Refresh">
          <RefreshCw size={14} className={loading ? "spin" : ""} />
        </button>
      </div>
      <div className="panel-body">
        {loading && !data && <div className="loading">Loading PRs...</div>}
        {error && <div className="error-msg">Error: {error}</div>}
        {digest ? (
          <div className="pr-digest-content">
            {digest.my_prs?.length > 0 && (
              <section>
                <h3 className="section-label">Your PRs ({digest.my_prs.length})</h3>
                {digest.my_prs.map((pr) => <PRRow key={`${pr.repo}#${pr.number}`} pr={pr} />)}
              </section>
            )}
            {digest.review_requested?.length > 0 && (
              <section>
                <h3 className="section-label warning">Review Requested ({digest.review_requested.length})</h3>
                {digest.review_requested.map((pr) => <PRRow key={`${pr.repo}#${pr.number}`} pr={pr} />)}
              </section>
            )}
            {digest.stale_prs?.length > 0 && (
              <section>
                <h3 className="section-label danger">Stale ({digest.stale_prs.length})</h3>
                {digest.stale_prs.map((pr) => <PRRow key={`${pr.repo}#${pr.number}`} pr={pr} />)}
              </section>
            )}
            {digest.open_prs?.length > 0 &&
              !digest.my_prs?.length &&
              !digest.review_requested?.length && (
              <section>
                <h3 className="section-label">All Open ({digest.open_prs.length})</h3>
                {digest.open_prs.slice(0, 10).map((pr) => <PRRow key={`${pr.repo}#${pr.number}`} pr={pr} />)}
              </section>
            )}
            {!digest.open_prs?.length && !digest.my_prs?.length && (
              <div className="empty-state">No open PRs</div>
            )}
          </div>
        ) : !loading ? (
          <div className="empty-state">No PR data available</div>
        ) : null}
      </div>
    </div>
  );
}

function PRRow({ pr }) {
  const repoShort = pr.repo?.split("/").pop() || pr.repo;
  const ciClass = pr.ci_status === "success" ? "ci-pass" : pr.ci_status === "failure" ? "ci-fail" : "ci-unknown";

  return (
    <div className="pr-row">
      <div className="pr-main">
        <span className="pr-repo">{repoShort}</span>
        <span className="pr-number">#{pr.number}</span>
        <span className="pr-title">{pr.title}</span>
      </div>
      <div className="pr-meta">
        <span className="pr-author">{pr.author}</span>
        <span className={`pr-status ${pr.status}`}>{pr.status}</span>
        <span className={`pr-ci ${ciClass}`}>{pr.ci_status || "?"}</span>
        {pr.url && (
          <a href={pr.url} target="_blank" rel="noreferrer" className="pr-link">
            <ExternalLink size={12} />
          </a>
        )}
      </div>
    </div>
  );
}

function extractDigest(data) {
  if (!data) return null;
  // Planner response format or raw conductor format
  const d = data?.data;
  if (typeof d === "object") {
    // Planner: { data: { data: { raw_data: { github: ... } } } }
    if (d?.data?.raw_data?.github) {
      const ghData = Object.values(d.data.raw_data.github)[0];
      return ghData;
    }
    // Raw conductor format: { github-yassir: { status: ok, data: { ... } } }
    for (const [, val] of Object.entries(d)) {
      if (val?.status === "ok" && val?.data) return val.data;
      if (val?.open_prs) return val;
    }
  }
  return null;
}
