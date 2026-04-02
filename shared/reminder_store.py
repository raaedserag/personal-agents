"""
Reminder Store — SQLite-backed personal reminders and TODO items.

This is NOT Jira. This is your personal "remember to..." list.
Stores reminders with optional due dates, supports completion and snoozing.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any

DB_PATH = os.getenv("REMINDER_DB_PATH", "/app/data/reminders.db")

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _init_db(_conn)
    return _conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT DEFAULT '',
            profile_id TEXT DEFAULT '',
            due_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT,
            snoozed_until TEXT,
            priority TEXT DEFAULT 'normal',
            source TEXT DEFAULT 'manual'
        )
    """)
    conn.commit()


def add_reminder(
    title: str,
    body: str = "",
    profile_id: str = "",
    due_at: str | None = None,
    priority: str = "normal",
    source: str = "manual",
) -> dict:
    """Create a new reminder."""
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO reminders (title, body, profile_id, due_at, priority, source) VALUES (?, ?, ?, ?, ?, ?)",
        (title, body, profile_id, due_at, priority, source),
    )
    conn.commit()
    return {"id": cur.lastrowid, "title": title, "due_at": due_at, "status": "created"}


def list_reminders(
    profile_id: str = "",
    include_completed: bool = False,
    due_before: str | None = None,
) -> list[dict]:
    """List reminders, optionally filtered."""
    conn = _get_conn()
    clauses = []
    params: list[Any] = []

    if not include_completed:
        clauses.append("completed_at IS NULL")
    if profile_id:
        clauses.append("(profile_id = ? OR profile_id = '')")
        params.append(profile_id)
    if due_before:
        clauses.append("(due_at IS NULL OR due_at <= ?)")
        params.append(due_before)

    # Filter out snoozed reminders
    clauses.append("(snoozed_until IS NULL OR snoozed_until <= datetime('now'))")

    where = " AND ".join(clauses) if clauses else "1=1"
    rows = conn.execute(
        f"SELECT * FROM reminders WHERE {where} ORDER BY "
        "CASE WHEN due_at IS NOT NULL THEN 0 ELSE 1 END, due_at ASC, priority DESC, created_at ASC",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_due_reminders(profile_id: str = "") -> list[dict]:
    """Get reminders that are due now or overdue."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    return list_reminders(profile_id=profile_id, due_before=now)


def complete_reminder(reminder_id: int) -> dict:
    """Mark a reminder as done."""
    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE reminders SET completed_at = ? WHERE id = ?", (now, reminder_id))
    conn.commit()
    return {"id": reminder_id, "status": "completed"}


def snooze_reminder(reminder_id: int, hours: int = 1) -> dict:
    """Snooze a reminder for N hours."""
    conn = _get_conn()
    until = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
    conn.execute("UPDATE reminders SET snoozed_until = ? WHERE id = ?", (until, reminder_id))
    conn.commit()
    return {"id": reminder_id, "snoozed_until": until}


def delete_reminder(reminder_id: int) -> dict:
    """Delete a reminder."""
    conn = _get_conn()
    conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    return {"id": reminder_id, "status": "deleted"}
