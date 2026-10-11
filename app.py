import io
import os
import re
from datetime import datetime

import pandas as pd
from flask import Flask, request, render_template_string, send_file

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB

# Avito Excel export columns. Column names are normalized to tolerate NBSPs.
ALIASES = {
    "Показы": ["Показы"],
    "Просмотры": ["Просмотры"],
    "Контакты": ["Контакты"],
    "Избранное": ["Добавили в избранное"],
    "Расходы": [
        "Расходы на размещение и целевые действия",
        "Расходы на объявления",
        "Расходы на продвижение",
        "Остальные расходы",
    ],
    "Средняя цена просмотра": ["Средняя цена просмотра"],
    "Средняя цена контакта": ["Средняя цена контакта"],
    "Цена": ["Цена"],
    "Город": ["Город"],
    "Регион": ["Регион размещения"],
    "Категория": ["Категория"],
    "Подкатегория": ["Подкатегория"],
    "Параметр": ["Параметр"],
    "Название объявления": ["Название объявления"],
    "Номер объявления": ["Номер объявления"],
    "Дней на Авито": ["Дней на Авито"],
    "Показы в просмотры": ["Конверсия из показов в просмотры"],
    "Просмотры в контакты": ["Конверсия из просмотров в контакты"],
}

def clean_col(value):
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()

def clean_frame(df):
    df = df.copy()
    df.columns = [clean_col(c) for c in df.columns]
    return df

def numeric(series):
    if series is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(
        series.astype(str).str.replace("\xa0", "", regex=False)
        .str.replace("₽", "", regex=False).str.replace("%", "", regex=False)
        .str.replace(",", ".", regex=False).str.strip(),
        errors="coerce"
    ).fillna(0)

def find_col(df, canonical):
    wanted = [clean_col(x) for x in ALIASES.get(canonical, [canonical])]
    for name in wanted:
        if name in df.columns:
            return name
    return None

def prepare_data(df):
    df = clean_frame(df)
    # The export may contain extra title/metadata rows; retain rows with a metric.
    metric_col = find_col(df, "Просмотры")
    if not metric_col:
        raise ValueError("Не найден столбец «Просмотры». Загрузите стандартную выгрузку статистики Avito в Excel.")
    df = df[df[metric_col].notna()].copy()
    if df.empty:
        raise ValueError("В файле не найдено строк со статистикой.")

    for canonical in ["Показы", "Просмотры", "Контакты", "Избранное",
                      "Средняя цена просмотра", "Средняя цена контакта",
                      "Дней на Авито", "Показы в просмотры", "Просмотры в контакты"]:
        col = find_col(df, canonical)
        df[canonical] = numeric(df[col]) if col else 0

    # Prefer total cost column. If unavailable, sum available cost components.
    total_cost_col = find_col(df, "Расходы")
    if total_cost_col:
        df["Расходы"] = numeric(df[total_cost_col])
    else:
        df["Расходы"] = 0
        for colname in ["Расходы на объявления", "Расходы на продвижение", "Остальные расходы"]:
            col = clean_col(colname)
            if col in df.columns:
                df["Расходы"] += numeric(df[col])

    for canonical in ["Город", "Регион", "Категория", "Подкатегория",
                      "Параметр", "Название объявления", "Номер объявления", "Цена"]:
        col = find_col(df, canonical)
        df[canonical] = df[col].fillna("").astype(str).str.strip() if col else ""

    # Derive rates from counts where possible; avoid trusting rounded source rates.
    df["Конверсия в просмотр, %"] = (df["Просмотры"] / df["Показы"].replace(0, pd.NA) * 100).fillna(0)
    df["Конверсия в контакт, %"] = (df["Контакты"] / df["Просмотры"].replace(0, pd.NA) * 100).fillna(0)
    df["Стоимость контакта, ₽"] = (df["Расходы"] / df["Контакты"].replace(0, pd.NA)).fillna(0)
    df["Стоимость просмотра, ₽"] = (df["Расходы"] / df["Просмотры"].replace(0, pd.NA)).fillna(0)
    df["Объект"] = df.apply(make_label, axis=1)
    return df

