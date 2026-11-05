"""Persistent, idempotent storage for Avito chats and messages."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ChatStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("AVITO_ANALYTICS_DB", "instance/avito_analytics.sqlite3")
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS avito_chats (
                    account_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    item_id TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (account_id, chat_id)
                );
                CREATE TABLE IF NOT EXISTS avito_messages (
                    account_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (account_id, chat_id, message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_avito_messages_chat_time
                    ON avito_messages(account_id, chat_id, created_at);
                CREATE TABLE IF NOT EXISTS avito_sync_state (
                    account_id TEXT PRIMARY KEY,
                    last_sync_at TEXT NOT NULL,
                    chats_count INTEGER NOT NULL DEFAULT 0,
                    messages_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'ok'
                );
            """)

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    def save_chat(self, account_id: str, chat: dict) -> bool:
        chat_id = chat.get("id") or chat.get("chat_id")
        if chat_id is None:
            return False
        context = chat.get("context") if isinstance(chat.get("context"), dict) else {}
        item_id = chat.get("item_id") or context.get("value") or ""
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO avito_chats(account_id,chat_id,item_id,updated_at,payload_json)
                VALUES(?,?,?,?,?)
                ON CONFLICT(account_id,chat_id) DO UPDATE SET
                  item_id=excluded.item_id, updated_at=excluded.updated_at,
                  payload_json=excluded.payload_json
            """, (str(account_id), str(chat_id), str(item_id),
                  datetime.now(timezone.utc).isoformat(), self._json(chat)))
        return True

    def save_message(self, account_id: str, chat_id: str, message: dict) -> bool:
        message_id = message.get("id") or message.get("message_id")
        if message_id is None:
            return False
        created = message.get("created") or message.get("created_at") or message.get("date") or ""
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT OR IGNORE INTO avito_messages(account_id,chat_id,message_id,created_at,payload_json)
                VALUES(?,?,?,?,?)
            """, (str(account_id), str(chat_id), str(message_id), str(created), self._json(message)))
            return cur.rowcount == 1

    def record_sync(self, account_id: str, chats_count: int, messages_count: int, status: str = "ok"):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO avito_sync_state(account_id,last_sync_at,chats_count,messages_count,status)
                VALUES(?,?,?,?,?)
                ON CONFLICT(account_id) DO UPDATE SET
                  last_sync_at=excluded.last_sync_at,chats_count=excluded.chats_count,
                  messages_count=excluded.messages_count,status=excluded.status
            """, (str(account_id), datetime.now(timezone.utc).isoformat(),
                  chats_count, messages_count, status))

    def status(self, account_id: str) -> dict:
        with self._connect() as conn:
            chats = conn.execute("SELECT COUNT(*) FROM avito_chats WHERE account_id=?", (str(account_id),)).fetchone()[0]
            messages = conn.execute("SELECT COUNT(*) FROM avito_messages WHERE account_id=?", (str(account_id),)).fetchone()[0]
            state = conn.execute("SELECT * FROM avito_sync_state WHERE account_id=?", (str(account_id),)).fetchone()
        return {"chats": chats, "messages": messages, "last_sync_at": state["last_sync_at"] if state else None,
                "status": state["status"] if state else "not_synced"}

    def recent_chats(self, account_id: str, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT c.chat_id,c.item_id,c.updated_at,c.payload_json,
                       COUNT(m.message_id) AS messages_count,
                       MAX(m.created_at) AS last_message_at
                FROM avito_chats c LEFT JOIN avito_messages m
                  ON m.account_id=c.account_id AND m.chat_id=c.chat_id
                WHERE c.account_id=?
                GROUP BY c.account_id,c.chat_id
                ORDER BY last_message_at DESC, c.updated_at DESC LIMIT ?
            """, (str(account_id), max(1, min(int(limit), 500)))).fetchall()
        return [{"chat_id": r["chat_id"], "item_id": r["item_id"], "updated_at": r["updated_at"],
                 "messages_count": r["messages_count"], "last_message_at": r["last_message_at"],
                 "chat": json.loads(r["payload_json"])} for r in rows]


    def messages_for_period(self, account_id: str, date_from: str | None = None,
                            date_to_exclusive: str | None = None) -> list[dict]:
        """Return stored messages, optionally filtered by ISO timestamp bounds.

        Date filtering is performed in Python because source timestamps may be
        Unix seconds, milliseconds or ISO strings. Unknown timestamps are
        omitted when a period is requested.
        """
        from .sync_service import _message_datetime, _parse_bound

        start = _parse_bound(date_from) if date_from else None
        end = _parse_bound(date_to_exclusive) if date_to_exclusive else None
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chat_id, payload_json FROM avito_messages WHERE account_id=?",
                (str(account_id),),
            ).fetchall()
        result = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            if start is not None or end is not None:
                stamp = _message_datetime(payload)
                if stamp is None or (start is not None and stamp < start) or (end is not None and stamp >= end):
                    continue
            result.append({"chat_id": row["chat_id"], "message": payload})
        result.sort(key=lambda item: (
            _message_datetime(item["message"]) or datetime.min.replace(tzinfo=timezone.utc),
            str(item["message"].get("id") or ""),
        ))
        return result
