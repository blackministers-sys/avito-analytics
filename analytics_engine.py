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
    """One diagnosis per listing row; peer baseline is same city/category when possible."""
    results = []
    eligible = frame[(frame["Показы"] >= 300) & (frame["Просмотры"] >= 50)].copy()
    for idx, row in frame.iterrows():
        own = _metrics(frame.loc[[idx]])
        peers = eligible[
            (eligible["Категория"] == row.get("Категория", ""))
            & (eligible["Город"] == row.get("Город", ""))
            & (eligible.index != idx)
        ]
        scope = "город + категория"
        if len(peers) < 3:
            peers = eligible[
                (eligible["Категория"] == row.get("Категория", ""))
                & (eligible.index != idx)
            ]
            scope = "категория, все города"
        if len(peers) < 3:
            peers = eligible[eligible.index != idx]
            scope = "вся выгрузка"
        baseline = None
        if len(peers) >= 3:
            baseline = {
                "ctr": _median((_metrics(peers.loc[[i]])["ctr"] for i in peers.index)),
                "view_to_contact": _median((_metrics(peers.loc[[i]])["view_to_contact"] for i in peers.index)),
                "cost_per_view": _median((_metrics(peers.loc[[i]])["cost_per_view"] for i in peers.index)),
            }
        result = _stage_hypothesis(own, baseline, scope)
        result.update({"index": idx, "baseline_ads": len(peers), "metrics": own, "baseline": baseline})
        results.append(result)
    return results


def diagnose_categories(frame: pd.DataFrame) -> list[dict]:
    """Diagnose each category against the median of its city cohorts."""
    output = []
    for category, group in frame.groupby("Категория", dropna=False):
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
