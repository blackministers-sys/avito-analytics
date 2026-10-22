"""Read Avito Excel exports while preserving visible text in HYPERLINK formulas."""
import io
import re

import pandas as pd
from openpyxl import load_workbook


_HYPERLINK_FORMULA = re.compile(
    r'^\s*=\s*HYPERLINK\s*\(\s*"(?:""|[^"])*"\s*[,;]\s*("(?:[^"]|"")*"|[^,;\)]+)',
    re.IGNORECASE,
)


def _visible_formula_text(value):
    """Return a literal display argument from an Excel HYPERLINK formula."""
    if not isinstance(value, str) or not value.lstrip().startswith("="):
        return value
    match = _HYPERLINK_FORMULA.match(value)
    if not match:
        return value
    display = match.group(1).strip()
    if len(display) >= 2 and display[0] == display[-1] == '"':
        return display[1:-1].replace('""', '"')
    # If the display argument is a cell reference or expression, don't guess.
    return value


def read_excel_preserving_hyperlinks(file_bytes):
    """Read the active worksheet into a DataFrame, extracting visible hyperlink labels.

    Excel formulas have no cached display value available through openpyxl in all files,
    so literal HYPERLINK display arguments are parsed directly. Other formulas are kept
    unchanged rather than silently converted to missing values.
    """
    workbook = load_workbook(io.BytesIO(file_bytes), data_only=False, read_only=False)
    try:
        worksheet = workbook.active
        rows = list(worksheet.iter_rows())
        if not rows:
            return pd.DataFrame()
        headers = []
        for cell in rows[0]:
            value = _visible_formula_text(cell.value)
            if value is None:
                value = ""
            headers.append(value)
        data = []
        for row in rows[1:]:
            values = []
            for cell in row:
                value = _visible_formula_text(cell.value)
                if value is None:
                    value = ""
                values.append(value)
            # Keep rows aligned with worksheet columns; pandas handles blank rows later.
            data.append(values)
        return pd.DataFrame(data, columns=headers)
    finally:
        workbook.close()
