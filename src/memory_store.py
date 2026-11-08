"""Persistent, user-scoped SQLite long-term memory."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import MEMORY_DB_PATH
from src.transactions import CATEGORIES


class MemoryStore:
    """Read and update profile, budgets, goals, and user-approved notes."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else MEMORY_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_profile (
                    user_id TEXT NOT NULL,
                    profile_key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, profile_key)
                );
                CREATE TABLE IF NOT EXISTS budgets (
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL CHECK (amount > 0),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, category)
                );
                CREATE TABLE IF NOT EXISTS goals (
                    user_id TEXT NOT NULL,
                    goal_key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, goal_key)
                );
                CREATE TABLE IF NOT EXISTS memory_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (user_id, note)
                );
                CREATE TABLE IF NOT EXISTS pending_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_budget_amount(value: str) -> float | None:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(amount) or amount <= 0:
            return None
        return amount

    def recall_memory(self, user_id: str) -> dict[str, Any]:
        if not user_id.strip():
            return {"error": "user_id must be a non-empty string."}
        with self._connect() as connection:
            profile = connection.execute(
                "SELECT profile_key, value FROM user_profile WHERE user_id = ? ORDER BY profile_key",
                (user_id,),
            ).fetchall()
            budgets = connection.execute(
                "SELECT category, amount FROM budgets WHERE user_id = ? ORDER BY category",
                (user_id,),
            ).fetchall()
            goals = connection.execute(
                "SELECT goal_key, value FROM goals WHERE user_id = ? ORDER BY goal_key",
                (user_id,),
            ).fetchall()
            notes = connection.execute(
                "SELECT note FROM memory_notes WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
        return {
            "user_id": user_id,
            "profile": {row["profile_key"]: row["value"] for row in profile},
            "budgets": {row["category"]: row["amount"] for row in budgets},
            "goals": {row["goal_key"]: row["value"] for row in goals},
            "notes": [row["note"] for row in notes],
        }

    def save_memory(
        self, user_id: str, kind: str, key: str, value: str, confirmed: bool = False
    ) -> dict[str, Any]:
        if not user_id.strip() or not key.strip():
            return {"error": "user_id and key must be non-empty strings."}
        if not confirmed:
            return {
                "saved": False,
                "confirmation_required": True,
                "message": "Nothing was saved. Ask the user to confirm this exact memory change.",
            }
        timestamp = self._timestamp()
        with self._connect() as connection:
            if kind == "budget":
                if key not in CATEGORIES:
                    return {"error": f"Unknown category. Use one of: {', '.join(CATEGORIES)}."}
                amount = self._parse_budget_amount(value)
                if amount is None:
                    return {"error": "A budget value must be a positive number."}
                connection.execute(
                    """INSERT INTO budgets(user_id, category, amount, updated_at) VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, category) DO UPDATE SET amount=excluded.amount, updated_at=excluded.updated_at""",
                    (user_id, key, amount, timestamp),
                )
                return {"saved": True, "kind": kind, "key": key, "value": amount}
            if kind == "goal":
                connection.execute(
                    """INSERT INTO goals(user_id, goal_key, value, updated_at) VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, goal_key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                    (user_id, key, value, timestamp),
                )
                return {"saved": True, "kind": kind, "key": key, "value": value}
            if kind == "profile":
                connection.execute(
                    """INSERT INTO user_profile(user_id, profile_key, value, updated_at) VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, profile_key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                    (user_id, key, value, timestamp),
                )
                return {"saved": True, "kind": kind, "key": key, "value": value}
            if kind == "note":
                connection.execute(
                    "INSERT OR IGNORE INTO memory_notes(user_id, note, created_at) VALUES (?, ?, ?)",
                    (user_id, value, timestamp),
                )
                return {"saved": True, "kind": kind, "key": key}
        return {"error": "kind must be budget, goal, profile, or note."}

    def delete_memory(self, user_id: str, kind: str, key: str, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            return {"deleted": False, "confirmation_required": True}
        tables = {
            "budget": ("budgets", "category"),
            "goal": ("goals", "goal_key"),
            "profile": ("user_profile", "profile_key"),
        }
        if kind == "note":
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM memory_notes WHERE user_id = ? AND note = ?", (user_id, key)
                )
            return {"deleted": cursor.rowcount > 0, "kind": kind}
        if kind not in tables:
            return {"error": "kind must be budget, goal, profile, or note."}
        table, field = tables[kind]
        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE user_id = ? AND {field} = ?", (user_id, key)
            )
        return {"deleted": cursor.rowcount > 0, "kind": kind, "key": key}

    def get_budget(self, user_id: str, category: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT category, amount FROM budgets WHERE user_id = ? AND category = ?",
                (user_id, category),
            ).fetchone()
        return dict(row) if row else None

    def stage_memory(self, user_id: str, kind: str, key: str, value: str) -> dict[str, Any]:
        if kind not in {"budget", "goal", "profile", "note"}:
            return {"error": "kind must be budget, goal, profile, or note."}
        if kind == "budget":
            if key not in CATEGORIES:
                return {"error": f"Unknown category. Use one of: {', '.join(CATEGORIES)}."}
            if self._parse_budget_amount(value) is None:
                return {"error": "A budget value must be a positive number."}
        timestamp = self._timestamp()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO pending_memory(user_id, kind, memory_key, value, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (user_id, kind, key, value, timestamp),
            )
        return {
            "saved": False,
            "confirmation_required": True,
            "change_id": cursor.lastrowid,
            "proposed": {"kind": kind, "key": key, "value": value},
        }

    def has_pending_memory(self, user_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM pending_memory WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return row is not None

    def get_pending_memory(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT id, kind, memory_key, value FROM pending_memory
                WHERE user_id = ? ORDER BY id DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def discard_latest_memory(self, user_id: str) -> dict[str, Any]:
        pending = self.get_pending_memory(user_id)
        if pending is None:
            return {"discarded": False, "error": "There is no pending memory change to discard."}
        with self._connect() as connection:
            connection.execute("DELETE FROM pending_memory WHERE id = ?", (pending["id"],))
        return {
            "discarded": True,
            "kind": pending["kind"],
            "key": pending["memory_key"],
            "value": pending["value"],
        }

    def confirm_latest_memory(self, user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pending_memory WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            pending = dict(row) if row is not None else None
        if pending is None:
            return {"error": "There is no pending memory change to confirm."}
        result = self.save_memory(
            user_id,
            pending["kind"],
            pending["memory_key"],
            pending["value"],
            confirmed=True,
        )
        if result.get("saved"):
            with self._connect() as connection:
                connection.execute("DELETE FROM pending_memory WHERE id = ?", (pending["id"],))
        return result
