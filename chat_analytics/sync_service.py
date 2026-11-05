"""Read-only Avito Messenger synchronization with optional date filtering."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from .avito_client import AvitoClient
from .store import ChatStore


def _parse_bound(value: str | date | datetime | None, *, end: bool = False) -> datetime | None:
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
            parsed = datetime.combine(
                parsed_date + (timedelta(days=1) if end else timedelta()),
                time.min,
                tzinfo=timezone.utc,
            )
            return parsed
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed


def _message_datetime(message: dict) -> datetime | None:
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


def _in_period(message: dict, start: datetime | None, end_exclusive: datetime | None) -> bool:
    if start is None and end_exclusive is None:
        return True
    timestamp = _message_datetime(message)
    if timestamp is None:
        return False
    return (start is None or timestamp >= start) and (end_exclusive is None or timestamp < end_exclusive)


def sync_account(
    client: AvitoClient | None = None,
    store: ChatStore | None = None,
    *,
    date_from: str | date | datetime | None = None,
    date_to: str | date | datetime | None = None,
) -> dict:
    """Fetch accessible chats and persist messages in the requested inclusive date range.

    Chat discovery and history reads are read-only. Messages without a parseable
    timestamp are excluded when a date filter is active rather than guessed.
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
    saved_messages = 0
    fetched_messages = 0
    skipped_outside_period = 0
    skipped_unknown_timestamp = 0
    saved_chats = 0

    for chat in chats:
        if store.save_chat(account_id, chat):
            saved_chats += 1
        chat_id = chat.get("id") or chat.get("chat_id")
        if chat_id is None:
            continue
        for message in client.list_messages(int(user_id), str(chat_id)):
            fetched_messages += 1
            if start is not None or end_exclusive is not None:
                timestamp = _message_datetime(message)
                if timestamp is None:
                    skipped_unknown_timestamp += 1
                    continue
                if not _in_period(message, start, end_exclusive):
                    skipped_outside_period += 1
                    continue
            if store.save_message(account_id, str(chat_id), message):
                saved_messages += 1

    store.record_sync(account_id, len(chats), saved_messages, "ok")
    return {
        "account_id": account_id,
        "chats_received": len(chats),
        "chats_saved_or_updated": saved_chats,
        "messages_fetched": fetched_messages,
        "new_messages_saved": saved_messages,
        "messages_skipped_outside_period": skipped_outside_period,
        "messages_skipped_unknown_timestamp": skipped_unknown_timestamp,
        "period": {
            "from": start.isoformat() if start else None,
            "to_exclusive": end_exclusive.isoformat() if end_exclusive else None,
        },
        "status": store.status(account_id),
    }
