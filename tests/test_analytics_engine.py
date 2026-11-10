import unittest

import pandas as pd

from analytics_engine import diagnose_ads, diagnose_categories


class DiagnoseAdsTests(unittest.TestCase):
    def make_frame(self):
        return pd.DataFrame([
            {"Параметр": "Арки", "Город": "Москва", "Показы": 1000, "Просмотры": 200, "Контакты": 20, "Расходы": 2000},
            {"Параметр": "Арки", "Город": "Москва", "Показы": 1000, "Просмотры": 180, "Контакты": 18, "Расходы": 1800},
            {"Параметр": "Арки", "Город": "Москва", "Показы": 1000, "Просмотры": 160, "Контакты": 16, "Расходы": 1600},
            {"Параметр": "Арки", "Город": "Москва", "Показы": 1000, "Просмотры": 80, "Контакты": 2, "Расходы": 400},
            {"Параметр": "Пороги", "Город": "СПб", "Показы": 900, "Просмотры": 150, "Контакты": 15, "Расходы": 1500},
        ])

    def test_returns_one_diagnosis_per_listing(self):
        frame = self.make_frame()
        result = diagnose_ads(frame)
        self.assertEqual(len(result), len(frame))
        self.assertEqual([item["index"] for item in result], list(frame.index))

    def test_same_city_category_peers_are_used(self):
        result = diagnose_ads(self.make_frame())
        self.assertEqual(result[0]["baseline_ads"], 3)
        self.assertEqual(result[0]["scope"], "город + категория")

    def test_falls_back_to_category_then_all_export(self):
        frame = self.make_frame()
        frame.loc[4, "Параметр"] = "Арки"
        frame.loc[4, "Город"] = "СПб"
        result = diagnose_ads(frame)
        self.assertEqual(result[4]["scope"], "товарная категория, все города")
        self.assertEqual(result[4]["baseline_ads"], 4)

    def test_empty_frame_is_supported(self):
        self.assertEqual(diagnose_ads(self.make_frame().iloc[0:0]), [])

    def test_category_diagnostics_still_work(self):
        result = diagnose_categories(self.make_frame())
        self.assertTrue(result)
        self.assertEqual(result[0]["category"], "Арки")


if __name__ == "__main__":
    unittest.main()