def make_label(row):
    for key in ["Название объявления", "Номер объявления"]:
        val = str(row.get(key, "")).strip()
        if val and val.lower() not in ["nan", "none"]:
            return val
    parts = [row.get("Город", ""), row.get("Категория", ""),
             row.get("Подкатегория", ""), row.get("Параметр", ""), row.get("Цена", "")]
    parts = [str(x).strip() for x in parts if str(x).strip() and str(x).lower() != "nan"]
    return " · ".join(parts) or "Строка без названия"

def rub(value):
    return f"{value:,.2f} ₽".replace(",", " ").replace(".", ",")

def integer(value):
    return f"{int(round(value)):,}".replace(",", " ")

def pct(value):
    return f"{value:.2f}%".replace(".", ",")

def aggregate(df, by):
    result = df.groupby(by, dropna=False, as_index=False).agg(
        Показы=("Показы", "sum"),
        Просмотры=("Просмотры", "sum"),
        Контакты=("Контакты", "sum"),
        Избранное=("Избранное", "sum"),
        Расходы=("Расходы", "sum"),
    )
    result["Конверсия в контакт, %"] = result["Контакты"] / result["Просмотры"].replace(0, pd.NA) * 100
    result["Стоимость контакта, ₽"] = result["Расходы"] / result["Контакты"].replace(0, pd.NA)
    return result.fillna(0)

