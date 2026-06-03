# patient_store.py
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DB_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with _DB_LOCK, sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                patient_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                sex TEXT NOT NULL,
                age INTEGER NOT NULL,
                created_at_iso TEXT NOT NULL,
                updated_at_iso TEXT NOT NULL
            )
            """
        )
        conn.commit()


def upsert_patient(
    db_path: str,
    *,
    patient_id: str,
    display_name: str,
    sex: str,
    age: int,
) -> Dict[str, Any]:
    now = _now_iso()
    with _DB_LOCK, sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO patients (patient_id, display_name, sex, age, created_at_iso, updated_at_iso)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(patient_id) DO UPDATE SET
                display_name=excluded.display_name,
                sex=excluded.sex,
                age=excluded.age,
                updated_at_iso=excluded.updated_at_iso
            """,
            (patient_id, display_name, sex, age, now, now),
        )
        conn.commit()

    return get_patient(db_path, patient_id=patient_id)  # type: ignore[return-value]


def get_patient(db_path: str, *, patient_id: str) -> Optional[Dict[str, Any]]:
    with _DB_LOCK, sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT patient_id, display_name, sex, age, created_at_iso, updated_at_iso
            FROM patients
            WHERE patient_id=?
            """,
            (patient_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "patient_id": row[0],
        "display_name": row[1],
        "sex": row[2],
        "age": row[3],
        "created_at_iso": row[4],
        "updated_at_iso": row[5],
    }


def list_patients(db_path: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    with _DB_LOCK, sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT patient_id, display_name, sex, age, created_at_iso, updated_at_iso
            FROM patients
            ORDER BY updated_at_iso DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = cur.fetchall()

    return [
        {
            "patient_id": r[0],
            "display_name": r[1],
            "sex": r[2],
            "age": r[3],
            "created_at_iso": r[4],
            "updated_at_iso": r[5],
        }
        for r in rows
    ]
