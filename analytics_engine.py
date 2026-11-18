"""Evidence-based funnel diagnostics for Avito listing exports.

The engine identifies the stage where an ad/category underperforms comparable peers.
It emits hypotheses, not causal claims. All rates are recomputed from summed counts.
"""
from __future__ import annotations

import pandas as pd
from bisect import bisect_left


def _safe_ratio(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def _metrics(frame: pd.DataFrame) -> dict:
    shows = float(frame["Показы"].sum())
    views = float(frame["Просмотры"].sum())
    contacts = float(frame["Контакты"].sum())
    spend = float(frame["Расходы"].sum())
    revenue = float(frame["Выручка"].sum()) if "Выручка" in frame.columns else 0.0
    return {
        "ads": int(len(frame)),
        "shows": shows,
        "views": views,
        "contacts": contacts,
        "spend": spend,
        "revenue": revenue,
        "ctr": _safe_ratio(views, shows),
        "view_to_contact": _safe_ratio(contacts, views),
        "cost_per_view": _safe_ratio(spend, views),
        "cpl": _safe_ratio(spend, contacts),
    }


def _median(values):
    values = [float(x) for x in values if pd.notna(x) and float(x) > 0]
    return float(pd.Series(values).median()) if values else 0.0


def _stage_hypothesis(metrics: dict, baseline: dict | None, scope: str) -> dict:
    """Return the dominant observed bottleneck and a falsifiable next test."""
    if metrics["shows"] < 300 or metrics["views"] < 50:
        return {
            "stage": "Недостаточно данных",
            "hypothesis": "Пока нельзя надёжно определить этап просадки: слишком мало показов или просмотров.",
            "test": "Продолжить сбор статистики; не менять одновременно цену, фото и продвижение.",
            "confidence": "Низкая",
        }

    if not baseline:
        return {
            "stage": "Нужен ориентир",
            "hypothesis": "Нет достаточной сопоставимой группы, чтобы определить, какая конверсия действительно проседает.",
            "test": "Сравнить с объявлениями той же категории и города либо с предыдущим сопоставимым периодом.",
            "confidence": "Низкая",
        }

    ctr_low = baseline["ctr"] > 0 and metrics["ctr"] < baseline["ctr"] * 0.75
    post_view_low = (
        metrics["views"] >= 100
        and baseline["view_to_contact"] > 0
        and metrics["view_to_contact"] < baseline["view_to_contact"] * 0.75
    )
    expensive_view = (
        baseline["cost_per_view"] > 0
        and metrics["cost_per_view"] > baseline["cost_per_view"] * 1.25
    )

    if ctr_low and (post_view_low or expensive_view):
        stage = "Показы → просмотры (основная) + просмотры → контакты"
        hypothesis = (
            "Просадка начинается до открытия карточки: CTR ниже ориентира; "
            "после открытия конверсия также слабее либо просмотр обходится дороже."
        )
        test = "Сначала проверить первое фото, заголовок и цену в выдаче. Затем отдельно проверить предложение внутри карточки."
        confidence = "Средняя"
    elif ctr_low or expensive_view:
        stage = "Показы → просмотры"
        hypothesis = (
            "Узкое место вероятнее на этапе привлечения просмотра: "
            + ("CTR ниже сопоставимых объявлений. " if ctr_low else "")
            + ("Стоимость просмотра выше ориентира. " if expensive_view else "")
            + "Возможны слабая привлекательность карточки в выдаче или дорогой трафик."
        )
        test = "Сопоставить первое фото, заголовок, цену в выдаче и настройки продвижения; тестировать по одному изменению."
        confidence = "Средняя"
    elif post_view_low:
        stage = "Просмотры → контакты"
        hypothesis = (
            "Карточку открывают, но обращаются реже сопоставимых объявлений. "
            "Возможны неконкурентная цена, недостаток доверия, неполные характеристики "
            "или расхождение ожиданий с содержанием карточки."
        )
        test = "Проверить цену и условия относительно аналогов, описание, характеристики, гарантии и реальные причины отказов."
        confidence = "Средняя"
    else:
        stage = "Явная просадка не выявлена"
        hypothesis = "По доступным этапам нет выраженного отклонения от сопоставимой группы."
        test = "Проверить качество обращений и продажи; не считать контакт конечным бизнес-результатом."
        confidence = "Средняя"

    return {"stage": stage, "hypothesis": hypothesis, "test": test, "confidence": confidence, "scope": scope}


def diagnose_ads(frame: pd.DataFrame) -> list[dict]:
    """One diagnosis per listing; all row metrics are materialized once."""
    if frame.empty:
        return []

    product_group = "Параметр" if "Параметр" in frame.columns else "Категория"
    required = ["Показы", "Просмотры", "Контакты", "Расходы"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError("Missing diagnostic columns: " + ", ".join(missing))

    # Convert once to Python records. Repeated Series lookups inside a per-ad loop
    # were the dominant CPU cost for uploaded exports.
    records = frame.to_dict(orient="index")
    metric_frame = pd.DataFrame({
        "ctr": frame["Просмотры"].div(frame["Показы"].replace(0, pd.NA)).fillna(0),
        "view_to_contact": frame["Контакты"].div(frame["Просмотры"].replace(0, pd.NA)).fillna(0),
        "cost_per_view": frame["Расходы"].div(frame["Просмотры"].replace(0, pd.NA)).fillna(0),
        "eligible": (frame["Показы"] >= 300) & (frame["Просмотры"] >= 50),
    }, index=frame.index)
    metric_records = metric_frame.to_dict(orient="index")

    by_city_category: dict[tuple, list[int]] = {}
    by_category: dict[object, list[int]] = {}
    city_category_values: dict[tuple, dict[str, list[float]]] = {}
    category_values: dict[object, dict[str, list[float]]] = {}
    global_values = {key: [] for key in ("ctr", "view_to_contact", "cost_per_view")}

    for idx, row in records.items():
        m = metric_records[idx]
        if not bool(m["eligible"]):
            continue
        category = row.get(product_group, "")
        city = row.get("Город", "")
        by_city_category.setdefault((category, city), []).append(idx)
        by_category.setdefault(category, []).append(idx)
        city_bucket = city_category_values.setdefault(
            (category, city), {key: [] for key in global_values}
        )
        category_bucket = category_values.setdefault(
            category, {key: [] for key in global_values}
        )
        for key in global_values:
            value = float(m[key])
            if value > 0:
                city_bucket[key].append(value)
                category_bucket[key].append(value)
                global_values[key].append(value)

    for bucket in list(city_category_values.values()) + list(category_values.values()):
        for values in bucket.values():
            values.sort()
    for values in global_values.values():
        values.sort()

    def median_excluding(values, own_value, remove_own):
        remove_at = bisect_left(values, own_value) if remove_own and own_value > 0 else -1
        if remove_at >= len(values) or (remove_at >= 0 and values[remove_at] != own_value):
            remove_at = -1
        count = len(values) - int(remove_at >= 0)
        if count <= 0:
            return 0.0
        def at(position):
            return values[position if remove_at < 0 or position < remove_at else position + 1]
        middle = count // 2
        return float(at(middle)) if count % 2 else float((at(middle - 1) + at(middle)) / 2)

    results = []
    for idx, row in records.items():
        own = metric_records[idx]
        shows = float(row["Показы"])
        views = float(row["Просмотры"])
        contacts = float(row["Контакты"])
        spend = float(row["Расходы"])
        metrics = {
            "ads": 1, "shows": shows, "views": views, "contacts": contacts,
            "spend": spend, "ctr": float(own["ctr"]),
            "view_to_contact": float(own["view_to_contact"]),
            "cost_per_view": float(own["cost_per_view"]),
            "cpl": _safe_ratio(spend, contacts),
        }
        category, city = row.get(product_group, ""), row.get("Город", "")
        eligible_self = bool(own["eligible"])
        city_count = len(by_city_category.get((category, city), [])) - int(eligible_self)
        category_count = len(by_category.get(category, [])) - int(eligible_self)
        if city_count >= 3:
            scope = "город + категория"
            source = city_category_values[(category, city)]
        elif category_count >= 3:
            scope = "товарная категория, все города"
            source = category_values[category]
        else:
            scope = "вся выгрузка"
            source = global_values
        peer_count = city_count if scope == "город + категория" else (
            category_count if scope == "товарная категория, все города"
            else sum(bool(value) for value in metric_records.values()) - int(eligible_self)
        )
        baseline = None
        if peer_count >= 3:
            baseline = {
                key: median_excluding(source[key], float(own[key]), eligible_self)
                for key in global_values
            }
        result = _stage_hypothesis(metrics, baseline, scope)
        result.update({
            "index": idx, "baseline_ads": peer_count,
            "metrics": metrics, "baseline": baseline,
        })
        results.append(result)
    return results

def diagnose_categories(frame: pd.DataFrame) -> list[dict]:
    """Diagnose each category against the median of its city cohorts."""
    output = []
    group_column = "Параметр" if "Параметр" in frame.columns else "Категория"
    for category, group in frame.groupby(group_column, dropna=False):
        own = _metrics(group)
        city_metrics = []
        for _, city_group in group.groupby("Город", dropna=False):
            city = _metrics(city_group)
            if city["shows"] >= 300 and city["views"] >= 50:
                city_metrics.append(city)
        baseline = None
        if len(city_metrics) >= 2:
            baseline = {
                "ctr": _median(x["ctr"] for x in city_metrics),
                "view_to_contact": _median(x["view_to_contact"] for x in city_metrics),
                "cost_per_view": _median(x["cost_per_view"] for x in city_metrics),
            }
            diagnosis = _stage_hypothesis(own, baseline, "медиана городских когорт категории")
        elif own["shows"] < 300 or own["views"] < 50:
            diagnosis = _stage_hypothesis(own, None, "категория")
        else:
            diagnosis = {
                "stage": "Нужен ориентир",
                "hypothesis": "Категория рассчитана, но в ней недостаточно городских когорт для независимого сравнения.",
                "test": "Накопить данные минимум по нескольким городам или сравнить с предыдущим сопоставимым периодом.",
                "confidence": "Низкая",
            }
        diagnosis.update({"category": str(category), "metrics": own, "baseline": baseline,
                          "baseline_cities": len(city_metrics)})
        output.append(diagnosis)
    return output
