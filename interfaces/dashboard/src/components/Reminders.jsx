import { useCallback, useState } from "react";
import { getReminders, createReminder, completeReminder, snoozeReminder } from "../api";
import { usePolling } from "../hooks/usePolling";
import { ListTodo, RefreshCw, Plus, Check, Clock, X } from "lucide-react";

export default function Reminders({ profileId }) {
  const fetchReminders = useCallback(() => getReminders(profileId), [profileId]);
  const { data, loading, error, refresh } = usePolling(fetchReminders, 30000, [profileId]);
  const [showAdd, setShowAdd] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDue, setNewDue] = useState("");

  const reminders = data?.reminders || [];

  const handleAdd = async () => {
    if (!newTitle.trim()) return;
    await createReminder(newTitle, "", profileId, newDue || null, "normal");
    setNewTitle("");
    setNewDue("");
    setShowAdd(false);
    refresh();
  };

  const handleComplete = async (id) => {
    await completeReminder(id);
    refresh();
  };

  const handleSnooze = async (id) => {
    await snoozeReminder(id, 1);
    refresh();
  };

  return (
    <div className="panel reminder-panel">
      <div className="panel-header">
        <h2><ListTodo size={18} /> Reminders</h2>
        <div style={{ display: "flex", gap: "4px" }}>
          <button className="btn-sm btn-icon" onClick={() => setShowAdd(!showAdd)} title="Add">
            <Plus size={14} />
          </button>
          <button className="btn-sm btn-icon" onClick={refresh} title="Refresh">
            <RefreshCw size={14} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>
      <div className="panel-body">
        {showAdd && (
          <div className="reminder-add-form">
            <input
              type="text"
              className="reminder-input"
              placeholder="Remind me to..."
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              autoFocus
            />
            <input
              type="datetime-local"
              className="reminder-input reminder-date"
              value={newDue}
              onChange={(e) => setNewDue(e.target.value)}
            />
            <div className="reminder-add-actions">
              <button className="btn-sm" onClick={handleAdd}>Save</button>
              <button className="btn-sm btn-ghost" onClick={() => setShowAdd(false)}>Cancel</button>
            </div>
          </div>
        )}

        {loading && !data && <div className="loading">Loading...</div>}
        {error && <div className="error-msg">Error: {error}</div>}

        {reminders.length > 0 ? (
          <div className="reminder-list">
            {reminders.map((r) => (
              <div key={r.id} className={`reminder-item ${r.priority === "high" ? "high" : ""}`}>
                <div className="reminder-content">
                  <span className="reminder-title">{r.title}</span>
                  {r.due_at && (
                    <span className="reminder-due">
                      <Clock size={11} /> {r.due_at.replace("T", " ").slice(0, 16)}
                    </span>
                  )}
                </div>
                <div className="reminder-actions">
                  <button className="btn-icon-xs" onClick={() => handleSnooze(r.id)} title="Snooze 1h">
                    <Clock size={12} />
                  </button>
                  <button className="btn-icon-xs done" onClick={() => handleComplete(r.id)} title="Done">
                    <Check size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : !loading && !showAdd ? (
          <div className="empty-state">No reminders</div>
        ) : null}
      </div>
    </div>
  );
}
