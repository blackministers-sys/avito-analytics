import unittest

import pandas as pd

from app import clean_frame, find_col


class AvitoHeaderNormalizationTests(unittest.TestCase):
    def test_nonbreaking_spaces_do_not_hide_metric_columns(self):
        source = pd.DataFrame({
            "Расходы на\u00a0размещение и\u00a0целевые\u00a0действия": [123.45],
            "Средняя\u00a0цена контакта": [200.0],
            "Конверсия из\u00a0показов в\u00a0просмотры": [0.25],
        })
        normalized = clean_frame(source)
        self.assertEqual(find_col(normalized, "Расходы"), "Расходы на размещение и целевые действия")
        self.assertEqual(find_col(normalized, "Средняя цена контакта"), "Средняя цена контакта")
        self.assertEqual(find_col(normalized, "Показы в просмотры"), "Конверсия из показов в просмотры")


if __name__ == "__main__":
    unittest.main()
