from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DB_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def init_sessions_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with _DB_LOCK, sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL,
                started_at_iso TEXT NOT NULL,
                ended_at_iso TEXT,
                stopped_at TEXT,
                duration_sec REAL,
                note TEXT,
                metrics_json TEXT
            )
            """
        )
        conn.commit()


def start_session(
    db_path: str,
    *,
    session_id: str,
    patient_id: str,
    note: str = "",
) -> Dict[str, Any]:
    now = _now_iso()
    with _DB_LOCK, sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO sessions (session_id, patient_id, started_at_iso, note)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, patient_id, now, note),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()

    return _row_to_dict(row)


def stop_session(
    db_path: str,
    *,
    session_id: str,
    duration_sec: float,
    metrics_json: str,
    note: str = "",
) -> Dict[str, Any]:
    now = _now_iso()
    with _DB_LOCK, sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            UPDATE sessions
            SET ended_at_iso = ?,
                stopped_at = ?,
                duration_sec = ?,
                metrics_json = ?,
                note = ?
            WHERE session_id = ?
            """,
            (now, now, float(duration_sec), metrics_json, note, session_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Session not found: {session_id}")
        conn.commit()
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()

    return _row_to_dict(row)


def list_sessions(
    db_path: str,
    *,
    patient_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 5000))
    query = "SELECT * FROM sessions"
    params: list[Any] = []

    if patient_id:
        query += " WHERE patient_id = ?"
        params.append(patient_id)

    query += " ORDER BY started_at_iso DESC LIMIT ?"
    params.append(limit)

    with _DB_LOCK, sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    return [_row_to_dict(row) for row in rows]
