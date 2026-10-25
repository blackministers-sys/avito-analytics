import tempfile
import unittest
from pathlib import Path

from history_store import HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp_dir.name) / "history.sqlite3")
        self.store = HistoryStore(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def row(self, views=20, contacts=2, spend=100, title="Цепь Панцирь", ad_number="123"):
        return {
            "Номер объявления": ad_number,
            "Название объявления": title,
            "Город": "Санкт-Петербург",
            "Категория": "Украшения",
            "Подкатегория": "Цепи",
            "Параметр": "Панцирь",
            "Цена": "5000",
            "Показы": 100,
            "Просмотры": views,
            "Контакты": contacts,
            "Расходы": spend,
            "Избранное": 4,
        }

    def test_save_and_read_snapshot(self):
        result = self.store.save_snapshot([self.row()], b"export-v1", "day1.xlsx", captured_at="2026-10-25T10:00:00+00:00")
        self.assertTrue(result["created"])
        loaded = self.store.get_snapshot(result["snapshot_id"])
        self.assertEqual(loaded["row_count"], 1)
        self.assertEqual(loaded["observations"][0]["views"], 20)


    def test_reporting_period_is_saved_and_listed(self):
        saved = self.store.save_snapshot(
            [self.row()], b"period-export", "week.xlsx",
            report_start="2026-10-19", report_end="2026-10-25"
        )
        loaded = self.store.get_snapshot(saved["snapshot_id"])
        self.assertEqual(loaded["report_start"], "2026-10-19")
        self.assertEqual(loaded["report_end"], "2026-10-25")
        listed = self.store.list_snapshots()[0]
        self.assertEqual(listed["report_start"], "2026-10-19")
        self.assertEqual(listed["report_end"], "2026-10-25")

    def test_same_account_and_file_is_not_duplicated(self):
        first = self.store.save_snapshot([self.row()], b"same-export", "a.xlsx")
        second = self.store.save_snapshot([self.row()], b"same-export", "a.xlsx")
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(len(self.store.list_snapshots()), 1)

    def test_same_file_can_be_saved_for_different_accounts(self):
        self.store.save_snapshot([self.row()], b"export", account="jewelry")
        self.store.save_snapshot([self.row()], b"export", account="auto")
        self.assertEqual(len(self.store.list_snapshots("jewelry")), 1)
        self.assertEqual(len(self.store.list_snapshots("auto")), 1)

    def test_compare_two_snapshots_by_ad_number(self):
        self.store.save_snapshot(
            [self.row(views=20, contacts=2, spend=100)],
            b"older", captured_at="2026-10-24T10:00:00+00:00"
        )
        self.store.save_snapshot(
            [self.row(views=35, contacts=4, spend=150)],
            b"newer", captured_at="2026-10-25T10:00:00+00:00"
        )
        result = self.store.compare_latest()
        self.assertTrue(result["available"])
        change = result["changes"][0]
        self.assertEqual(change["metrics"]["views"]["delta"], 15)
        self.assertEqual(change["metrics"]["contacts"]["delta"], 2)
        self.assertEqual(change["metrics"]["spend"]["delta"], 50)

    def test_compare_without_two_snapshots_explains_limitation(self):
        self.store.save_snapshot([self.row()], b"only-one")
        result = self.store.compare_latest()
        self.assertFalse(result["available"])
        self.assertEqual(result["changes"], [])

    def test_rows_without_ad_number_use_descriptive_key(self):
        self.store.save_snapshot([self.row(ad_number="")], b"no-id")
        loaded = self.store.get_snapshot(1)
        self.assertIn("Цепь Панцирь", loaded["observations"][0]["listing_key"])


if __name__ == "__main__":
    unittest.main()
