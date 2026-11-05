"""Build transparent period reports from stored Avito Messenger messages."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .sync_service import _message_datetime, _parse_bound
from .store import ChatStore
from .analyzer import classify_text


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, dict):
        for key in ("text", "message", "description"):
            value = content.get(key)
            if isinstance(value, str):
                return value.strip()
    value = message.get("text")
    return value.strip() if isinstance(value, str) else ""


def _sender(message: dict, account_user_id: str) -> str:
    # Browser imports may carry an explicit role inferred from the visible UI.
    # Accept only the closed vocabulary; never infer from wording or bubble order.
    role = message.get("sender_type")
    if role in {"customer", "seller", "unknown"}:
        return role
    # Official API messages use explicit author identifiers.
    author = message.get("author_id")
    if author is None:
        author = message.get("user_id")
    if author is None:
        return "unknown"
    return "seller" if str(author) == str(account_user_id) else "customer"


def build_period_report(
    account_id: str,
    date_from: str,
    date_to: str,
    *,
    store: ChatStore | None = None,
) -> dict[str, Any]:
    """Analyze period messages while retaining full stored conversation context."""
    start = _parse_bound(date_from)
    end_exclusive = _parse_bound(date_to, end=True)
    if start is None or end_exclusive is None or start >= end_exclusive:
        raise ValueError("Укажи корректный период: дата начала не позже даты окончания.")

    store = store or ChatStore()
    selected = store.messages_for_period(
        account_id, start.isoformat(), end_exclusive.isoformat()
    )
    grouped: dict[str, list[dict]] = defaultdict(list)
    topics: Counter[str] = Counter()
    inbound = outbound = unknown = 0

    for entry in selected:
        msg = entry["message"]
        text = _message_text(msg)
        if not text:
            continue
        sender = _sender(msg, account_id)
        stamp = _message_datetime(msg)
        grouped[entry["chat_id"]].append({
            "text": text,
            "sender": sender,
            "timestamp": stamp,
            "raw": msg,
        })
        if sender == "customer":
            inbound += 1
            topics.update(classify_text(text))
        elif sender == "seller":
            outbound += 1
        else:
            unknown += 1

    conversations = []
    response_samples = []
    awaiting_reply = 0
    for chat_id, messages in grouped.items():
        messages.sort(key=lambda item: item["timestamp"] or datetime.min.replace(tzinfo=timezone.utc))
        last = messages[-1]
        if last["sender"] == "customer":
            awaiting_reply += 1
        first_customer = next((i for i, item in enumerate(messages) if item["sender"] == "customer"), None)
        if first_customer is not None:
            first_seller = next((i for i in range(first_customer + 1, len(messages))
                                 if messages[i]["sender"] == "seller"), None)
            if first_seller is not None:
                t0, t1 = messages[first_customer]["timestamp"], messages[first_seller]["timestamp"]
                if t0 and t1 and t1 >= t0:
                    response_samples.append((t1 - t0).total_seconds() / 60)
        conversations.append({
            "chat_id": chat_id,
            "messages_in_period": len(messages),
            "customer_messages": sum(x["sender"] == "customer" for x in messages),
            "seller_messages": sum(x["sender"] == "seller" for x in messages),
            "unknown_sender_messages": sum(x["sender"] == "unknown" for x in messages),
            "last_message_at": last["timestamp"].isoformat() if last["timestamp"] else None,
            "last_sender": last["sender"],
            "last_message_preview": last["text"][:240],
            "topics": sorted({topic for x in messages if x["sender"] == "customer"
                              for topic in classify_text(x["text"])}),
        })

    conversations.sort(key=lambda item: item["last_message_at"] or "", reverse=True)
    return {
        "account_id": str(account_id),
        "period": {"from": date_from, "to": date_to},
        "summary": {
            "conversations_with_messages": len(conversations),
            "messages_in_period": sum(x["messages_in_period"] for x in conversations),
            "customer_messages": inbound,
            "seller_messages": outbound,
            "unknown_sender_messages": unknown,
            "conversations_awaiting_seller_reply": awaiting_reply,
            "average_first_response_minutes": (
                round(sum(response_samples) / len(response_samples), 1) if response_samples else None
            ),
            "response_time_sample_size": len(response_samples),
            "topics": dict(topics.most_common()),
            "topic_classification_note": "Темы — текстовые сигналы, не подтверждённые причины отказа или потери продажи.",
        },
        "conversations": conversations,
        "limitations": [
            "В отчёт включены сообщения с распознанным временем внутри выбранного периода.",
            "Неизвестный автор не угадывается и учитывается отдельно.",
            "Отсутствие ответа или тишина не считаются доказанной потерей продажи.",
            "Результат зависит от полноты доступной истории источника.",
        ],
    }
