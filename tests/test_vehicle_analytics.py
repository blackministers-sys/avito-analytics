import pandas as pd

from vehicle_analytics import identify_vehicle, analyze_vehicle_groups


def test_lancer_generation_is_normalized():
    row = {"Название объявления": "Порог Mitsubishi Lancer 9", "Параметр": "", "Категория": "Запчасти"}
    assert identify_vehicle(row)[:3] == ("mitsubishi", "lancer", "IX")


def test_unknown_generation_is_not_guessed():
    row = {"Название объявления": "Арка Toyota Corolla", "Параметр": "", "Категория": "Запчасти"}
    assert identify_vehicle(row)[:3] == ("toyota", "corolla", "Не определено")


def test_structured_vehicle_fields_are_preferred():
    row = {"Марка": "Митсубиси", "Модель": "Лансер", "Поколение": "X",
           "Название объявления": "Порог Mitsubishi Lancer"}
    assert identify_vehicle(row)[:3] == ("mitsubishi", "lancer", "X")


def test_vehicle_aggregation_keeps_zero_contact_groups():
    frame = pd.DataFrame([
        {"Название объявления": "Порог Mitsubishi Lancer 9", "Показы": 1000, "Просмотры": 200, "Контакты": 5, "Расходы": 500},
        {"Название объявления": "Арка Mitsubishi Lancer 9", "Показы": 500, "Просмотры": 100, "Контакты": 0, "Расходы": 300},
        {"Название объявления": "Порог Toyota Corolla E150", "Показы": 700, "Просмотры": 120, "Контакты": 2, "Расходы": 250},
    ])
    result = analyze_vehicle_groups(frame)
    groups = {(g["make"], g["model"], g["generation"]): g for g in result["groups"]}
    lancer = groups[("mitsubishi", "lancer", "IX")]
    assert lancer["ads"] == 2
    assert lancer["contacts"] == 5
    assert lancer["no_contact_ads"] == 1
    assert result["coverage"]["identified"] == 3


def test_vehicle_analysis_accepts_missing_optional_columns():
    frame = pd.DataFrame([{"Название объявления": "Порог Mitsubishi Lancer 9", "Показы": 100, "Просмотры": 20, "Контакты": 1, "Расходы": 50}])
    result = analyze_vehicle_groups(frame)
    assert result["coverage"]["rows"] == 1
    assert result["coverage"]["identified"] == 1
    assert result["groups"][0]["contacts"] == 1


def test_identify_vehicle_accepts_series_with_missing_fields():
    row = pd.Series({"Название объявления": "Порог Mitsubishi Lancer 9"})
    assert identify_vehicle(row)[:3] == ("mitsubishi", "lancer", "IX")
