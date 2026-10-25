import io
import os
import re
from datetime import datetime

import pandas as pd
from data_validation import validate_export
from history_store import HistoryStore
from excel_import import read_excel_preserving_hyperlinks
from flask import Flask, request, render_template_string, send_file, redirect

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB

# Avito Excel export columns. Column names are normalized to tolerate NBSPs.
ALIASES = {
    "Показы": ["Показы"],
    "Просмотры": ["Просмотры"],
    "Контакты": ["Контакты"],
    "Избранное": ["Добавили в избранное"],
    "Расходы": [
        "Расходы на объявления",
        "Расходы на размещение и целевые действия",
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
.tablebox{overflow-x:auto;max-width:100%}#citySummaryTable{table-layout:fixed;width:100%;white-space:normal;font-size:12px}#citySummaryTable th,#citySummaryTable td{padding:9px 6px;white-space:normal;overflow-wrap:anywhere;word-break:normal;vertical-align:top}#citySummaryTable th:nth-child(1),#citySummaryTable td:nth-child(1){width:19%}#citySummaryTable th:nth-child(2),#citySummaryTable td:nth-child(2){width:12%}#citySummaryTable th:nth-child(3),#citySummaryTable td:nth-child(3){width:10%}#citySummaryTable th:nth-child(4),#citySummaryTable td:nth-child(4){width:12%}#citySummaryTable th:nth-child(5),#citySummaryTable td:nth-child(5){width:13%}#citySummaryTable th:nth-child(6),#citySummaryTable td:nth-child(6){width:12%}#citySummaryTable th:nth-child(7),#citySummaryTable td:nth-child(7){width:22%;line-height:1.35}.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end}.filters label{display:flex;flex-direction:column;gap:5px;color:var(--muted);font-size:12px}.filters select{background:#0b1120;color:var(--text);border:1px solid var(--line);border-radius:7px;padding:10px;min-width:145px}.filters button.secondary{background:#29364b}table{width:100%;border-collapse:collapse;white-space:nowrap}th{text-align:left;font-size:11px;color:var(--muted);font-weight:600;padding:12px;border-bottom:1px solid var(--line)}td{padding:12px;border-bottom:1px solid var(--line)}tbody tr:last-child td{border:0}#recommendationsTable{table-layout:fixed;width:100%;white-space:normal;font-size:12px}#recommendationsTable th,#recommendationsTable td{padding:8px 6px;white-space:normal;overflow-wrap:anywhere;word-break:normal;vertical-align:top}#recommendationsTable th:nth-child(1),#recommendationsTable td:nth-child(1){width:20%}#recommendationsTable th:nth-child(2),#recommendationsTable td:nth-child(2){width:9%}#recommendationsTable th:nth-child(3),#recommendationsTable td:nth-child(3),#recommendationsTable th:nth-child(4),#recommendationsTable td:nth-child(4),#recommendationsTable th:nth-child(5),#recommendationsTable td:nth-child(5),#recommendationsTable th:nth-child(6),#recommendationsTable td:nth-child(6),#recommendationsTable th:nth-child(7),#recommendationsTable td:nth-child(7),#recommendationsTable th:nth-child(8),#recommendationsTable td:nth-child(8){width:5%}#recommendationsTable th:nth-child(9),#recommendationsTable td:nth-child(9){width:7%}#recommendationsTable th:nth-child(10),#recommendationsTable td:nth-child(10){width:11%}#recommendationsTable th:nth-child(11),#recommendationsTable td:nth-child(11){width:13%}#recommendationsTable td:last-child details{min-width:0;max-width:100%}#recommendationsTable td:last-child summary{white-space:normal;overflow-wrap:anywhere;cursor:pointer;color:var(--blue)}#recommendationsTable td:last-child details div{white-space:normal;overflow-wrap:anywhere;word-break:normal;padding-top:6px;max-width:100%}@media(max-width:1100px){ #recommendationsTable{font-size:11px}#recommendationsTable th,#recommendationsTable td{padding:6px 4px}#recommendationsTable th:nth-child(1),#recommendationsTable td:nth-child(1){width:20%}#recommendationsTable th:nth-child(2),#recommendationsTable td:nth-child(2){width:9%}#recommendationsTable th:nth-child(9),#recommendationsTable td:nth-child(9){width:8%}#recommendationsTable th:nth-child(10),#recommendationsTable td:nth-child(10){width:12%}#recommendationsTable th:nth-child(11),#recommendationsTable td:nth-child(11){width:15%}}
.tag{font-size:11px;border-radius:5px;padding:4px 7px;background:#203c36;color:var(--green)}.tag.warn{background:#40351f;color:var(--yellow)}.tag.bad{background:#432630;color:var(--red)}
.rec{padding:12px 0;border-bottom:1px solid var(--line)}.rec:last-child{border:0}.rec strong{display:block;margin:7px 0 4px}
.error{background:#432630;color:#ffb5bd;border:1px solid #80404b;padding:12px;border-radius:8px;margin:14px 0}
footer{margin-top:22px;color:var(--muted);font-size:11px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cols{grid-template-columns:1fr}.wrap{padding:14px}}
@media(max-width:480px){.grid{gap:8px}.metric,.panel{padding:13px}.value{font-size:22px}}
</style></head><body><div class="wrap">
<header class="top"><div><div class="brand"><span>Avito</span> Analytics</div><div class="muted">Аналитика кабинета на основе выгрузки</div></div>
<div class="pill">● {{ "РЕАЛЬНАЯ ВЫГРУЗКА" if has_data else "ОЖИДАЕТ ФАЙЛ" }}</div></header>
<section class="panel upload"><div><h2>Загрузить статистику</h2><div class="muted small">Поддерживается Excel (.xlsx, .xls) до 20 МБ. Файл обрабатывается в памяти.</div><div style="margin-top:12px"><a href="/history" style="display:inline-block;background:#203c36;color:#7ee0b2;border:1px solid #35685a;border-radius:8px;padding:9px 12px;text-decoration:none;font-weight:700">История статистики →</a></div></div>
<form method="post" action="/analyze" enctype="multipart/form-data"><input type="file" name="file" accept=".xlsx,.xls,.csv" required><label class="muted small">Период отчёта с <input type="date" name="report_start" aria-label="Начало периода отчёта"></label><label class="muted small">по <input type="date" name="report_end" aria-label="Конец периода отчёта"></label><button type="submit">Анализировать</button></form></section>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
{% if has_data %}
<section style="margin-top:22px"><h1>Обзор кабинета</h1><div class="muted">Строк: {{ row_count }} · Период отчёта — метка выгрузки; он не фильтрует данные внутри файла</div></section>
{% if history_result is defined %}
<section class="panel" style="margin-top:12px;border-color:#35685a">
<h2>Результат сохранения истории</h2>
<p>Файл: {{ history_result.source_filename }} · Снимок №{{ history_result.snapshot_id }}</p>
<p>{% if history_result.created %}Создана новая запись истории.{% else %}Этот файл уже был в истории; проверено и обновлено заполнение периода.{% endif %}</p>
<p>Период отчёта: {% if history_result.report_start or history_result.report_end %}{{ history_result.report_start or "не указан" }} — {{ history_result.report_end or "не указан" }}{% else %}не указан{% endif %}</p>
<p><a href="/history">Открыть историю статистики →</a></p>
</section>
{% endif %}
{% if validation_report %}
<section class="panel" style="margin-top:15px;border-color:{{ '#80404b' if validation_report.status == 'needs_review' else '#6c5734' }}">
<h2>Проверка качества данных: {{ validation_report.status_label }}</h2>
<p class="muted">{{ validation_report.summary }}</p>
<div class="muted small">Проверено строк: {{ validation_report.row_count }} · Полные дубли: {{ validation_report.duplicate_rows }} · Возможные строки итогов: {{ validation_report.possible_summary_rows }}</div>
{% if validation_report.warnings %}
<ul>{% for warning in validation_report.warnings %}<li style="margin:6px 0">{{ warning }}</li>{% endfor %}</ul>
{% else %}<p class="good small">Базовые проверки не выявили явных проблем. Это не гарантирует отсутствие пересекающихся срезов.</p>{% endif %}
</section>
{% endif %}
<section class="grid">
<div class="metric"><div class="label">Показы</div><div class="value">{{ kpis.shows }}</div><div class="muted small">Всего по загруженным строкам</div></div>
<div class="metric"><div class="label">Просмотры</div><div class="value">{{ kpis.views }}</div><div class="muted small">Конверсия из показов: {{ kpis.view_rate }}</div></div>
<div class="metric"><div class="label">Контакты</div><div class="value">{{ kpis.contacts }}</div><div class="muted small">Конверсия в контакт: {{ kpis.contact_rate }}</div></div>
<div class="metric"><div class="label">Расходы</div><div class="value">{{ kpis.spend }}</div><div class="muted small">Стоимость контакта: {{ kpis.cpa }}</div></div>
</section>
<section class="panel" style="margin-top:15px">
<h2>Маркетинговая воронка</h2>
<p class="muted small">Показы → просмотры → контакты. Просадка определяется по конверсии и объёму данных; без сопоставимого прошлого периода или внешнего ориентира это предварительная диагностика, а не доказательство причины.</p>
<div class="grid">
{% for step in funnel %}
<div class="metric">
<div class="label">{{ step.name }}</div>
<div class="value">{{ step.rate }}</div>
<div class="muted small">{{ step.input }} → {{ step.output }}</div>
<div style="margin-top:10px"><span class="tag {{ step.kind }}">{{ step.status }}</span></div>
<strong style="display:block;margin-top:10px">{{ step.action_title }}</strong>
<div class="muted small" style="margin-top:5px">{{ step.action_text }}</div>
</div>
{% endfor %}
</div>
</section>
<section class="cols">
<div class="panel"><h2>Автоматические наблюдения</h2>
<div id="recommendationScopeNotice" class="muted small" hidden>Включены фильтры. Наблюдения ниже рассчитаны по всей выгрузке, поэтому скрыты, чтобы не смешивать выборки.</div>
<div id="recommendationsList">
{% for rec in recommendations %}<div class="rec"><span class="tag {{ rec.kind }}">{{ rec.label }}</span><strong>{{ rec.title }}</strong><div class="muted">{{ rec.text }}</div></div>{% endfor %}
</div></div>
<div class="panel"><h2>Сводка по городам</h2><p class="muted small">Стоимость контакта считается как общие расходы города / общие контакты. Города отсортированы по количеству контактов; малые выборки оценивайте осторожно.</p><div class="tablebox"><table id="citySummaryTable"><thead><tr><th>Город</th><th>Просмотры</th><th>Контакты</th><th>Конверсия</th><th>Расходы</th><th>₽/контакт</th><th>Предварительный сигнал</th></tr></thead><tbody>
{% for r in cities %}<tr class="city-summary-row" data-city="{{ r.name }}"><td>{{ r.name }}</td><td>{{ r.views }}</td><td>{{ r.contacts }}</td><td>{{ r.contact_rate }}</td><td>{{ r.spend }}</td><td>{{ r.cpa }}</td><td>{{ r.signal }}</td></tr>{% endfor %}
</tbody></table></div></div>
</section>
<section class="panel" style="margin-top:15px"><div class="upload"><h2>Категории и параметры</h2><a href="/download" style="color:var(--blue)">Скачать результаты CSV</a></div><div class="tablebox"><table id="categorySummaryTable"><thead><tr><th>Категория / параметр</th><th>Показы</th><th>Просмотры</th><th>Контакты</th><th>Конверсия</th><th>Расходы</th><th>₽/контакт</th></tr></thead><tbody>
{% for r in categories %}<tr class="category-summary-row" data-category="{{ r.name }}"><td>{{ r.name }}</td><td>{{ r.shows }}</td><td>{{ r.views }}</td><td>{{ r.contacts }}</td><td>{{ r.rate }}</td><td>{{ r.spend }}</td><td>{{ r.cpa }}</td></tr>{% endfor %}
</tbody></table></div></section>
<section class="panel" style="margin-top:15px">
<h2>Фильтры и сортировка</h2>
<div class="filters">
<label>Город <select id="filterCity"><option value="">Все города</option></select></label>
<label>Категория <select id="filterCategory"><option value="">Все категории</option></select></label>
<label>Оценка <select id="filterStatus"><option value="">Все оценки</option></select></label>
<label>Контакты <select id="filterContacts"><option value="">Любое количество</option><option value="yes">Есть контакты</option><option value="no">Нет контактов</option></select></label>
<label>Сортировать <select id="sortBy"><option value="default">По исходному порядку</option><option value="shows">Показы: больше → меньше</option><option value="views">Просмотры: больше → меньше</option><option value="contacts">Контакты: больше → меньше</option><option value="rate">Конверсия в контакт: выше → ниже</option><option value="spend">Расходы: больше → меньше</option><option value="cpaAsc">Стоимость контакта: дешевле → дороже</option><option value="cpaDesc">Стоимость контакта: дороже → дешевле</option><option value="priority">Приоритет: высокий → низкий</option></select></label>
<button type="button" id="resetFilters" class="secondary">Сбросить</button>
</div><div class="muted small" id="filterCount" style="margin-top:10px"></div>
</section>
<section class="panel" style="margin-top:15px"><h2>Строки выгрузки</h2><div class="muted small" style="margin-bottom:12px">Для оценки используются доступные поля. Если в файле нет ID или названия объявления, заголовок формируется по городу, категории, параметру и цене.</div>
<div class="tablebox"><table id="recommendationsTable"><thead><tr><th>Заголовок</th><th>Город</th><th>Показы</th><th>Просмотры</th><th>Контакты</th><th>Конверсия</th><th>Расходы</th><th>₽/контакт</th><th>Приоритет</th><th>Оценка</th><th>Что делать</th></tr></thead><tbody>
{% for r in rows %}<tr class="data-row" data-city="{{ r.city }}" data-category="{{ r.category }}" data-summary-category="{{ r.summary_category }}" data-status="{{ r.status }}" data-shows="{{ r.raw_shows }}" data-views="{{ r.raw_views }}" data-contacts="{{ r.raw_contacts }}" data-rate="{{ r.raw_rate }}" data-spend="{{ r.raw_spend }}" data-cpa="{{ r.raw_cpa }}" data-priority="{{ 3 if r.priority == 'Высокий' else 2 if r.priority == 'Средний' else 1 }}" data-name="{{ r.name }}"><td>{{ r.name }}</td><td>{{ r.city }}</td><td>{{ r.shows }}</td><td>{{ r.views }}</td><td>{{ r.contacts }}</td><td>{{ r.rate }}</td><td>{{ r.spend }}</td><td>{{ r.cpa }}</td><td><span class="tag {{ r.priority_kind }}">{{ r.priority }}</span></td><td><span class="tag {{ r.kind }}">{{ r.status }}</span></td><td class="muted small"><details><summary>Показать рекомендацию</summary><div>{{ r.next_step }}</div></details></td></tr>{% endfor %}
</tbody></table></div></section>
{% else %}
<section class="panel" style="margin-top:15px"><h2>Что появится после загрузки</h2><p class="muted">Сводные показатели, стоимость контакта, конверсия, сравнение городов и категорий, а также предварительные рекомендации на основе данных.</p><p class="muted small">Важно: если выгрузка содержит пересекающиеся срезы или агрегаты, их необходимо проверить перед использованием общих сумм.</p></section>
{% endif %}
<footer>Avito Analytics · MVP · Аналитические оценки предварительные и не заменяют проверку бизнес-контекста.</footer>
</div>
<script>
(function(){
 const table = document.querySelector('.data-row')?.closest('table');
 if (!table) return;
 const body = table.querySelector('tbody');
 const rows = Array.from(body.querySelectorAll('tr.data-row'));
 const citySelect = document.getElementById('filterCity');
 const categorySelect = document.getElementById('filterCategory');
 const statusSelect = document.getElementById('filterStatus');
 const contactsSelect = document.getElementById('filterContacts');
 const sortSelect = document.getElementById('sortBy');
 const count = document.getElementById('filterCount');
 const uniq = (key) => [...new Set(rows.map(r=>r.dataset[key]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ru'));
 function fill(select, values){values.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;select.appendChild(o);});}
 fill(citySelect,uniq('city')); fill(categorySelect,uniq('category')); fill(statusSelect,uniq('status'));
 const original = new Map(rows.map((r,i)=>[r,i]));
 function n(r,key){const v=Number(r.dataset[key]);return Number.isFinite(v)?v:0;}
 function apply(){
   let shown=rows.filter(r=>(!citySelect.value||r.dataset.city===citySelect.value)&&(!categorySelect.value||r.dataset.category===categorySelect.value)&&(!statusSelect.value||r.dataset.status===statusSelect.value)&&(!contactsSelect.value||(contactsSelect.value==='yes'?n(r,'contacts')>0:n(r,'contacts')===0)));
   const key=sortSelect.value;
   const map={shows:'shows',views:'views',contacts:'contacts',rate:'rate',spend:'spend',cpaAsc:'cpa',cpaDesc:'cpa',priority:'priority'};
   if(map[key]) shown.sort((a,b)=> (key==='cpaAsc'?1:-1)*(n(a,map[key])-n(b,map[key])) || original.get(a)-original.get(b));
   else shown.sort((a,b)=>original.get(a)-original.get(b));
   rows.forEach(r=>r.hidden=true); shown.forEach(r=>{r.hidden=false;body.appendChild(r);});
   // Rebuild summary tables from the exact filtered listing set, not from the full export.
   function renderSummary(tableSelector, key, type){
     const summaryBody=document.querySelector(tableSelector)?.querySelector('tbody');
     if(!summaryBody) return;
     const groups=new Map();
     shown.forEach(r=>{
       const name=(r.dataset[key]||'').trim()||'Не указано';
       if(!groups.has(name)) groups.set(name,{name,ads:0,shows:0,views:0,contacts:0,spend:0,noContacts:0});
       const g=groups.get(name);
       g.ads+=1; g.shows+=n(r,'shows'); g.views+=n(r,'views'); g.contacts+=n(r,'contacts'); g.spend+=n(r,'spend');
       if(n(r,'contacts')===0) g.noContacts+=1;
     });
     const sorted=[...groups.values()].sort((a,b)=>b.contacts-a.contacts||b.views-a.views||a.name.localeCompare(b.name,'ru'));
     const accountTotals=shown.reduce((a,r)=>{a.views+=n(r,'views');a.contacts+=n(r,'contacts');a.spend+=n(r,'spend');return a;},{views:0,contacts:0,spend:0});
     const accountCpa=accountTotals.contacts?accountTotals.spend/accountTotals.contacts:0;
     // Build category-level benchmarks across cities from the same filtered listing set.
     // Only compare category groups with >=100 views and >=3 contacts.
     const cityCategory=new Map();
     shown.forEach(r=>{
       const city=(r.dataset.city||'').trim()||'Не указан';
       const category=(r.dataset.summaryCategory||r.dataset.category||'').trim()||'Не указано';
       const key=city+'\\u0000'+category;
       if(!cityCategory.has(key)) cityCategory.set(key,{city,category,views:0,contacts:0,spend:0});
       const g=cityCategory.get(key);
       g.views+=n(r,'views');g.contacts+=n(r,'contacts');g.spend+=n(r,'spend');
     });
     const categoryBenchmarks=new Map();
     cityCategory.forEach(g=>{
       if(g.views<100 || g.contacts<3) return;
       if(!categoryBenchmarks.has(g.category)) categoryBenchmarks.set(g.category,[]);
       categoryBenchmarks.get(g.category).push({...g,cpa:g.spend/g.contacts});
     });
     const cityCategorySignals=new Map();
     cityCategory.forEach(g=>{
       if(g.views<100 || g.contacts<3) return;
       const peers=(categoryBenchmarks.get(g.category)||[]).filter(p=>p.city!==g.city);
       if(peers.length<2) return;
       const sortedCpa=peers.map(p=>p.cpa).sort((a,b)=>a-b);
       const mid=Math.floor(sortedCpa.length/2);
       const median=sortedCpa.length%2?sortedCpa[mid]:(sortedCpa[mid-1]+sortedCpa[mid])/2;
       if(!cityCategorySignals.has(g.city)) cityCategorySignals.set(g.city,[]);
       cityCategorySignals.get(g.city).push({category:g.category,cpa:g.spend/g.contacts,median,contacts:g.contacts,views:g.views});
     });
     summaryBody.replaceChildren();
     sorted.forEach(g=>{
       const tr=document.createElement('tr');
       tr.className=type==='city'?'city-summary-row':'category-summary-row';
       tr.dataset[key]=g.name;
       const cpaValue=g.contacts?g.spend/g.contacts:0;
       const cpa=g.contacts?Math.round(cpaValue).toLocaleString('ru-RU')+' ₽':'—';
       if(type==='city'){
         const rate=g.views?g.contacts/g.views*100:0;
         let signal;
         if(g.contacts===0 && g.views>=100 && g.spend>0){
           signal='Проверить объявления: есть расходы, нет контактов';
         } else if(g.contacts<5 || g.views<300){
           signal='Мало данных — продолжить тест';
         } else {
           const categorySignals=cityCategorySignals.get(g.name)||[];
           const worse=categorySignals.filter(x=>x.contacts>=5 && x.cpa>=x.median*1.25);
           const better=categorySignals.filter(x=>x.contacts>=5 && x.cpa<=x.median*0.8);
           if(worse.length){
             const x=worse.sort((a,b)=>(b.cpa/b.median)-(a.cpa/a.median))[0];
             signal='В категории «'+x.category+'» контакт дороже медианы других городов на '+Math.round((x.cpa/x.median-1)*100)+'% — проверить предложение';
           } else if(better.length){
             const x=better.sort((a,b)=>(a.cpa/a.median)-(b.cpa/b.median))[0];
             signal='В категории «'+x.category+'» контакт дешевле медианы других городов на '+Math.round((1-x.cpa/x.median)*100)+'% — проверить качество и стабильность';
           } else if(categorySignals.length){
             signal='По сопоставимым категориям сильного отклонения нет';
           } else if(accountCpa>0 && g.contacts>=10 && cpaValue>=accountCpa*1.25){
             signal='Стоимость контакта выше средней по выборке — проверить объявления';
           } else if(accountCpa>0 && g.contacts>=10 && cpaValue<=accountCpa*0.8){
             signal='Стоимость контакта ниже средней по выборке — проверить качество и стабильность';
           } else {
             signal='Нет достаточных сопоставимых категорий; продолжить наблюдение';
           }
         }
         [g.name,Math.round(g.views).toLocaleString('ru-RU'),
          Math.round(g.contacts).toLocaleString('ru-RU'),
          g.views?rate.toLocaleString('ru-RU',{maximumFractionDigits:2})+'%':'—',
          Math.round(g.spend).toLocaleString('ru-RU')+' ₽',
          cpa,signal]
          .forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.appendChild(td);});
       } else {
         const rate=g.views?g.contacts/g.views*100:0;
         [g.name,Math.round(g.shows).toLocaleString('ru-RU'),Math.round(g.views).toLocaleString('ru-RU'),Math.round(g.contacts).toLocaleString('ru-RU'),rate.toLocaleString('ru-RU',{maximumFractionDigits:2})+'%',Math.round(g.spend).toLocaleString('ru-RU')+' ₽',cpa].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.appendChild(td);});
       }
       summaryBody.appendChild(tr);
     });
   }
   renderSummary('#citySummaryTable','city','city');
   renderSummary('#categorySummaryTable','summaryCategory','category');
   const scoped=!!(citySelect.value||categorySelect.value||statusSelect.value||contactsSelect.value);
   document.getElementById('recommendationsList').hidden=scoped;
   document.getElementById('recommendationScopeNotice').hidden=!scoped;
   count.textContent='Показано объявлений: '+shown.length+' из '+rows.length;
   const sums=shown.reduce((a,r)=>{a.shows+=n(r,'shows');a.views+=n(r,'views');a.contacts+=n(r,'contacts');a.spend+=n(r,'spend');return a;},{shows:0,views:0,contacts:0,spend:0});
   const metrics=Array.from(document.querySelectorAll('.metric'));
   const fmt=x=>Math.round(x).toLocaleString('ru-RU');
   const money=x=>Math.round(x).toLocaleString('ru-RU')+' ₽';
   if(metrics.length>=4){
    metrics[0].querySelector('.value').textContent=fmt(sums.shows);
    metrics[1].querySelector('.value').textContent=fmt(sums.views);
    metrics[1].querySelector('.small').textContent='Конверсия из показов: '+(sums.shows?sums.views/sums.shows*100:0).toLocaleString('ru-RU',{maximumFractionDigits:2})+'%';
    metrics[2].querySelector('.value').textContent=fmt(sums.contacts);
    metrics[2].querySelector('.small').textContent='Конверсия в контакт: '+(sums.views?sums.contacts/sums.views*100:0).toLocaleString('ru-RU',{maximumFractionDigits:2})+'%';
    metrics[3].querySelector('.value').textContent=money(sums.spend);
    metrics[3].querySelector('.small').textContent='Стоимость контакта: '+(sums.contacts?money(sums.spend/sums.contacts):'—');
   }
 }
 [citySelect,categorySelect,statusSelect,contactsSelect,sortSelect].forEach(el=>el.addEventListener('change',apply));
 document.getElementById('resetFilters').addEventListener('click',()=>{[citySelect,categorySelect,statusSelect,contactsSelect].forEach(el=>el.value='');sortSelect.value='default';apply();});
 apply();
})();
</script>
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

@app.get("/analyze")
def analyze_get():
    # Refreshing the upload endpoint sends GET; return users to the upload page instead of 405.
    return redirect("/")

@app.post("/analyze")
def analyze():
    global LAST_EXPORT
    file = request.files.get("file")
    if not file or not file.filename:
        return render_template_string(PAGE, has_data=False, error="Выберите файл.")
    name = file.filename.lower()
    validation_report = None
    try:
        raw = file.read()
        if name.endswith(".csv"):
            try:
                source = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", encoding="utf-8-sig")
            except UnicodeDecodeError:
                source = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", encoding="cp1251")
        elif name.endswith(".xlsx"):
            source = read_excel_preserving_hyperlinks(raw)
        elif name.endswith(".xls"):
            source = pd.read_excel(io.BytesIO(raw))
        else:
            raise ValueError("Поддерживаются файлы .xlsx, .xls и .csv.")
        # Normalize headers before validation and alias matching. Avito exports may
        # use non-breaking spaces, which otherwise cause metric columns to be missed.
        source = clean_frame(source)
        metric_columns = {}
        for canonical in ["Показы", "Просмотры", "Контакты", "Расходы"]:
            actual = find_col(source, canonical)
            if actual:
                metric_columns[canonical] = actual
        identity_columns = []
        for canonical in ["Номер объявления", "Название объявления"]:
            actual = find_col(source, canonical)
            if actual:
                identity_columns.append(actual)
        validation_report = validate_export(
            source,
            metric_columns=metric_columns,
            identity_columns=identity_columns,
        )
        df = prepare_data(source)
        LAST_EXPORT = df.copy()

        # Persist an immutable snapshot. The export's reporting period is not parsed yet,
        # so comparisons are by upload time and must be treated as preliminary.
        history_account = os.environ.get("AVITO_ANALYTICS_ACCOUNT", "default")
        history_rows = []
        for _, history_row in df.iterrows():
            history_rows.append({
                "Номер объявления": history_row.get("Номер объявления", ""),
                "Название объявления": history_row.get("Название объявления", ""),
                "Город": history_row.get("Город", ""),
                "Категория": history_row.get("Категория", ""),
                "Подкатегория": history_row.get("Подкатегория", ""),
                "Параметр": history_row.get("Параметр", ""),
                "Цена": history_row.get("Цена", ""),
                "Показы": history_row.get("Показы", 0),
                "Просмотры": history_row.get("Просмотры", 0),
                "Контакты": history_row.get("Контакты", 0),
                "Расходы": history_row.get("Расходы", 0),
                "Избранное": history_row.get("Избранное", 0),
            })
        history_result = HistoryStore().save_snapshot(
            history_rows, raw, source_filename=file.filename, account=history_account,
            report_start=request.form.get("report_start", ""),
            report_end=request.form.get("report_end", "")
        )
        history_result["source_filename"] = file.filename

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
            Объявлений=("Город", "size"), Показы=("Показы", "sum"),
            Просмотры=("Просмотры", "sum"), Контакты=("Контакты", "sum"),
            Расходы=("Расходы", "sum"),
            БезКонтактов=("Контакты", lambda values: int((values == 0).sum())))
        city_df["cpa"] = city_df["Расходы"] / city_df["Контакты"].replace(0, pd.NA)
        city_df["contact_rate"] = city_df["Контакты"] / city_df["Просмотры"].replace(0, pd.NA) * 100
        city_df["no_contact_share"] = city_df["БезКонтактов"] / city_df["Объявлений"].replace(0, pd.NA) * 100
        city_df = city_df.sort_values(["Контакты", "Просмотры"], ascending=False).head(15).fillna(0)
        def city_signal(r):
            city_contacts = int(r["Контакты"])
            city_views = int(r["Просмотры"])
            city_spend = float(r["Расходы"])
            city_cpa = float(r["cpa"])
            if city_contacts == 0 and city_views >= 100 and city_spend > 0:
                return "Проверить объявления: есть расходы, нет контактов"
            if city_contacts < 5 or city_views < 300:
                return "Мало данных — продолжить тест"
            if contacts and city_contacts >= 10 and city_cpa <= cpa * 0.8:
                return "Кандидат на осторожное усиление"
            if contacts and city_contacts >= 10 and city_cpa >= cpa * 1.25:
                return "Проверить экономику и качество обращений"
            return "Наблюдать; сравнить одинаковые категории"
        cities = [{"name":safe_text(r["_city"]), "ads":integer(r["Объявлений"]),
                   "shows":integer(r["Показы"]), "views":integer(r["Просмотры"]),
                   "contacts":integer(r["Контакты"]), "spend":money(r["Расходы"]),
                   "contact_rate":f'{r["contact_rate"]:.2f}%'.replace(".",",") if r["Просмотры"] else "—",
                   "no_contact_share":f'{r["no_contact_share"]:.0f}%'.replace(".",","),
                   "signal":city_signal(r),
                   "cpa":money(r["cpa"]) if r["Контакты"] else "—"}
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

        # Compare listings against peers, not the whole account: cities/categories can have
        # materially different economics. Require at least three other eligible listings.
        eligible_peers = df[(df["Просмотры"] >= 100) & (df["Контакты"] >= 3)].copy()
        eligible_peers["_peer_cpa"] = eligible_peers["Расходы"] / eligible_peers["Контакты"]
        positive_spend = df.loc[df["Расходы"] > 0, "Расходы"]
        median_spend = float(positive_spend.median()) if not positive_spend.empty else 0.0
        rows = []
        row_actions = []
        for idx, r in df.iterrows():
            obj_cpa = float(r["Стоимость контакта, ₽"])
            rv = float(r["Просмотры"])
            rc = float(r["Контакты"])
            rs = float(r["Расходы"])
            same_city_category = eligible_peers[
                (eligible_peers["Город"] == r["Город"]) &
                (eligible_peers["Категория"] == r["Категория"]) &
                (eligible_peers.index != idx)
            ]
            benchmark_scope = "в том же городе и категории"
            peers = same_city_category
            if len(peers) < 3:
                peers = eligible_peers[
                    (eligible_peers["Категория"] == r["Категория"]) &
                    (eligible_peers.index != idx)
                ]
                benchmark_scope = "в той же категории по всем городам"
            benchmark_cpa = float(peers["_peer_cpa"].median()) if len(peers) >= 3 else 0.0
            if rc == 0 and rs > 0 and rv >= 100:
                status, kind = "Проверить расходы", "bad"
                action = "check"
                next_step = "Проверить фото, цену, описание и качество трафика; не отключать автоматически."
            elif rv < 100 or rc < 3:
                status, kind = "Недостаточно данных", "warn"
                action = "insufficient"
                next_step = "Накопить статистику; пока не менять бюджет только по этим данным."
            elif benchmark_cpa <= 0:
                status, kind = "Нет сопоставимых данных", "warn"
                action = "compare"
                next_step = "Недостаточно похожих объявлений с минимум 100 просмотрами и 3 контактами для надёжного сравнения."
            elif obj_cpa <= benchmark_cpa * 0.80 and rc >= 5:
                status, kind = "Потенциал усиления", ""
                action = "strengthen"
                next_step = f"Стоимость контакта минимум на 20% ниже медианы аналогов {benchmark_scope}. Проверьте качество контактов и стабильность результата перед тестом увеличения бюджета."
                row_actions.append((r, obj_cpa))
            elif obj_cpa >= benchmark_cpa * 1.25:
                status, kind = "Оптимизировать", "warn"
                action = "optimize"
                next_step = f"Стоимость контакта минимум на 25% выше медианы аналогов {benchmark_scope}. Проверьте цену, фото и предложение до сокращения бюджета."
                row_actions.append((r, obj_cpa))
            else:
                status, kind = "Сопоставить с аналогами", "warn"
                action = "compare"
                next_step = f"Стоимость контакта близка к медиане аналогов {benchmark_scope}; продолжайте наблюдение и сравните качество обращений."
            if benchmark_cpa > 0 and action not in ("check", "insufficient"):
                next_step += f" Медиана аналогов: {money(benchmark_cpa)}; объявлений в сравнении: {len(peers)}."
            if rc == 0 and rs > 0 and rv >= 100:
                priority, priority_kind = "Высокий", "bad"
            elif action == "optimize" and benchmark_cpa > 0 and obj_cpa >= benchmark_cpa * 1.5 and rc >= 3:
                priority, priority_kind = "Высокий", "bad"
            elif rs > 0 and (action in ("check", "optimize", "insufficient") or rv < 100 or rc < 3):
                priority, priority_kind = "Средний", "warn"
            else:
                priority, priority_kind = "Низкий", ""
            rows.append({"name":safe_text(r["Объект"]), "city":safe_text(r["Город"]) or "—",
                "category": safe_text(r["Категория"]) or "Не указано",
                "summary_category": " · ".join([safe_text(r[c]) for c in ["Категория", "Подкатегория", "Параметр"] if safe_text(r[c])]) or "Не указано",
                "shows":integer(r["Показы"]),"views":integer(rv),
                "contacts":integer(rc),
                "rate":f'{r["Конверсия в контакт, %"]:.2f}%'.replace(".",","),
                "spend":money(rs),
                "cpa":money(obj_cpa) if rc else "—",
                "raw_shows":float(r["Показы"]), "raw_views":rv, "raw_contacts":rc,
                "raw_rate":float(r["Конверсия в контакт, %"]), "raw_spend":rs,
                "raw_cpa":obj_cpa if rc else 1e30,
                "status":status,"kind":kind,"priority":priority,"priority_kind":priority_kind,"next_step":next_step})

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

        # Funnel diagnosis is descriptive: without historical or external benchmarks,
        # do not claim that a conversion rate is objectively poor.
        funnel = []
        if shows > 0:
            view_rate_value = views / shows * 100
            if shows < 100 or views < 20:
                status, kind = "Мало данных", "warn"
                action_title = "Накопить данные"
                action_text = "Проверьте релевантность показов и соберите больше статистики. Не меняйте сразу несколько элементов."
            else:
                status, kind = "Нужен ориентир", "warn"
                action_title = "Сравнить с историей или аналогами"
                action_text = "По одной выгрузке нельзя достоверно назвать конверсию плохой или хорошей. Сравните с сопоставимым прошлым периодом или похожими объявлениями; при просадке проверьте заголовок, фото, цену и географию."
            funnel.append({"name":"Показы → просмотры","rate":f"{view_rate_value:.2f}%".replace(".",","),
                "input":integer(shows),"output":integer(views),"status":status,"kind":kind,
                "action_title":action_title,"action_text":action_text})
        if views > 0:
            contact_rate_value = contacts / views * 100
            if views < 100 or contacts < 3:
                status, kind = "Мало данных", "warn"
                action_title = "Накопить данные"
                action_text = "Не делайте вывод по единичным контактам. Проверьте условия предложения и дождитесь более надёжной выборки."
            else:
                status, kind = "Нужен ориентир", "warn"
                action_title = "Сравнить с историей или аналогами"
                action_text = "По одной выгрузке нельзя достоверно назвать конверсию плохой или хорошей. Сравните с сопоставимым прошлым периодом и похожими категориями/городами; если есть просадка, проверьте цену, описание, фотографии и условия покупки."
            funnel.append({"name":"Просмотры → контакты","rate":f"{contact_rate_value:.2f}%".replace(".",","),
                "input":integer(views),"output":integer(contacts),"status":status,"kind":kind,
                "action_title":action_title,"action_text":action_text})
        if not funnel:
            funnel.append({"name":"Воронка","rate":"—","input":"—","output":"—","status":"Нет данных","kind":"warn",
                "action_title":"Проверьте выгрузку","action_text":"Для расчёта нужны показы, просмотры и контакты."})

        kpis = {"shows":integer(shows),"views":integer(views),"contacts":integer(contacts),
                "spend":money(spend),"view_rate":f"{view_rate:.2f}%".replace(".",","),
                "contact_rate":f"{contact_rate:.2f}%".replace(".",","),
                "cpa":money(cpa) if contacts else "—"}
        return render_template_string(PAGE, has_data=True, error=None, kpis=kpis, funnel=funnel,
            validation_report=validation_report, row_count=len(df), recommendations=recommendations, cities=cities,
            categories=categories, rows=rows, history_result=history_result)
    except Exception as exc:
        return render_template_string(PAGE, has_data=False,
            error=f"Не удалось обработать файл: {str(exc)}"), 400

@app.get("/history")
def history():
    account = os.environ.get("AVITO_ANALYTICS_ACCOUNT", "default")
    store = HistoryStore()
    snapshots = store.list_snapshots(account=account, limit=50)
    comparison = store.compare_latest(account=account)
    return render_template_string("""
    <!doctype html><html lang="ru"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>История — Avito Analytics</title>
    <style>
      body{font-family:Arial,sans-serif;max-width:1100px;margin:30px auto;padding:0 16px;background:#0b1120;color:#e5e7eb}
      a{color:#8ab4ff} .muted{color:#9ca3af} input[type=date]{background:#0b1120;color:#e5e7eb;border:1px solid #374151;border-radius:6px;padding:8px} table{width:100%;border-collapse:collapse;margin:18px 0}
      th,td{text-align:left;padding:10px;border-bottom:1px solid #374151;font-size:14px}
      .panel{border:1px solid #374151;border-radius:10px;padding:16px;margin:18px 0;overflow:auto}
      code{overflow-wrap:anywhere}
    </style>
    <h1>История статистики</h1><p><a href="/">← Вернуться к загрузке</a></p>
    <p class="muted">Аккаунт: {{ account }}. Повторная загрузка идентичного файла не создаёт новый снимок.</p>
    <div class="panel"><strong>Важно о точности сравнения</strong><p class="muted">Сейчас приложение сохраняет дату загрузки, но не определяет автоматически период статистики внутри файла. Поэтому два снимка сравниваются по времени загрузки, а не по подтверждённым непересекающимся периодам. Если выгрузки содержат накопительные значения или разные диапазоны дат, разница не показывает изменение эффективности за период. Используйте её только как предварительную проверку; следующий этап — распознавание периода и корректное сравнение сопоставимых интервалов.</p></div>
    <div class="panel"><h2>Последние снимки</h2>
    {% if snapshots %}<table><thead><tr><th>ID</th><th>Дата загрузки</th><th>Файл</th><th>Период отчёта</th><th>Строк</th></tr></thead><tbody>
    {% for s in snapshots %}<tr><td>{{s.id}}</td><td>{{s.captured_at}}</td><td>{{s.source_filename}}</td><td>{% if s.report_start or s.report_end %}{{s.report_start or "…"}} — {{s.report_end or "…"}}{% else %}<span class="muted">Не указан</span>{% endif %}</td><td>{{s.row_count}}</td></tr>{% endfor %}
    </tbody></table>{% else %}<p>История пока пуста. Загрузите статистику через главную страницу.</p>{% endif %}</div>
    <div class="panel"><h2>Предварительное сравнение двух последних снимков</h2>
    {% if comparison.available %}
      <p>Загрузки: {{comparison.older_captured_at}} → {{comparison.newer_captured_at}}</p>
      <p>Периоды отчётов: {% if comparison.older_report_start or comparison.older_report_end %}{{comparison.older_report_start or "…"}} — {{comparison.older_report_end or "…"}}{% else %}не указаны{% endif %} → {% if comparison.newer_report_start or comparison.newer_report_end %}{{comparison.newer_report_start or "…"}} — {{comparison.newer_report_end or "…"}}{% else %}не указаны{% endif %}</p>
      <p>Изменения строк: {{comparison.changes|length}}</p>
      <p class="muted">{{comparison.note}}</p>
      <table><thead><tr><th>Объявление</th><th>Статус</th><th>Просмотры</th><th>Контакты</th><th>Расходы</th><th>Избранное</th></tr></thead><tbody>
      {% for x in comparison.changes %}
       <tr><td>{{x.title}}</td><td>{% if x.status=='new' %}Новое{% elif x.status=='missing' %}Не найдено в новой выгрузке{% else %}Есть в обоих снимках{% endif %}</td>
       {% if x.current and x.previous %}
        <td>{{x.metrics.views.before}} → {{x.metrics.views.after}} ({{'%+.0f'|format(x.metrics.views.delta)}})</td>
        <td>{{x.metrics.contacts.before}} → {{x.metrics.contacts.after}} ({{'%+.0f'|format(x.metrics.contacts.delta)}})</td>
        <td>{{x.metrics.spend.before}} → {{x.metrics.spend.after}} ({{'%+.0f'|format(x.metrics.spend.delta)}})</td>
        <td>{{x.metrics.favorites.before}} → {{x.metrics.favorites.after}} ({{'%+.0f'|format(x.metrics.favorites.delta)}})</td>
       {% else %}<td>—</td><td>—</td><td>—</td><td>—</td>{% endif %}</tr>
      {% endfor %}</tbody></table>
    {% else %}<p>{{comparison.reason}}</p>{% endif %}</div>
    </html>
    """, account=account, snapshots=snapshots, comparison=comparison)


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
