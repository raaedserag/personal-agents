"""
Memory Store — SQLite-backed persistent memory for agents.

Replaces the file-based memory manager. Each agent writes to its own
namespace (agent_id), and shared context is accessible cross-agent.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .models import MemoryEntry, SharedContext

DEFAULT_DB_PATH = Path("/app/data/memory.db")


class MemoryStore:
    """Thread-safe SQLite memory store for a single agent."""

    def __init__(self, db_path: str | Path | None = None, agent_id: str = ""):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.agent_id = agent_id
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        with self._cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    profile_id TEXT DEFAULT '',
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_agent
                ON agent_memory(agent_id, memory_type, created_at DESC)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shared_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_agent TEXT NOT NULL,
                    context_type TEXT NOT NULL,
                    profile_id TEXT DEFAULT '',
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_shared_context
                ON shared_context(context_type, profile_id, resolved_at)
            """)

    # ── Agent Memory Operations ──────────────────────────────────

    def save_log(self, query: str, response: str, profile_id: str = "") -> int:
        """Log a query-response pair."""
        content = json.dumps({
            "query": query[:500],
            "response": response[:2000],
        })
        return self._insert_memory("query_log", content, profile_id)

    def save_summary(self, summary: str, profile_id: str = "") -> int:
        """Save a daily summary."""
        return self._insert_memory("daily_summary", summary, profile_id)

    def save_context(self, context: str, profile_id: str = "",
                     expires_hours: int | None = None) -> int:
        """Save arbitrary context with optional TTL."""
        return self._insert_memory("context", context, profile_id, expires_hours)

    def _insert_memory(self, memory_type: str, content: str,
                       profile_id: str = "", expires_hours: int | None = None) -> int:
        expires_at = None
        if expires_hours:
            expires_at = (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat()

        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO agent_memory (agent_id, profile_id, memory_type, content, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (self.agent_id, profile_id, memory_type, content, expires_at),
            )
            return cur.lastrowid or 0

    def get_recent_logs(self, limit: int = 10, profile_id: str | None = None) -> list[MemoryEntry]:
        """Fetch recent query logs."""
        return self._query_memories("query_log", limit, profile_id)

    def get_recent_summaries(self, days: int = 3, profile_id: str | None = None) -> list[MemoryEntry]:
        """Fetch daily summaries from recent days."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        with self._cursor() as cur:
            params: list = [self.agent_id, "daily_summary", since]
            sql = """SELECT * FROM agent_memory
                     WHERE agent_id = ? AND memory_type = ? AND created_at >= ?"""
            if profile_id:
                sql += " AND profile_id = ?"
                params.append(profile_id)
            sql += " ORDER BY created_at DESC"
            cur.execute(sql, params)
            return [self._row_to_entry(row) for row in cur.fetchall()]

    def get_recent_context(self, days: int = 3, profile_id: str | None = None) -> str:
        """Build a context string from recent summaries and logs. Drop-in replacement
        for the old load_recent_context()."""
        lines = []

        summaries = self.get_recent_summaries(days, profile_id)
        for s in summaries:
            lines.append(f"[{s.created_at.strftime('%Y-%m-%d')}] {s.content[:200]}")

        logs = self.get_recent_logs(5, profile_id)
        for log in logs:
            try:
                data = json.loads(log.content)
                lines.append(f"[{log.created_at.strftime('%Y-%m-%d %H:%M')}] Q: {data.get('query', '')[:100]}")
            except json.JSONDecodeError:
                lines.append(f"[{log.created_at.strftime('%Y-%m-%d %H:%M')}] {log.content[:100]}")

        return "\n".join(lines)

    def _query_memories(self, memory_type: str, limit: int = 10,
                        profile_id: str | None = None) -> list[MemoryEntry]:
        with self._cursor() as cur:
            params: list = [self.agent_id, memory_type]
            sql = """SELECT * FROM agent_memory
                     WHERE agent_id = ? AND memory_type = ?
                     AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)"""
            if profile_id:
                sql += " AND profile_id = ?"
                params.append(profile_id)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cur.execute(sql, params)
            return [self._row_to_entry(row) for row in cur.fetchall()]

    # ── Shared Context Operations ────────────────────────────────

    def publish_context(self, context_type: str, content: str,
                        profile_id: str = "") -> int:
        """Publish shared context visible to all agents."""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO shared_context (source_agent, context_type, profile_id, content)
                   VALUES (?, ?, ?, ?)""",
                (self.agent_id, context_type, profile_id, content),
            )
            return cur.lastrowid or 0

    def resolve_context(self, context_id: int) -> None:
        """Mark a shared context entry as resolved."""
        with self._cursor() as cur:
            cur.execute(
                "UPDATE shared_context SET resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
                (context_id,),
            )

    def get_active_contexts(self, context_type: str | None = None,
                            profile_id: str | None = None) -> list[SharedContext]:
        """Fetch unresolved shared context entries."""
        with self._cursor() as cur:
            params: list = []
            sql = "SELECT * FROM shared_context WHERE resolved_at IS NULL"
            if context_type:
                sql += " AND context_type = ?"
                params.append(context_type)
            if profile_id:
                sql += " AND profile_id = ?"
                params.append(profile_id)
            sql += " ORDER BY created_at DESC"
            cur.execute(sql, params)
            return [self._row_to_shared(row) for row in cur.fetchall()]

    # ── Cleanup ──────────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Remove expired memory entries. Returns count deleted."""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM agent_memory WHERE expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP"
            )
            return cur.rowcount

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            agent_id=row["agent_id"],
            profile_id=row["profile_id"],
            memory_type=row["memory_type"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
        )

    @staticmethod
    def _row_to_shared(row: sqlite3.Row) -> SharedContext:
        return SharedContext(
            id=row["id"],
            source_agent=row["source_agent"],
            context_type=row["context_type"],
            profile_id=row["profile_id"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
        )
