"""Source-independent normalization for Avito chat messages.

The analytics layer consumes this schema only. Source adapters must provide
explicit field mappings; unknown sender roles and timestamps remain unknown.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


SCHEMA_VERSION = "1.0"


class MessageNormalizationError(ValueError):
    """Raised when a source record cannot be mapped to a stable message."""


def _path(value: Any, dotted_path: str | None) -> Any:
    if not dotted_path:
        return None
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _iso_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # Avito adapters must explicitly identify seconds vs milliseconds
        # before calling this function; ambiguous numeric values are rejected.
        raise MessageNormalizationError("Числовой timestamp требует явного преобразования источником.")
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc).isoformat()
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_message(
    raw: dict[str, Any],
    *,
    account_id: str,
    conversation_id: str,
    source_type: str,
    field_map: dict[str, str],
) -> dict[str, Any]:
    """Normalize one source record using explicit dotted-path mappings.

    Required field_map keys: message_id, text. Optional: timestamp, sender,
    attachments. Sender mapping is explicit: customer/buyer -> customer,
    seller/manager -> seller; every other value remains unknown.
    """
    if not isinstance(raw, dict):
        raise MessageNormalizationError("Сообщение должно быть объектом.")
    if not str(account_id).strip() or not str(conversation_id).strip():
        raise MessageNormalizationError("Не заданы внутренний ID аккаунта или ID диалога.")
    message_id = _path(raw, field_map.get("message_id"))
    text = _path(raw, field_map.get("text"))
    if message_id is None or not str(message_id).strip():
        raise MessageNormalizationError("Не найден ID сообщения.")
    if text is None:
        raise MessageNormalizationError("Не найден текст сообщения.")
    sender_raw = _path(raw, field_map.get("sender"))
    sender_value = str(sender_raw or "").strip().lower()
    if sender_value in {"customer", "buyer", "client", "покупатель", "клиент"}:
        sender = "customer"
    elif sender_value in {"seller", "manager", "продавец", "менеджер"}:
        sender = "seller"
    else:
        sender = "unknown"

    timestamp_raw = _path(raw, field_map.get("timestamp"))
    attachments_raw = _path(raw, field_map.get("attachments"))
    attachments = []
    if isinstance(attachments_raw, list):
        for item in attachments_raw:
            if isinstance(item, dict):
                attachments.append({
                    "type": str(item.get("type") or item.get("kind") or "unknown"),
                    "name": str(item.get("name") or "")[:255],
                    "source_id": str(item.get("id") or "")[:128],
                })
            else:
                attachments.append({"type": "unknown", "name": "", "source_id": ""})

    return {
        "schema_version": SCHEMA_VERSION,
        "account_id": str(account_id).strip(),
        "conversation_id": str(conversation_id).strip(),
        "message_id": str(message_id).strip(),
        "timestamp": _iso_timestamp(timestamp_raw),
        "sender_type": sender,
        "text": str(text).strip(),
        "attachments": attachments,
        "source": {
            "type": str(source_type).strip(),
            "record_hash": sha256(repr(sorted(raw.items())).encode("utf-8")).hexdigest(),
        },
    }
