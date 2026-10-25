"""SQLite-backed snapshots of Avito listing statistics.

The store is intentionally independent from Flask so it can be tested in isolation.
For production on Render, AVITO_ANALYTICS_DB should point to a persistent disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DB_PATH = os.environ.get("AVITO_ANALYTICS_DB", "instance/avito_analytics.sqlite3")


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    # Convert pandas/numpy scalar values without requiring pandas in this module.
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return None
        return value
    return str(value)


def _text(value: Any) -> str:
    value = _json_value(value)
    return "" if value is None else str(value).strip()


class HistoryStore:
    """Persist immutable upload snapshots and their normalized listing metrics."""

    def __init__(self, db_path: str | os.PathLike[str] = DEFAULT_DB_PATH):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account TEXT NOT NULL DEFAULT 'default',
                    captured_at TEXT NOT NULL,
                    source_filename TEXT NOT NULL DEFAULT '',
                    source_hash TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    UNIQUE(account, source_hash)
                );
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
                    row_number INTEGER NOT NULL,
                    listing_key TEXT NOT NULL,
                    ad_number TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    city TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    subcategory TEXT NOT NULL DEFAULT '',
                    parameter TEXT NOT NULL DEFAULT '',
                    price TEXT NOT NULL DEFAULT '',
                    shows REAL NOT NULL DEFAULT 0,
                    views REAL NOT NULL DEFAULT 0,
                    contacts REAL NOT NULL DEFAULT 0,
                    spend REAL NOT NULL DEFAULT 0,
                    favorites REAL NOT NULL DEFAULT 0,
                    UNIQUE(snapshot_id, row_number)
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_account_time
                    ON snapshots(account, captured_at);
                CREATE INDEX IF NOT EXISTS idx_observations_listing
                    ON observations(listing_key, snapshot_id);
            """)

    @staticmethod
    def fingerprint(source_bytes: bytes) -> str:
        return hashlib.sha256(source_bytes).hexdigest()

    def save_snapshot(
        self,
        rows: Iterable[dict[str, Any]],
        source_bytes: bytes,
        source_filename: str = "",
        account: str = "default",
        captured_at: str | None = None,
    ) -> dict[str, Any]:
        """Save one immutable upload. Exact same file/account is not stored twice."""
        account = _text(account) or "default"
        source_hash = self.fingerprint(source_bytes)
        timestamp = captured_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = list(rows)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, captured_at, row_count FROM snapshots WHERE account=? AND source_hash=?",
                (account, source_hash),
            ).fetchone()
            if existing:
                return {
                    "snapshot_id": existing["id"],
                    "created": False,
                    "captured_at": existing["captured_at"],
                    "row_count": existing["row_count"],
                    "source_hash": source_hash,
                }
            cursor = conn.execute(
                "INSERT INTO snapshots(account, captured_at, source_filename, source_hash, row_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (account, timestamp, _text(source_filename), source_hash, len(rows)),
            )
            snapshot_id = cursor.lastrowid
            values = []
            for index, row in enumerate(rows):
                ad_number = _text(row.get("Номер объявления"))
                title = _text(row.get("Название объявления"))
                city = _text(row.get("Город"))
                category = _text(row.get("Категория"))
                subcategory = _text(row.get("Подкатегория"))
                parameter = _text(row.get("Параметр"))
                price = _text(row.get("Цена"))
                # Prefer a stable Avito ad number. Fallback is descriptive, not guaranteed unique.
                listing_key = ad_number or "|".join((title, city, category, subcategory, parameter, price))
                if not listing_key.strip("|"):
                    listing_key = f"row:{index}"
                values.append((
                    snapshot_id, index, listing_key, ad_number, title, city, category,
                    subcategory, parameter, price,
                    float(_json_value(row.get("Показы")) or 0),
                    float(_json_value(row.get("Просмотры")) or 0),
                    float(_json_value(row.get("Контакты")) or 0),
                    float(_json_value(row.get("Расходы")) or 0),
                    float(_json_value(row.get("Избранное")) or 0),
                ))
            conn.executemany("""
                INSERT INTO observations(
                    snapshot_id, row_number, listing_key, ad_number, title, city, category,
                    subcategory, parameter, price, shows, views, contacts, spend, favorites
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, values)
        return {
            "snapshot_id": snapshot_id,
            "created": True,
            "captured_at": timestamp,
            "row_count": len(rows),
            "source_hash": source_hash,
        }

    def list_snapshots(self, account: str = "default", limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT id, account, captured_at, source_filename, row_count, source_hash
                FROM snapshots WHERE account=?
                ORDER BY captured_at DESC, id DESC LIMIT ?
            """, (_text(account) or "default", max(1, min(int(limit), 500)))).fetchall()
        return [dict(row) for row in rows]

    def get_snapshot(self, snapshot_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            snapshot = conn.execute(
                "SELECT * FROM snapshots WHERE id=?", (int(snapshot_id),)
            ).fetchone()
            if not snapshot:
                return None
            observations = conn.execute("""
                SELECT row_number, listing_key, ad_number, title, city, category,
                       subcategory, parameter, price, shows, views, contacts, spend, favorites
                FROM observations WHERE snapshot_id=? ORDER BY row_number
            """, (int(snapshot_id),)).fetchall()
        result = dict(snapshot)
        result["observations"] = [dict(row) for row in observations]
        return result

    def compare_latest(self, account: str = "default") -> dict[str, Any]:
        """Compare the two latest snapshots by stable listing key, without claiming causation."""
        snapshots = self.list_snapshots(account=account, limit=2)
        if len(snapshots) < 2:
            return {"available": False, "reason": "Для сравнения нужны минимум две разные выгрузки.", "changes": []}
        newer, older = snapshots[0], snapshots[1]
        new_data = self.get_snapshot(newer["id"])["observations"]
        old_data = self.get_snapshot(older["id"])["observations"]
        old_by_key: dict[str, dict[str, Any]] = {}
        for row in old_data:
            old_by_key[row["listing_key"]] = row
        changes = []
        for row in new_data:
            previous = old_by_key.get(row["listing_key"])
            if previous is None:
                changes.append({
                    "listing_key": row["listing_key"], "title": row["title"] or row["listing_key"],
                    "status": "new", "previous": None, "current": row,
                })
                continue
            metrics = {}
            for field in ("shows", "views", "contacts", "spend", "favorites"):
                before, after = float(previous[field]), float(row[field])
                metrics[field] = {"before": before, "after": after, "delta": after - before}
            changes.append({
                "listing_key": row["listing_key"], "title": row["title"] or row["listing_key"],
                "status": "existing", "previous": previous, "current": row, "metrics": metrics,
            })
        current_keys = {row["listing_key"] for row in new_data}
        for row in old_data:
            if row["listing_key"] not in current_keys:
                changes.append({
                    "listing_key": row["listing_key"], "title": row["title"] or row["listing_key"],
                    "status": "missing", "previous": row, "current": None,
                })
        return {
            "available": True,
            "older_snapshot_id": older["id"],
            "newer_snapshot_id": newer["id"],
            "older_captured_at": older["captured_at"],
            "newer_captured_at": newer["captured_at"],
            "changes": changes,
            "note": "Разница между выгрузками сама по себе не доказывает причинный эффект изменений.",
        }
