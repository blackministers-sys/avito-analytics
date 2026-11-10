"""Evidence-based funnel diagnostics for Avito listing exports.

The engine identifies the stage where an ad/category underperforms comparable peers.
It emits hypotheses, not causal claims. All rates are recomputed from summed counts.
"""
from __future__ import annotations

import pandas as pd


def _safe_ratio(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def _metrics(frame: pd.DataFrame) -> dict:
    shows = float(frame["Показы"].sum())
    views = float(frame["Просмотры"].sum())
    contacts = float(frame["Контакты"].sum())
    spend = float(frame["Расходы"].sum())
    return {
        "ads": int(len(frame)),
        "shows": shows,
        "views": views,
        "contacts": contacts,
        "spend": spend,
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
    """One diagnosis per listing; peer metrics are precomputed once (linear grouping)."""
    if frame.empty:
        return []

    product_group = "Параметр" if "Параметр" in frame.columns else "Категория"
    metric_frame = pd.DataFrame(index=frame.index)
    metric_frame["ctr"] = frame["Просмотры"].div(frame["Показы"].replace(0, pd.NA)).fillna(0)
    metric_frame["view_to_contact"] = frame["Контакты"].div(frame["Просмотры"].replace(0, pd.NA)).fillna(0)
    metric_frame["cost_per_view"] = frame["Расходы"].div(frame["Просмотры"].replace(0, pd.NA)).fillna(0)
    metric_frame["eligible"] = (frame["Показы"] >= 300) & (frame["Просмотры"] >= 50)

    # Store row-level peer metrics in grouped lists once. This avoids repeatedly
    # filtering/copying the full DataFrame for every listing (the former O(n²) path).
    eligible = metric_frame[metric_frame["eligible"]]
    by_city_category = {}
    by_category = {}
    all_peer_values = {
        key: eligible[key].tolist()
        for key in ("ctr", "view_to_contact", "cost_per_view")
    }
    for idx, row in frame.loc[eligible.index].iterrows():
        category = row.get(product_group, "")
        city = row.get("Город", "")
        key = (category, city)
        by_city_category.setdefault(key, []).append(idx)
        by_category.setdefault(category, []).append(idx)

    results = []
    for idx, row in frame.iterrows():
        own_values = metric_frame.loc[idx]
        metrics = {
            "ads": 1,
            "shows": float(row["Показы"]),
            "views": float(row["Просмотры"]),
            "contacts": float(row["Контакты"]),
            "spend": float(row["Расходы"]),
            "ctr": float(own_values["ctr"]),
            "view_to_contact": float(own_values["view_to_contact"]),
            "cost_per_view": float(own_values["cost_per_view"]),
            "cpl": _safe_ratio(float(row["Расходы"]), float(row["Контакты"])),
        }

        category = row.get(product_group, "")
        city = row.get("Город", "")
        peers = by_city_category.get((category, city), [])
        scope = "город + категория"
        if idx in peers:
            peers = [peer for peer in peers if peer != idx]
        if len(peers) < 3:
            peers = [peer for peer in by_category.get(category, []) if peer != idx]
            scope = "товарная категория, все города"
        if len(peers) < 3:
            peers = [peer for peer in eligible.index if peer != idx]
            scope = "вся выгрузка"

        baseline = None
        if len(peers) >= 3:
            baseline = {
                key: _median(metric_frame.loc[peers, key].tolist())
                for key in ("ctr", "view_to_contact", "cost_per_view")
            }
        result = _stage_hypothesis(metrics, baseline, scope)
        result.update({
            "index": idx,
            "baseline_ads": len(peers),
            "metrics": metrics,
            "baseline": baseline,
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
