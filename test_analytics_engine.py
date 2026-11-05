import pandas as pd

from analytics_engine import diagnose_ads, diagnose_categories


def sample(rows):
    return pd.DataFrame(rows, columns=["Город", "Категория", "Показы", "Просмотры", "Контакты", "Расходы"])


def test_ad_diagnosis_finds_post_view_bottleneck():
    rows = []
    for city in ["A", "B", "C", "D"]:
        rows.append([city, "Цепи", 1000, 200, 10, 1000])
    rows.append(["A", "Цепи", 1000, 200, 1, 1000])
    result = diagnose_ads(sample(rows))
    target = result[-1]
    assert target["stage"] == "Просмотры → контакты"
    assert "обращаются реже" in target["hypothesis"]


def test_ad_diagnosis_flags_weak_ctr_and_expensive_views():
    rows = []
    for city in ["A", "B", "C", "D"]:
        rows.append([city, "Цепи", 1000, 250, 10, 1000])
    rows.append(["A", "Цепи", 2000, 100, 5, 3000])
    target = diagnose_ads(sample(rows))[-1]
    assert "Показы → просмотры" in target["stage"]


def test_insufficient_sample_is_not_overdiagnosed():
    frame = sample([["A", "Цепи", 100, 20, 0, 50]])
    result = diagnose_ads(frame)[0]
    assert result["stage"] == "Недостаточно данных"


def test_category_diagnosis_returns_each_category():
    frame = sample([
        ["A", "Цепи", 1000, 200, 10, 1000],
        ["B", "Цепи", 1000, 200, 10, 1000],
        ["A", "Браслеты", 1000, 200, 2, 1000],
        ["B", "Браслеты", 1000, 200, 2, 1000],
    ])
    result = diagnose_categories(frame)
    assert {x["category"] for x in result} == {"Цепи", "Браслеты"}
    assert all("stage" in x and "hypothesis" in x and "test" in x for x in result)
