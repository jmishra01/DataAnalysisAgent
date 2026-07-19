"""Durable conversation memory backed by the Python standard-library SQLite driver."""

import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path

from .errors import SessionConflictError
from .schemas import AgentResponse, ConversationTurn

_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def file_fingerprint(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ConversationMemory:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                csv_path TEXT NOT NULL,
                csv_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                insights_json TEXT NOT NULL,
                clarifications_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_turns_session_id ON turns(session_id, id);
            """
        )

    def open_session(self, csv_path: str, session_id: str | None = None) -> str:
        resolved_path = str(Path(csv_path).resolve())
        fingerprint = file_fingerprint(resolved_path)
        selected_id = session_id or uuid.uuid4().hex[:12]
        if not _SESSION_ID.fullmatch(selected_id):
            raise ValueError("Session ID must be 1-64 letters, numbers, dots, dashes, or underscores.")

        existing = self.connection.execute(
            "SELECT csv_path, csv_fingerprint FROM sessions WHERE session_id = ?",
            (selected_id,),
        ).fetchone()
        if existing and existing["csv_fingerprint"] != fingerprint:
            raise SessionConflictError(
                f"Session '{selected_id}' belongs to a different CSV. Choose another session ID."
            )
        if not existing:
            self.connection.execute(
                "INSERT INTO sessions(session_id, csv_path, csv_fingerprint) VALUES (?, ?, ?)",
                (selected_id, resolved_path, fingerprint),
            )
            self.connection.commit()
        return selected_id

    def load_turns(self, session_id: str, limit: int) -> list[ConversationTurn]:
        rows = self.connection.execute(
            """
            SELECT question, status, message, insights_json, clarifications_json, created_at
            FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [
            ConversationTurn(
                question=row["question"],
                status=row["status"],
                message=row["message"],
                insights=json.loads(row["insights_json"]),
                clarifications=json.loads(row["clarifications_json"]),
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        ]

    def append(self, session_id: str, question: str, response: AgentResponse) -> None:
        self.connection.execute(
            """
            INSERT INTO turns(
                session_id, question, status, message, insights_json, clarifications_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                question,
                response.status,
                response.message,
                json.dumps(response.insights[:6]),
                json.dumps(response.questions),
            ),
        )
        self.connection.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (session_id,),
        )
        self.connection.commit()

    def clear(self, session_id: str) -> None:
        self.connection.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
