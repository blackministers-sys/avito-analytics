"""Conservative validation helpers for Avito Analytics exports.

This module reports risks; it deliberately does not delete rows or decide that
an export is safe to total based on a single heuristic.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd


SUMMARY_WORDS = (
    "итого", "всего", "общий итог", "total", "grand total",
    "сводка", "сумма по",
)
METRIC_NAMES = ("Показы", "Просмотры", "Контакты", "Расходы")


def normalize_column_name(value: Any) -> str:
    """Normalize spaces and non-breaking spaces in column names."""
    return " ".join(str(value).replace("\u00a0", " ").split()).strip()


def _cell_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().casefold()


def _parse_numeric(value: Any) -> tuple[float | None, bool]:
    """Return parsed value and whether a non-empty value failed parsing."""
    if pd.isna(value) or str(value).strip() == "":
        return None, False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), False
    text = str(value).replace("\u00a0", "").replace(" ", "")
    text = text.replace("₽", "").replace("%", "").replace(",", ".")
    try:
        return float(text), False
    except (TypeError, ValueError):
        return None, True


def validate_export(
    frame: pd.DataFrame,
    metric_columns: dict[str, str] | None = None,
    identity_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Return a UI-friendly validation report without modifying the input.

    metric_columns maps canonical metric names to actual DataFrame columns.
    identity_columns should contain fields identifying a unique observation
    (for example listing ID and reporting date) when known.
    """
    if frame is None or frame.empty:
        return {
            "status": "needs_review",
            "status_label": "Нужна проверка",
            "summary": "Файл пуст или не содержит строк данных.",
            "row_count": 0,
            "warnings": ["Нет строк для проверки."],
            "checks": [],
            "metrics": {},
        }

    df = frame.copy()
    df.columns = [normalize_column_name(c) for c in df.columns]
    metric_columns = metric_columns or {
        name: name for name in METRIC_NAMES if name in df.columns
    }
    identity_columns = [
        normalize_column_name(c) for c in (identity_columns or [])
        if normalize_column_name(c) in df.columns
    ]

    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    row_count = int(len(df))

    # Numeric parsing: missing/invalid values are reported separately from zero.
    invalid_total = 0
    missing_total = 0
    for canonical, actual in metric_columns.items():
        if actual not in df.columns:
            warnings.append(f"Не найден столбец метрики «{canonical}».")
            continue
        parsed = [_parse_numeric(v) for v in df[actual].tolist()]
        invalid = sum(1 for _, bad in parsed if bad)
        missing = sum(1 for v, bad in parsed if v is None and not bad)
        invalid_total += invalid
        missing_total += missing
        metrics[canonical] = {
            "invalid_values": int(invalid),
            "missing_values": int(missing),
            "valid_values": int(sum(v is not None and not bad for v, bad in parsed)),
        }
        if invalid:
            warnings.append(
                f"В столбце «{canonical}» не удалось распознать значений: {invalid}."
            )
        if missing:
            warnings.append(
                f"В столбце «{canonical}» пустых значений: {missing}; они не считаются нулями при проверке."
            )
    checks.append({
        "id": "numeric_values",
        "label": "Числовые значения",
        "status": "warning" if invalid_total or missing_total else "ok",
        "detail": f"Ошибочных значений: {invalid_total}; пустых: {missing_total}.",
    })

    # Exact duplicate detection is a warning only: duplicates may be legitimate.
    duplicate_count = int(df.duplicated(keep="first").sum())
    if duplicate_count:
        warnings.append(
            f"Найдены полностью повторяющиеся строки: {duplicate_count}. Они не удалены автоматически."
        )
    checks.append({
        "id": "exact_duplicates",
        "label": "Полные дубли строк",
        "status": "warning" if duplicate_count else "ok",
        "detail": f"Повторных вхождений: {duplicate_count}.",
    })

    # Possible total/summary rows. Check text fields only, never drop rows.
    text_columns = [
        c for c in df.columns
        if c not in set(metric_columns.values())
        and (pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]))
    ]
    summary_rows: list[int] = []
    for index, row in df.iterrows():
        texts = [_cell_text(row[c]) for c in text_columns]
        if any(any(word in text for word in SUMMARY_WORDS) for text in texts):
            summary_rows.append(int(index) + 1)
    if summary_rows:
        warnings.append(
            "Возможные строки итогов/сводки (номера строк в исходной таблице): "
            + ", ".join(map(str, summary_rows[:20]))
            + ("…" if len(summary_rows) > 20 else "")
            + ". Проверьте, не дублируют ли они строки детализации."
        )
    checks.append({
        "id": "summary_rows",
        "label": "Строки итогов",
        "status": "warning" if summary_rows else "ok",
        "detail": f"Возможных строк итогов: {len(summary_rows)}.",
    })

    # Identity collisions are only evaluated if caller supplies a known grain.
    identity_duplicate_count = None
    if identity_columns:
        identity_duplicate_count = int(df.duplicated(subset=identity_columns, keep="first").sum())
        if identity_duplicate_count:
            warnings.append(
                "Повторяются значения ключевых полей ("
                + ", ".join(identity_columns)
                + f"): {identity_duplicate_count}. Это могут быть дубли или разные срезы; нужна проверка."
            )
    checks.append({
        "id": "identity_key",
        "label": "Ключ наблюдения",
        "status": "warning" if identity_duplicate_count else ("ok" if identity_columns else "unknown"),
        "detail": (
            f"Повторяющихся ключей: {identity_duplicate_count}."
            if identity_columns
            else "Ключевые поля не заданы; уникальность наблюдений не подтверждена."
        ),
    })
    if not identity_columns:
        warnings.append(
            "Не задан ключ уникального наблюдения. По одной таблице нельзя подтвердить, что все строки независимы."
        )

    # A conservative status: the helper never certifies totals solely from heuristics.
    risky = duplicate_count > 0 or bool(summary_rows) or invalid_total > 0 or missing_total > 0
    if risky:
        status = "needs_review"
        status_label = "Нужна проверка"
        summary = "Обнаружены признаки, которые нужно проверить до расчёта общих итогов."
    elif not identity_columns:
        status = "breakdowns_only"
        status_label = "Итоги не подтверждены"
        summary = "Базовые проверки пройдены, но уникальность строк не подтверждена."
    elif identity_duplicate_count:
        status = "needs_review"
        status_label = "Нужна проверка"
        summary = "Повторяются ключи наблюдений; общие итоги могут быть завышены."
    else:
        status = "reviewed"
        status_label = "Базовые проверки пройдены"
        summary = "Явных проблем в базовых проверках не найдено. Это не доказывает отсутствие пересекающихся срезов."

    return {
        "status": status,
        "status_label": status_label,
        "summary": summary,
        "row_count": row_count,
        "warnings": warnings,
        "checks": checks,
        "metrics": metrics,
        "duplicate_rows": duplicate_count,
        "possible_summary_rows": len(summary_rows),
        "identity_columns": identity_columns,
        "identity_duplicate_rows": identity_duplicate_count,
    }