PAGE = r"""
<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Avito Analytics — импорт статистики</title>
<style>
:root{--bg:#0b1120;--panel:#121b2d;--line:#28364d;--text:#edf2fa;--muted:#9babc2;--blue:#82aaff;--green:#52d6a5;--red:#ff8491;--yellow:#ffd078}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 Inter,Arial,sans-serif}
.wrap{max-width:1500px;margin:auto;padding:26px}.top{display:flex;justify-content:space-between;align-items:center;gap:15px;flex-wrap:wrap;margin-bottom:25px}
.brand{font-size:24px;font-weight:800}.brand span{color:var(--blue)}.muted{color:var(--muted)}h1{font-size:28px;margin:0 0 5px}h2{font-size:17px;margin:0 0 15px}
.pill{border:1px solid #6c5734;color:var(--yellow);background:#302719;padding:7px 11px;border-radius:8px;font-size:12px}
.panel,.metric{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;min-width:0}
.upload{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}.upload form{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
input[type=file]{max-width:100%;color:var(--muted)}button{background:#3568ce;color:white;border:0;border-radius:8px;padding:11px 16px;font-weight:700;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-top:15px}
.label{color:var(--muted);font-size:13px}.value{font-size:28px;font-weight:800;margin:10px 0 4px;letter-spacing:-.5px}
.small{font-size:12px}.good{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--yellow)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-top:15px}
.tablebox{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}th{text-align:left;font-size:11px;color:var(--muted);font-weight:600;padding:12px;border-bottom:1px solid var(--line)}td{padding:12px;border-bottom:1px solid var(--line)}tbody tr:last-child td{border:0}
.tag{font-size:11px;border-radius:5px;padding:4px 7px;background:#203c36;color:var(--green)}.tag.warn{background:#40351f;color:var(--yellow)}.tag.bad{background:#432630;color:var(--red)}
.rec{padding:12px 0;border-bottom:1px solid var(--line)}.rec:last-child{border:0}.rec strong{display:block;margin:7px 0 4px}
.error{background:#432630;color:#ffb5bd;border:1px solid #80404b;padding:12px;border-radius:8px;margin:14px 0}
footer{margin-top:22px;color:var(--muted);font-size:11px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cols{grid-template-columns:1fr}.wrap{padding:14px}}
@media(max-width:480px){.grid{gap:8px}.metric,.panel{padding:13px}.value{font-size:22px}}
</style></head><body><div class="wrap">
<header class="top"><div><div class="brand"><span>Avito</span> Analytics</div><div class="muted">Аналитика кабинета на основе выгрузки</div></div>
<div class="pill">● {{ "РЕАЛЬНАЯ ВЫГРУЗКА" if has_data else "ОЖИДАЕТ ФАЙЛ" }}</div></header>
<section class="panel upload"><div><h2>Загрузить статистику</h2><div class="muted small">Поддерживается Excel (.xlsx, .xls) до 20 МБ. Файл обрабатывается в памяти.</div></div>
<form method="post" action="/analyze" enctype="multipart/form-data"><input type="file" name="file" accept=".xlsx,.xls,.csv" required><button type="submit">Анализировать</button></form></section>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
{% if has_data %}
<section style="margin-top:22px"><h1>Обзор кабинета</h1><div class="muted">Строк: {{ row_count }} · Период берётся из исходной выгрузки, если указан в ней</div></section>
<section class="grid">
<div class="metric"><div class="label">Показы</div><div class="value">{{ kpis.shows }}</div><div class="muted small">Всего по загруженным строкам</div></div>
<div class="metric"><div class="label">Просмотры</div><div class="value">{{ kpis.views }}</div><div class="muted small">Конверсия из показов: {{ kpis.view_rate }}</div></div>
<div class="metric"><div class="label">Контакты</div><div class="value">{{ kpis.contacts }}</div><div class="muted small">Конверсия в контакт: {{ kpis.contact_rate }}</div></div>
<div class="metric"><div class="label">Расходы</div><div class="value">{{ kpis.spend }}</div><div class="muted small">Стоимость контакта: {{ kpis.cpa }}</div></div>
</section>
<section class="cols">
<div class="panel"><h2>Автоматические наблюдения</h2>
{% for rec in recommendations %}<div class="rec"><span class="tag {{ rec.kind }}">{{ rec.label }}</span><strong>{{ rec.title }}</strong><div class="muted">{{ rec.text }}</div></div>{% endfor %}
</div>
<div class="panel"><h2>Сводка по городам</h2><div class="tablebox"><table><thead><tr><th>Город</th><th>Просмотры</th><th>Контакты</th><th>₽/контакт</th></tr></thead><tbody>
{% for r in cities %}<tr><td>{{ r.name }}</td><td>{{ r.views }}</td><td>{{ r.contacts }}</td><td>{{ r.cpa }}</td></tr>{% endfor %}
</tbody></table></div></div>
</section>
<section class="panel" style="margin-top:15px"><div class="upload"><h2>Категории и параметры</h2><a href="/download" style="color:var(--blue)">Скачать результаты CSV</a></div><div class="tablebox"><table><thead><tr><th>Категория / параметр</th><th>Показы</th><th>Просмотры</th><th>Контакты</th><th>Конверсия</th><th>Расходы</th><th>₽/контакт</th></tr></thead><tbody>
{% for r in categories %}<tr><td>{{ r.name }}</td><td>{{ r.shows }}</td><td>{{ r.views }}</td><td>{{ r.contacts }}</td><td>{{ r.rate }}</td><td>{{ r.spend }}</td><td>{{ r.cpa }}</td></tr>{% endfor %}
</tbody></table></div></section>
<section class="panel" style="margin-top:15px"><h2>Строки выгрузки</h2><div class="muted small" style="margin-bottom:12px">Для оценки используются доступные поля. Если в файле нет ID или названия объявления, объект обозначается городом, категорией, параметром и ценой.</div>
<div class="tablebox"><table><thead><tr><th>Объект</th><th>Город</th><th>Показы</th><th>Просмотры</th><th>Контакты</th><th>Конверсия</th><th>Расходы</th><th>₽/контакт</th><th>Оценка</th></tr></thead><tbody>
{% for r in rows %}<tr><td>{{ r.name }}</td><td>{{ r.city }}</td><td>{{ r.shows }}</td><td>{{ r.views }}</td><td>{{ r.contacts }}</td><td>{{ r.rate }}</td><td>{{ r.spend }}</td><td>{{ r.cpa }}</td><td><span class="tag {{ r.kind }}">{{ r.status }}</span></td></tr>{% endfor %}
</tbody></table></div></section>
{% else %}
<section class="panel" style="margin-top:15px"><h2>Что появится после загрузки</h2><p class="muted">Сводные показатели, стоимость контакта, конверсия, сравнение городов и категорий, а также предварительные рекомендации на основе данных.</p><p class="muted small">Важно: если выгрузка содержит пересекающиеся срезы или агрегаты, их необходимо проверить перед использованием общих сумм.</p></section>
{% endif %}
<footer>Avito Analytics · MVP · Аналитические оценки предварительные и не заменяют проверку бизнес-контекста.</footer>
</div></body></html>
"""

