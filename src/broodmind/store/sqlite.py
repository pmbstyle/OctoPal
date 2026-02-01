from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from broodmind.config.settings import Settings
from broodmind.store.base import Store
from broodmind.store.models import (
    AuditEvent,
    IntentRecord,
    MemoryEntry,
    PermitRecord,
    WorkerRecord,
    WorkerTemplateRecord,
)


class SQLiteStore(Store):
    def __init__(self, settings: Settings) -> None:
        settings.state_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = settings.state_dir / "broodmind.db"
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workers (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                task TEXT NOT NULL,
                granted_caps_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS intents (
                id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                risk TEXT NOT NULL,
                requires_approval INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS permits (
                id TEXT PRIMARY KEY,
                intent_id TEXT NOT NULL,
                intent_type TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                correlation_id TEXT,
                level TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding_json TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS worker_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                worker_entrypoint TEXT NOT NULL,
                worker_files_json TEXT NOT NULL,
                requested_caps_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_state (
                chat_id INTEGER PRIMARY KEY,
                bootstrapped_at TEXT
            );
            """
        )
        self._conn.commit()
        self._ensure_schema_upgrades()

    def _ensure_schema_upgrades(self) -> None:
        try:
            self._conn.execute("ALTER TABLE permits ADD COLUMN intent_type TEXT NOT NULL DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

    def create_worker(self, record: WorkerRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO workers (id, status, task, granted_caps_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.status,
                record.task,
                json.dumps(record.granted_caps),
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ),
        )
        self._conn.commit()

    def update_worker_status(self, worker_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE workers SET status = ?, updated_at = ? WHERE id = ?",
            (status, _utc_now().isoformat(), worker_id),
        )
        self._conn.commit()

    def list_workers(self) -> list[WorkerRecord]:
        cursor = self._conn.execute("SELECT * FROM workers ORDER BY created_at DESC")
        return [self._row_to_worker(row) for row in cursor.fetchall()]

    def save_intent(self, record: IntentRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO intents (id, worker_id, type, payload_json, payload_hash, risk, requires_approval, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.worker_id,
                record.type,
                json.dumps(record.payload),
                record.payload_hash,
                record.risk,
                1 if record.requires_approval else 0,
                record.status,
                record.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def update_intent_status(self, intent_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE intents SET status = ? WHERE id = ?",
            (status, intent_id),
        )
        self._conn.commit()

    def create_permit(self, record: PermitRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO permits (id, intent_id, intent_type, worker_id, payload_hash, expires_at, consumed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.intent_id,
                record.intent_type,
                record.worker_id,
                record.payload_hash,
                record.expires_at.isoformat(),
                record.consumed_at.isoformat() if record.consumed_at else None,
                record.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def consume_permit_atomic(self, permit_id: str, now: datetime) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE permits
            SET consumed_at = ?
            WHERE id = ? AND consumed_at IS NULL AND expires_at > ?
            """,
            (now.isoformat(), permit_id, now.isoformat()),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def get_permit(self, permit_id: str, now: datetime) -> PermitRecord | None:
        cursor = self._conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,))
        row = cursor.fetchone()
        if not row:
            return None
        record = self._row_to_permit(row)
        if record.consumed_at is not None:
            return None
        if record.expires_at <= now:
            return None
        return record

    def append_audit(self, event: AuditEvent) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_events (id, ts, correlation_id, level, event_type, data_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.ts.isoformat(),
                event.correlation_id,
                event.level,
                event.event_type,
                json.dumps(event.data),
            ),
        )
        self._conn.commit()

    def list_audit(self, limit: int = 100) -> list[AuditEvent]:
        cursor = self._conn.execute(
            "SELECT * FROM audit_events ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_audit(row) for row in cursor.fetchall()]

    def get_audit(self, event_id: str) -> AuditEvent | None:
        cursor = self._conn.execute("SELECT * FROM audit_events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_audit(row)

    def upsert_worker_template(self, record: WorkerTemplateRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO worker_templates (
                id, name, description, worker_entrypoint, worker_files_json,
                requested_caps_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                worker_entrypoint = excluded.worker_entrypoint,
                worker_files_json = excluded.worker_files_json,
                requested_caps_json = excluded.requested_caps_json,
                updated_at = excluded.updated_at
            """,
            (
                record.id,
                record.name,
                record.description,
                record.worker_entrypoint,
                json.dumps(record.worker_files),
                json.dumps(record.requested_caps),
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ),
        )
        self._conn.commit()

    def list_worker_templates(self) -> list[WorkerTemplateRecord]:
        cursor = self._conn.execute("SELECT * FROM worker_templates ORDER BY updated_at DESC")
        return [self._row_to_worker_template(row) for row in cursor.fetchall()]

    def get_worker_template(self, template_id: str) -> WorkerTemplateRecord | None:
        cursor = self._conn.execute("SELECT * FROM worker_templates WHERE id = ?", (template_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_worker_template(row)

    def add_memory_entry(self, entry: MemoryEntry) -> None:
        self._conn.execute(
            """
            INSERT INTO memory_entries (id, role, content, embedding_json, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.role,
                entry.content,
                json.dumps(entry.embedding) if entry.embedding is not None else None,
                entry.created_at.isoformat(),
                json.dumps(entry.metadata),
            ),
        )
        self._conn.commit()

    def list_memory_entries(self, limit: int = 200) -> list[MemoryEntry]:
        cursor = self._conn.execute(
            "SELECT * FROM memory_entries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_memory(row) for row in cursor.fetchall()]

    def list_memory_entries_by_chat(self, chat_id: int, limit: int = 50) -> list[MemoryEntry]:
        needle = f"\"chat_id\": {chat_id}"
        cursor = self._conn.execute(
            "SELECT * FROM memory_entries WHERE metadata_json LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{needle}%", limit),
        )
        return [self._row_to_memory(row) for row in cursor.fetchall()]

    def is_chat_bootstrapped(self, chat_id: int) -> bool:
        cursor = self._conn.execute(
            "SELECT bootstrapped_at FROM chat_state WHERE chat_id = ?",
            (chat_id,),
        )
        row = cursor.fetchone()
        return bool(row and row["bootstrapped_at"])

    def mark_chat_bootstrapped(self, chat_id: int, ts: datetime) -> None:
        self._conn.execute(
            """
            INSERT INTO chat_state (chat_id, bootstrapped_at)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET bootstrapped_at = excluded.bootstrapped_at
            """,
            (chat_id, ts.isoformat()),
        )
        self._conn.commit()

    def _row_to_worker(self, row: sqlite3.Row) -> WorkerRecord:
        return WorkerRecord(
            id=row["id"],
            status=row["status"],
            task=row["task"],
            granted_caps=_loads_json(row["granted_caps_json"]),
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
        )

    def _row_to_intent(self, row: sqlite3.Row) -> IntentRecord:
        return IntentRecord(
            id=row["id"],
            worker_id=row["worker_id"],
            type=row["type"],
            payload=_loads_json(row["payload_json"]),
            payload_hash=row["payload_hash"],
            risk=row["risk"],
            requires_approval=bool(row["requires_approval"]),
            status=row["status"],
            created_at=_parse_dt(row["created_at"]),
        )

    def _row_to_permit(self, row: sqlite3.Row) -> PermitRecord:
        intent_type = row["intent_type"] if "intent_type" in row.keys() else ""
        return PermitRecord(
            id=row["id"],
            intent_id=row["intent_id"],
            intent_type=intent_type,
            worker_id=row["worker_id"],
            payload_hash=row["payload_hash"],
            expires_at=_parse_dt(row["expires_at"]),
            consumed_at=_parse_dt(row["consumed_at"]) if row["consumed_at"] else None,
            created_at=_parse_dt(row["created_at"]),
        )

    def _row_to_audit(self, row: sqlite3.Row) -> AuditEvent:
        return AuditEvent(
            id=row["id"],
            ts=_parse_dt(row["ts"]),
            correlation_id=row["correlation_id"],
            level=row["level"],
            event_type=row["event_type"],
            data=_loads_json(row["data_json"]),
        )

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryEntry:
        embedding = None
        if row["embedding_json"]:
            embedding = json.loads(row["embedding_json"])
        return MemoryEntry(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            embedding=embedding,
            created_at=_parse_dt(row["created_at"]),
            metadata=_loads_json(row["metadata_json"]),
        )

    def _row_to_worker_template(self, row: sqlite3.Row) -> WorkerTemplateRecord:
        return WorkerTemplateRecord(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            worker_entrypoint=row["worker_entrypoint"],
            worker_files=_loads_json(row["worker_files_json"]),
            requested_caps=_loads_json(row["requested_caps_json"]),
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _loads_json(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return json.loads(value)
