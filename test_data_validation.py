import unittest

import pandas as pd

from data_validation import validate_export


class ValidateExportTests(unittest.TestCase):
    def test_empty_frame_needs_review(self):
        report = validate_export(pd.DataFrame())
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["row_count"], 0)

    def test_missing_key_does_not_certify_totals(self):
        frame = pd.DataFrame({
            "Показы": [100, 200],
            "Просмотры": [20, 40],
            "Контакты": [2, 4],
            "Расходы": [100, 200],
        })
        report = validate_export(frame)
        self.assertEqual(report["status"], "breakdowns_only")
        self.assertIn("уникальность строк не подтверждена", report["summary"])

    def test_exact_duplicates_are_reported_not_deleted(self):
        frame = pd.DataFrame({
            "ID": [10, 10],
            "Показы": [100, 100],
            "Просмотры": [20, 20],
            "Контакты": [2, 2],
            "Расходы": [100, 100],
        })
        report = validate_export(
            frame,
            metric_columns={name: name for name in ["Показы", "Просмотры", "Контакты", "Расходы"]},
            identity_columns=["ID"],
        )
        self.assertEqual(report["duplicate_rows"], 1)
        self.assertEqual(len(frame), 2)
        self.assertEqual(report["status"], "needs_review")

    def test_summary_rows_are_flagged(self):
        frame = pd.DataFrame({
            "Название": ["Объявление A", "Итого по кабинету"],
            "Показы": [100, 100],
            "Просмотры": [20, 20],
            "Контакты": [2, 2],
            "Расходы": [100, 100],
        })
        report = validate_export(
            frame,
            metric_columns={name: name for name in ["Показы", "Просмотры", "Контакты", "Расходы"]},
            identity_columns=["Название"],
        )
        self.assertEqual(report["possible_summary_rows"], 1)
        self.assertEqual(report["status"], "needs_review")

    def test_invalid_numeric_is_not_treated_as_zero(self):
        frame = pd.DataFrame({
            "ID": [1, 2],
            "Показы": ["100", "не число"],
            "Просмотры": [20, 10],
            "Контакты": [2, 1],
            "Расходы": [100, 50],
        })
        report = validate_export(
            frame,
            metric_columns={name: name for name in ["Показы", "Просмотры", "Контакты", "Расходы"]},
            identity_columns=["ID"],
        )
        self.assertEqual(report["metrics"]["Показы"]["invalid_values"], 1)
        self.assertEqual(report["status"], "needs_review")


if __name__ == "__main__":
    unittest.main()