LAST_EXPORT = None

def money(v):
    return f"{v:,.0f} ₽".replace(",", " ")

def safe_text(v):
    v = str(v).strip()
    return "" if v.lower() in ("nan", "none") else v

@app.get("/")
def home():
    return render_template_string(PAGE, has_data=False, error=None)

@app.post("/analyze")
def analyze():
    global LAST_EXPORT
    file = request.files.get("file")
    if not file or not file.filename:
        return render_template_string(PAGE, has_data=False, error="Выберите файл.")
    name = file.filename.lower()
    try:
        raw = file.read()
        if name.endswith(".csv"):
            try:
                source = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", encoding="utf-8-sig")
            except UnicodeDecodeError:
                source = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", encoding="cp1251")
        elif name.endswith((".xlsx", ".xls")):
            source = pd.read_excel(io.BytesIO(raw))
        else:
            raise ValueError("Поддерживаются файлы .xlsx, .xls и .csv.")
        df = prepare_data(source)
        LAST_EXPORT = df.copy()

        shows = df["Показы"].sum()
        views = df["Просмотры"].sum()
        contacts = df["Контакты"].sum()
        spend = df["Расходы"].sum()
        view_rate = views / shows * 100 if shows else 0
        contact_rate = contacts / views * 100 if views else 0
        cpa = spend / contacts if contacts else 0

        # City and category aggregations are summaries of rows in the export.
        # Warn in the UI that totals need a check if export contains overlapping cuts.
        city_col = df["Город"].replace("", "Не указан")
        city_df = df.assign(_city=city_col).groupby("_city", as_index=False).agg(
            Просмотры=("Просмотры", "sum"), Контакты=("Контакты", "sum"), Расходы=("Расходы", "sum"))
        city_df["cpa"] = city_df["Расходы"] / city_df["Контакты"].replace(0, pd.NA)
        city_df = city_df.fillna(0).sort_values(["Контакты", "Просмотры"], ascending=False).head(10)
        cities = [{"name":safe_text(r["_city"]), "views":integer(r["Просмотры"]),
                   "contacts":integer(r["Контакты"]), "cpa":money(r["cpa"]) if r["Контакты"] else "—"}
                  for _, r in city_df.iterrows()]

        group_cols = ["Категория", "Подкатегория", "Параметр"]
        cat_df = df.groupby(group_cols, dropna=False, as_index=False).agg(
            Показы=("Показы","sum"), Просмотры=("Просмотры","sum"),
            Контакты=("Контакты","sum"), Расходы=("Расходы","sum"))
        cat_df["rate"] = cat_df["Контакты"] / cat_df["Просмотры"].replace(0, pd.NA) * 100
        cat_df["cpa"] = cat_df["Расходы"] / cat_df["Контакты"].replace(0, pd.NA)
        cat_df = cat_df.fillna(0).sort_values(["Контакты","Просмотры"], ascending=False).head(20)
        categories = []
        for _, r in cat_df.iterrows():
            label = " · ".join([safe_text(r[c]) for c in group_cols if safe_text(r[c])])
            categories.append({"name":label or "Не указано","shows":integer(r["Показы"]),
                "views":integer(r["Просмотры"]),"contacts":integer(r["Контакты"]),
                "rate":f'{r["rate"]:.2f}%'.replace(".",","),
                "spend":money(r["Расходы"]),"cpa":money(r["cpa"]) if r["Контакты"] else "—"})

        # Build evidence-based preliminary labels. Avoid strong conclusions from tiny samples.
        avg_cpa = cpa
        rows = []
        row_actions = []
        for _, r in df.iterrows():
            obj_cpa = float(r["Стоимость контакта, ₽"])
            rv = float(r["Просмотры"])
            rc = float(r["Контакты"])
            rs = float(r["Расходы"])
            if rc == 0 and rs > 0 and rv >= 100:
                status, kind = "Проверить расходы", "bad"
                action = "check"
            elif rv < 100 or rc < 3:
                status, kind = "Недостаточно данных", "warn"
                action = "insufficient"
            elif avg_cpa > 0 and obj_cpa <= avg_cpa * 0.80 and rc >= 5:
                status, kind = "Потенциал усиления", ""
                action = "strengthen"
                row_actions.append((r, obj_cpa))
            elif avg_cpa > 0 and obj_cpa >= avg_cpa * 1.25 and rc >= 3:
                status, kind = "Оптимизировать", "warn"
                action = "optimize"
                row_actions.append((r, obj_cpa))
            else:
                status, kind = "Сопоставить с аналогами", "warn"
                action = "compare"
            rows.append({"name":safe_text(r["Объект"]), "city":safe_text(r["Город"]) or "—",
                "shows":integer(r["Показы"]),"views":integer(rv),
                "contacts":integer(rc),
                "rate":f'{r["Конверсия в контакт, %"]:.2f}%'.replace(".",","),
                "spend":money(rs),
                "cpa":money(obj_cpa) if rc else "—",
                "status":status,"kind":kind})

        recommendations = []
        if views:
            recommendations.append({"kind":"", "label":"СВОДКА",
                "title":f"Конверсия из просмотров в контакт — {contact_rate:.2f}%".replace(".",","),
                "text":"Это базовый ориентир по загруженным строкам. Сравнивайте только сопоставимые города, категории и периоды; средняя конверсия сама по себе не определяет успех."})

        # Compare categories with minimum sample size. Aggregates are used for guidance,
        # not as proof of profitability; orders/revenue are not present in this MVP logic.
        eligible_cats = cat_df[(cat_df["Просмотры"] >= 100) & (cat_df["Контакты"] >= 3)].copy()
        eligible_cats["cpa"] = eligible_cats["Расходы"] / eligible_cats["Контакты"].replace(0, pd.NA)
        eligible_cats = eligible_cats.dropna(subset=["cpa"])
        if not eligible_cats.empty:
            best = eligible_cats.sort_values(["cpa", "Контакты"], ascending=[True, False]).iloc[0]
            worst = eligible_cats.sort_values(["cpa", "Контакты"], ascending=[False, False]).iloc[0]
            best_name = " · ".join([safe_text(best[c]) for c in group_cols if safe_text(best[c])]) or "Категория без названия"
            worst_name = " · ".join([safe_text(worst[c]) for c in group_cols if safe_text(worst[c])]) or "Категория без названия"
            if best_name == worst_name:
                recommendations.append({"kind":"", "label":"СРАВНИТЬ",
                    "title":f"{best_name}: {int(best['Контакты'])} контактов",
                    "text":"Пока это единственная категория с достаточным объёмом данных для сравнения. Соберите ещё статистику, затем оцените динамику."})
            else:
                recommendations.append({"kind":"", "label":"ПОТЕНЦИАЛ УСИЛЕНИЯ",
                    "title":f"{best_name} — {money(float(best['cpa']))} за контакт",
                    "text":f"Категория дала {int(best['Контакты'])} контактов при {integer(best['Просмотры'])} просмотрах. Проверьте качество обращений и стабильность результата, прежде чем увеличивать бюджет."})
                if float(worst["cpa"]) >= float(best["cpa"]) * 1.25:
                    recommendations.append({"kind":"warn", "label":"ОПТИМИЗИРОВАТЬ",
                        "title":f"Сравнить затраты в категории «{worst_name}»",
                        "text":f"Стоимость контакта — {money(float(worst['cpa']))}, контактов — {int(worst['Контакты'])}. Проверьте цену, объявления и качество обращений; не сокращайте бюджет автоматически."})

        zero_contact = int(((df["Контакты"] == 0) & (df["Расходы"] > 0) & (df["Просмотры"] >= 100)).sum())
        if zero_contact:
            recommendations.append({"kind":"bad","label":"ПРОВЕРИТЬ",
                "title":f"{zero_contact} строк с расходами, от 100 просмотров и без контактов",
                "text":"Это приоритет для ручной проверки: оцените цену, фото, предложение и срок размещения. При этом не отключайте объект автоматически — выборка может быть недостаточной."})
        low_sample = int(((df["Просмотры"] < 100) | (df["Контакты"] < 3)).sum())
        if low_sample:
            recommendations.append({"kind":"warn","label":"НЕДОСТАТОЧНО ДАННЫХ",
                "title":f"{low_sample} строк требуют накопления статистики",
                "text":"Не делайте вывод об эффективности по нескольким просмотрам или 1–2 контактам. Сначала наберите достаточный объём наблюдений."})
        if not recommendations:
            recommendations.append({"kind":"warn","label":"НЕДОСТАТОЧНО ДАННЫХ",
                "title":"Пока недостаточно данных для рекомендаций",
                "text":"Проверьте, что выгрузка содержит просмотры, контакты и расходы."})
        # Keep the interface concise while preserving the most actionable observations.
        recommendations = recommendations[:5]

        kpis = {"shows":integer(shows),"views":integer(views),"contacts":integer(contacts),
                "spend":money(spend),"view_rate":f"{view_rate:.2f}%".replace(".",","),
                "contact_rate":f"{contact_rate:.2f}%".replace(".",","),
                "cpa":money(cpa) if contacts else "—"}
        return render_template_string(PAGE, has_data=True, error=None, kpis=kpis,
            row_count=len(df), recommendations=recommendations, cities=cities,
            categories=categories, rows=rows)
    except Exception as exc:
        return render_template_string(PAGE, has_data=False,
            error=f"Не удалось обработать файл: {str(exc)}"), 400

@app.get("/download")
def download():
    global LAST_EXPORT
    if LAST_EXPORT is None:
        return "Сначала загрузите и проанализируйте файл.", 400
    buf = io.StringIO()
    LAST_EXPORT.to_csv(buf, index=False, encoding="utf-8-sig")
    data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return send_file(data, mimetype="text/csv", as_attachment=True,
                     download_name="avito_analytics_results.csv")

@app.get("/health")
def health():
    return {"status":"ok","app":"Avito Analytics"}, 200

@app.get("/callback")
def callback():
    error = request.args.get("error")
    code = request.args.get("code")
    if error:
        return "<h1>Ошибка авторизации</h1><p>Avito вернул ошибку авторизации.</p>", 400
    if code:
        return "<h1>Avito Analytics</h1><p>Код авторизации получен. Обмен на токен ещё не реализован.</p>", 200
    return "<h1>Avito Analytics</h1><p>Callback работает. Код авторизации не передан.</p>", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
