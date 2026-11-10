import unittest

import pandas as pd

from app import prepare_data


class MarketingMetricsTests(unittest.TestCase):
    def test_ctr_cr_and_ddr_use_raw_counts_and_delivered_revenue(self):
        source = pd.DataFrame([{
            "Показы": 1000,
            "Просмотры": 100,
            "Контакты": 10,
            "Расходы на объявления": 2000,
            "Стоимость доставленных товаров": 5000,
            "Стоимость заказанных товаров": 6000,
            "Город": "Москва",
            "Категория": "Браслеты",
        }])
        result = prepare_data(source).iloc[0]
        self.assertAlmostEqual(result["CTR, %"], 10.0)
        self.assertAlmostEqual(result["CR, %"], 10.0)
        self.assertAlmostEqual(result["Выручка"], 5000.0)
        self.assertAlmostEqual(result["ДРР, %"], 40.0)
        self.assertAlmostEqual(result["ДРР по заказанным товарам, %"], 2000 / 6000 * 100)

    def test_ddr_is_zero_when_export_has_no_delivered_revenue(self):
        source = pd.DataFrame([{
            "Показы": 100,
            "Просмотры": 10,
            "Контакты": 2,
            "Расходы на объявления": 300,
            "Город": "Москва",
            "Категория": "Браслеты",
        }])
        result = prepare_data(source).iloc[0]
        self.assertEqual(result["Выручка"], 0)
        self.assertEqual(result["ДРР, %"], 0)

    def test_nbsp_revenue_headers_are_normalized(self):
        source = pd.DataFrame([{
            "Показы": 200,
            "Просмотры": 20,
            "Контакты": 4,
            "Расходы на\u00a0объявления": 100,
            "Стоимость доставленных товаров": 1000,
        }])
        result = prepare_data(source).iloc[0]
        self.assertAlmostEqual(result["ДРР, %"], 10.0)


if __name__ == "__main__":
    unittest.main()
