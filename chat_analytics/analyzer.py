"""Transparent, rule-based analytics for manually uploaded chat exports.

The module intentionally does not connect to Avito and does not persist messages.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd


REASON_RULES = {
    "Цена / дорого": [
        r"дорог", r"дороже", r"дешевле", r"скид", r"торг", r"бюджет",
        r"не потян", r"цена не", r"по цене",
    ],
    "Нет товара / не подходит наличие": [
        r"нет в налич", r"законч", r"уже продан", r"не осталось",
        r"нет такого", r"не подойд[её]т", r"не тот размер", r"не та модель",
    ],
    "Доставка / получение": [
        r"достав", r"отправ", r"самовывоз", r"транспортн", r"сдэк",
        r"почт", r"курьер", r"сроки получения",
    ],
    "Недоверие / безопасность сделки": [
        r"предоплат", r"безопасн", r"гарант", r"обман", r"мошенн",
        r"отзыв", r"наложенн", r"оплат[аи] при получении",
    ],
    "Условия / характеристики": [
        r"характерист", r"размер", r"вес", r"материал", r"комплект",
        r"совместим", r"подойд", r"состояни", r"фото", r"видео",
    ],
    "Нашёл другого продавца": [
        r"уже купил", r"наш[её]л", r"нашел у друг", r"заказал в другом",
        r"купил в другом", r"у конкур",
    ],
    "Сроки / неактуально": [
        r"уже не актуаль", r"передумал", r"пока не нуж", r"позже",
        r"не сейчас", r"отлож",
    ],
}

POSITIVE_PATTERNS = [
    r"оформ", r"беру", r"покуп", r"оплат", r"заказал", r"закажу",
    r"куда перевод", r"отправляйте", r"заберу",
]
REFUSAL_PATTERNS = [
    r"не буду", r"отказ", r"не интересно", r"не актуально",
    r"не подходит", r"дорого", r"купил у друг",
]
CUSTOMER_ROLE_HINTS = ("покупатель", "клиент", "buyer", "customer")
SELLER_ROLE_HINTS = ("продавец", "менеджер", "seller", "manager")


def _clean(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def classify_text(text: str) -> list[str]:
    """Return matched topics; this is a signal, not a confirmed loss reason."""
    value = (text or "").lower().replace("ё", "е")
    found = []
    for label, patterns in REASON_RULES.items():
        if any(re.search(pattern, value) for pattern in patterns):
            found.append(label)
    return found


def _matches(text: str, patterns: list[str]) -> bool:
    value = (text or "").lower().replace("ё", "е")
    return any(re.search(pattern, value) for pattern in patterns)


def normalize_messages(
    frame: pd.DataFrame,
    mapping: dict[str, str],
) -> pd.DataFrame:
    """Map arbitrary export columns to a stable message schema."""
    required = ("conversation_id", "text")
    missing = [key for key in required if not mapping.get(key)]
    if missing:
        raise ValueError("Не выбраны обязательные поля: " + ", ".join(missing))

    out = pd.DataFrame()
    for key, source in mapping.items():
        if source and source in frame.columns:
            out[key] = frame[source].map(_clean)
    if "conversation_id" not in out or "text" not in out:
        raise ValueError("Не удалось прочитать ID диалога и текст сообщения.")
    out["conversation_id"] = out["conversation_id"].astype(str).str.strip()
    out = out[(out["conversation_id"] != "") & (out["text"] != "")]
    if "timestamp" in out:
        out["timestamp_parsed"] = pd.to_datetime(out["timestamp"], errors="coerce", dayfirst=True)
        out = out.sort_values(["conversation_id", "timestamp_parsed"], na_position="last")
    return out.reset_index(drop=True)


def _role_is_customer(role: str) -> bool | None:
    value = (role or "").lower()
    if any(hint in value for hint in CUSTOMER_ROLE_HINTS):
        return True
    if any(hint in value for hint in SELLER_ROLE_HINTS):
        return False
    return None


def analyze_conversations(messages: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Summarize each conversation without treating silence as a confirmed refusal."""
    rows = []
    all_topics: Counter[str] = Counter()

    for conversation_id, group in messages.groupby("conversation_id", sort=False):
        texts = group["text"].tolist()
        joined = " ".join(texts)
        roles = group["sender"].tolist() if "sender" in group else []
        customer_texts = []
        seller_texts = []
        if roles:
            for role, text in zip(roles, texts):
                is_customer = _role_is_customer(role)
                if is_customer is True:
                    customer_texts.append(text)
                elif is_customer is False:
                    seller_texts.append(text)
        if not customer_texts:
            # If role labels are absent/unknown, analyze the full dialogue but
            # explicitly mark role attribution as unavailable.
            customer_texts = texts

        topics = sorted({topic for text in customer_texts for topic in classify_text(text)})
        all_topics.update(topics)
        positive = any(_matches(text, POSITIVE_PATTERNS) for text in customer_texts)
        refusal = any(_matches(text, REFUSAL_PATTERNS) for text in customer_texts)
        last_text = texts[-1] if texts else ""
        last_role = roles[-1] if roles else ""
        last_is_customer = _role_is_customer(last_role) if last_role else None

        if positive:
            status = "Есть сигнал намерения купить"
        elif refusal:
            status = "Есть явный сигнал отказа"
        elif last_is_customer is True:
            status = "Последнее сообщение клиента — нужен ответ/проверка"
        elif last_is_customer is False:
            status = "Последнее сообщение продавца — исход неизвестен"
        else:
            status = "Исход не определён"

        timestamps = group["timestamp_parsed"].dropna() if "timestamp_parsed" in group else []
        first_response_minutes = None
        if len(timestamps) >= 2 and roles:
            ordered = group.reset_index(drop=True)
            first_customer_idx = next(
                (i for i, role in enumerate(ordered["sender"]) if _role_is_customer(role) is True),
                None,
            )
            if first_customer_idx is not None:
                response_idx = next(
                    (i for i in range(first_customer_idx + 1, len(ordered))
                     if _role_is_customer(ordered.loc[i, "sender"]) is False),
                    None,
                )
                if response_idx is not None:
                    t0 = ordered.loc[first_customer_idx, "timestamp_parsed"]
                    t1 = ordered.loc[response_idx, "timestamp_parsed"]
                    if pd.notna(t0) and pd.notna(t1):
                        first_response_minutes = max(0.0, (t1 - t0).total_seconds() / 60)

        row = {
            "conversation_id": conversation_id,
            "messages": len(group),
            "ad_title": group["ad_title"].iloc[0] if "ad_title" in group else "",
            "ad_id": group["ad_id"].iloc[0] if "ad_id" in group else "",
            "topics": ", ".join(topics) if topics else "Не выявлены",
            "status_signal": status,
            "first_response_minutes": first_response_minutes,
            "last_message": last_text[:240],
            "role_attribution": "Определена" if roles and any(_role_is_customer(r) is not None for r in roles) else "Не определена",
        }
        rows.append(row)

    result = pd.DataFrame(rows)
    summary = {
        "conversations": len(result),
        "messages": len(messages),
        "topics": dict(all_topics.most_common()),
        "role_attributed": int((result["role_attribution"] == "Определена").sum()) if not result.empty else 0,
        "response_time_sample": int(result["first_response_minutes"].notna().sum()) if not result.empty else 0,
    }
    return result, summary
