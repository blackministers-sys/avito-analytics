"""Read-only Avito Messenger synchronization with full conversation retention."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from .avito_client import AvitoClient
from .store import ChatStore


def _parse_bound(value, *, end=False):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value + (timedelta(days=1) if end else timedelta()), time.min, tzinfo=timezone.utc)
        return parsed
    else:
        raw = str(value).strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = date.fromisoformat(raw)
            except ValueError as exc:
                raise ValueError("Период должен быть датой YYYY-MM-DD или ISO datetime.") from exc
            return datetime.combine(
                parsed_date + (timedelta(days=1) if end else timedelta()),
                time.min,
                tzinfo=timezone.utc,
            )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _message_datetime(message):
    value = message.get("created") or message.get("created_at") or message.get("date")
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp /= 1000
        try:
            return datetime.fromtimestamp(stamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _in_period(message, start, end_exclusive):
    if start is None and end_exclusive is None:
        return True
    timestamp = _message_datetime(message)
    return bool(timestamp and (start is None or timestamp >= start)
                and (end_exclusive is None or timestamp < end_exclusive))


def sync_account(client=None, store=None, *, date_from=None, date_to=None):
    """Fetch all accessible chat histories and retain context for period analysis.

    The requested interval determines report counters, not which messages are
    persisted. Full accessible histories are retained so an in-range message
    can be analyzed with its surrounding conversation context.
    """
    start = _parse_bound(date_from)
    end_exclusive = _parse_bound(date_to, end=True)
    if start and end_exclusive and start >= end_exclusive:
        raise ValueError("Начало периода должно быть раньше окончания.")

    client = client or AvitoClient()
    store = store or ChatStore()
    account = client.account()
    user_id = account.get("id") or account.get("user_id")
    if user_id is None:
        raise RuntimeError("Avito не вернул ID аккаунта в /core/v1/accounts/self.")
    account_id = str(user_id)
    chats = client.list_chats(int(user_id))
    saved_messages = fetched_messages = in_period = unknown_timestamps = 0
    saved_chats = 0
    failed_chats = []

    for chat in chats:
        if store.save_chat(account_id, chat):
            saved_chats += 1
        chat_id = chat.get("id") or chat.get("chat_id")
        if chat_id is None:
            continue
        try:
            messages = client.list_messages(int(user_id), str(chat_id))
        except Exception as exc:
            failed_chats.append({"chat_id": str(chat_id), "error": str(exc)[:240]})
            continue
        for message in messages:
            fetched_messages += 1
            stamp = _message_datetime(message)
            if stamp is None:
                unknown_timestamps += 1
            elif _in_period(message, start, end_exclusive):
                in_period += 1
            if store.save_message(account_id, str(chat_id), message):
                saved_messages += 1

    status = "partial" if failed_chats else "ok"
    store.record_sync(account_id, len(chats), saved_messages, status)
    return {
        "account_id": account_id,
        "chats_received": len(chats),
        "chats_saved_or_updated": saved_chats,
        "messages_fetched": fetched_messages,
        "new_messages_saved": saved_messages,
        "messages_in_selected_period": in_period,
        "messages_with_unknown_timestamp": unknown_timestamps,
        "failed_chats_count": len(failed_chats),
        "failed_chats": failed_chats[:50],
        "period": {
            "from": start.isoformat() if start else None,
            "to_exclusive": end_exclusive.isoformat() if end_exclusive else None,
        },
        "status": store.status(account_id),
        "sync_status": status,
    }
