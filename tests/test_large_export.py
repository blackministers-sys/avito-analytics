import io
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import app as analytics_app
from history_store import HistoryStore


class LargeExportRouteTests(unittest.TestCase):
    def test_632_row_xlsx_upload_completes(self):
        rows = []
        for i in range(632):
            rows.append({
                "Номер объявления": str(8100000000 + i),
                "Город": "Москва" if i % 3 else "Санкт-Петербург",
                "Категория": "Запчасти",
                "Подкатегория": "Кузовные детали",
                "Параметр": "Арки" if i % 2 == 0 else "Пороги",
                "Название объявления": f"Тестовое объявление {i}",
                "Цена": "10 000 ₽",
                "Показы": 1200 + i,
                "Просмотры": 140 + (i % 50),
                "Контакты": 8 + (i % 7),
                "Расходы на объявления": 900 + (i * 3),
                "Стоимость доставленных товаров": 0,
                "Стоимость заказанных товаров": 0,
                "Добавили в избранное": i % 10,
                "Дней на Авито": 30,
            })
        source = pd.DataFrame(rows)
        payload = io.BytesIO()
        source.to_excel(payload, index=False, engine="openpyxl")
        payload.seek(0)

        with tempfile.TemporaryDirectory() as directory:
            store_path = f"{directory}/history.sqlite3"
            with patch.object(
                analytics_app, "HistoryStore",
                lambda: HistoryStore(store_path),
            ):
                client = analytics_app.app.test_client()
                response = client.post(
                    "/analyze",
                    data={"file": (payload, "avito_632_rows.xlsx")},
                    content_type="multipart/form-data",
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Обзор кабинета".encode("utf-8"), response.data)
        self.assertNotIn("Internal Server Error".encode("utf-8"), response.data)


if __name__ == "__main__":
    unittest.main()
