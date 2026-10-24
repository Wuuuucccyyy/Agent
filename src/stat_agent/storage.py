"""Append-only run snapshots; payloads preserve schemas, evidence and versions."""
import json
import sqlite3
from pathlib import Path


def save_run(database: Path, run_id: str, payload: dict) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO runs VALUES (?, ?)",
                           (run_id, json.dumps(payload, ensure_ascii=False, allow_nan=False)))


def read_run(database: Path, run_id: str) -> dict:
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise KeyError(run_id)
    return json.loads(row[0])
