import unittest
from io import BytesIO

from openpyxl import Workbook

from excel_import import read_excel_preserving_hyperlinks


class ExcelHyperlinkImportTests(unittest.TestCase):
    def test_reads_visible_text_from_hyperlink_formula(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Номер объявления", "Название объявления"])
        sheet["A2"] = '=HYPERLINK("https://www.avito.ru/item_8102416562","8102416562")'
        sheet["B2"] = '=HYPERLINK("https://www.avito.ru/item_8102416562","Серебряная цепь")'
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()

        result = read_excel_preserving_hyperlinks(buffer.getvalue())
        self.assertEqual(result.loc[0, "Номер объявления"], "8102416562")
        self.assertEqual(result.loc[0, "Название объявления"], "Серебряная цепь")

    def test_keeps_ordinary_cell_values(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Номер объявления", "Показы"])
        sheet.append(["8102416562", 7298])
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()

        result = read_excel_preserving_hyperlinks(buffer.getvalue())
        self.assertEqual(result.loc[0, "Номер объявления"], "8102416562")
        self.assertEqual(result.loc[0, "Показы"], 7298)


if __name__ == "__main__":
    unittest.main()
