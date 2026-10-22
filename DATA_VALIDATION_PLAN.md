# Avito Analytics: data validation plan

## Goal

Prevent misleading totals and recommendations when an uploaded Avito export contains overlapping aggregation levels, duplicate records, missing metrics, or malformed values.

## Safety rule

Do not change the production branch `main` directly. Work on `audit/data-validation`; deploy only after review and testing.

## Current risks found in `app.py`

1. The app sums every row for account-level KPIs without determining whether rows represent unique listings, daily records, categories, or summary totals.
2. City/category tables aggregate the same rows independently. That is useful as a breakdown, but does not prove the rows are mutually exclusive.
3. `numeric()` converts unparseable values to zero, which can hide missing or malformed data.
4. `LAST_EXPORT` is process memory, so downloaded results can disappear after a restart or when requests reach another worker.
5. Recommendations compare per-row cost/contact with an account-wide average even when row types or periods may not be comparable.

## Proposed validation workflow

1. Identify the file type, sheet, headers, and likely report period.
2. Normalize column names and parse numeric fields while tracking invalid/missing values separately from real zeros.
3. Infer row grain from available columns (listing ID, date, city, category, summary labels).
4. Detect exact duplicate rows and likely aggregate/summary rows; do not silently delete uncertain matches.
5. Classify the export as:
   - **Safe to total** — row grain is sufficiently clear and rows appear mutually exclusive.
   - **Breakdowns only** — dimensions can be compared, but account-wide totals may double-count.
   - **Needs review** — required metrics or row structure are ambiguous.
6. Show a validation report before presenting account-level totals.
7. Only generate recommendations from comparable records and display sample size, period, and confidence limitations.

## Tests required before deployment

- Standard export with unique listing rows.
- Export with a grand-total row plus detail rows.
- Repeated rows.
- Missing/invalid numeric cells.
- Zero impressions/views/contacts.
- Multiple sheets and CSV encoding/separator variations.
- City/category breakdowns that overlap with listing-level rows.

## Non-goals for this first change

- No automatic editing of Avito listings or photos.
- No claims that we know Avito's ranking algorithm.
- No changes to the production branch or Render deployment.
- No automatic deletion of rows based only on a heuristic.

## Next implementation step

Build a validation layer that reports detected structure and warnings without changing the existing KPI calculations until tests establish safe behavior. Then integrate it behind an explicit validation result and review with real exports.
