
import os
from flask import Flask, request, render_template_string

app = Flask(__name__)

AVITO_CLIENT_ID = os.environ.get("AVITO_CLIENT_ID")
AVITO_CLIENT_SECRET = os.environ.get("AVITO_CLIENT_SECRET")

HTML = r"""
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Avito Analytics</title>
<style>
:root {
  --bg:#0b1120; --panel:#121b2d; --line:#253249;
  --text:#edf2fa; --muted:#93a4bd; --blue:#72a7ff;
  --green:#43d6a0; --red:#ff7888; --yellow:#ffd078;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.5 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1440px;margin:auto;padding:28px}
header{display:flex;justify-content:space-between;align-items:center;
gap:16px;margin-bottom:30px;flex-wrap:wrap}
.brand{font-size:23px;font-weight:750;letter-spacing:-.6px}
.brand span{color:var(--blue)}
.sub{color:var(--muted);font-size:12px;margin-top:4px}
.demo{border:1px solid #765b32;background:#302619;color:var(--yellow);
padding:7px 12px;border-radius:8px;font-size:12px}
h1{font-size:27px;letter-spacing:-.7px;margin:0}
h2{font-size:16px;margin:0 0 18px}
.intro{display:flex;justify-content:space-between;align-items:end;
gap:16px;margin-bottom:22px;flex-wrap:wrap}
.muted{color:var(--muted)}
select,button{background:var(--panel);color:var(--text);
border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:inherit}
button{cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px}
.panel,.metric{background:var(--panel);border:1px solid var(--line);
border-radius:14px;padding:20px;min-width:0}
.metric-label{color:var(--muted);font-size:13px}
.metric-value{font-size:29px;font-weight:750;letter-spacing:-.8px;margin:12px 0 5px}
.change{font-size:12px}
.good{color:var(--green)} .bad{color:var(--red)}
.neutral{color:var(--muted)}
.main-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(280px,1fr);
gap:15px;margin-top:15px}
.chart-legend{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);
font-size:12px;margin-bottom:14px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
svg{width:100%;height:auto;display:block;overflow:visible}
.recommendation{padding:13px 0;border-bottom:1px solid var(--line)}
.recommendation:last-child{border:0;padding-bottom:0}
.tag{display:inline-block;padding:3px 8px;border-radius:5px;
font-size:11px;margin-bottom:7px}
.tag.green{background:#163a35;color:var(--green)}
.tag.red{background:#42232d;color:var(--red)}
.tag.yellow{background:#42351f;color:var(--yellow)}
.rec-title{font-weight:650;margin-bottom:4px}
.rec-text{font-size:12px;color:var(--muted)}
.table-panel{margin-top:15px}
.table-head{display:flex;justify-content:space-between;align-items:center;
gap:12px;margin-bottom:14px;flex-wrap:wrap}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;white-space:nowrap}
th{text-align:left;color:var(--muted);font-size:11px;font-weight:550;
padding:12px;border-bottom:1px solid var(--line)}
td{padding:14px 12px;border-bottom:1px solid var(--line)}
tbody tr:last-child td{border-bottom:0}
.status{font-size:11px;border-radius:5px;padding:4px 8px}
.status.good{background:#163a35}
.status.bad{background:#42232d}
.status.mid{background:#42351f;color:var(--yellow)}
.small{font-size:12px}
footer{color:var(--muted);font-size:11px;margin:22px 0 4px}
.empty{padding:22px 0;color:var(--muted)}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.main-grid{grid-template-columns:1fr}.wrap{padding:18px}}
@media(max-width:480px){.wrap{padding:12px}.grid{gap:9px}
.metric,.panel{padding:14px}.metric-value{font-size:23px}
h1{font-size:23px}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div>
    <div class="brand"><span>Avito</span> Analytics</div>
    <div class="sub">Платформа аналитики и принятия решений</div>
  </div>
  <div class="demo">● ДЕМО · НЕ РЕАЛЬНЫЕ ДАННЫЕ</div>
</header>

<section class="intro">
  <div>
    <h1>Обзор кабинета</h1>
    <div class="muted" style="margin-top:7px">
      Анализ эффективности объявлений и продвижения
    </div>
  </div>
  <select id="period" aria-label="Период анализа">
    <option value="7">Последние 7 дней</option>
    <option value="30" selected>Последние 30 дней</option>
    <option value="90">Последние 90 дней</option>
  </select>
</section>

<section class="grid">
  <div class="metric">
    <div class="metric-label">Просмотры</div>
    <div class="metric-value" id="views">12 480</div>
    <div class="change good">↑ 14,2% <span class="neutral">к прошлому периоду</span></div>
  </div>
  <div class="metric">
    <div class="metric-label">Контакты</div>
    <div class="metric-value" id="contacts">386</div>
    <div class="change good">↑ 9,6% <span class="neutral">к прошлому периоду</span></div>
  </div>
  <div class="metric">
    <div class="metric-label">Расходы на продвижение</div>
    <div class="metric-value" id="spend">48 200 ₽</div>
    <div class="change neutral">За выбранный период</div>
  </div>
  <div class="metric">
    <div class="metric-label">Стоимость контакта</div>
    <div class="metric-value" id="cpc">124,87 ₽</div>
    <div class="change neutral">Расходы ÷ контакты</div>
  </div>
</section>

<section class="main-grid">
  <div class="panel">
    <h2>Динамика показателей</h2>
    <div class="chart-legend">
      <span><i class="dot" style="background:#72a7ff"></i>Просмотры</span>
      <span><i class="dot" style="background:#43d6a0"></i>Контакты</span>
    </div>
    <svg viewBox="0 0 620 230" role="img" aria-label="Демонстрационный график динамики">
      <g stroke="#253249" stroke-width="1">
        <line x1="42" y1="25" x2="600" y2="25"/>
        <line x1="42" y1="70" x2="600" y2="70"/>
        <line x1="42" y1="115" x2="600" y2="115"/>
        <line x1="42" y1="160" x2="600" y2="160"/>
        <line x1="42" y1="195" x2="600" y2="195"/>
      </g>
      <g fill="#93a4bd" font-size="10">
        <text x="4" y="29">100%</text><text x="10" y="74">75%</text>
        <text x="10" y="119">50%</text><text x="10" y="164">25%</text>
        <text x="42" y="215">1</text><text x="220" y="215">7</text>
        <text x="400" y="215">14</text><text x="580" y="215">30</text>
      </g>
      <polyline id="viewsLine" fill="none" stroke="#72a7ff" stroke-width="3"
        stroke-linecap="round" stroke-linejoin="round"
        points="42,150 110,130 180,145 250,95 320,110 390,72 460,90 530,48 590,58"/>
      <polyline id="contactsLine" fill="none" stroke="#43d6a0" stroke-width="3"
        stroke-linecap="round" stroke-linejoin="round"
        points="42,180 110,168 180,174 250,155 320,163 390,143 460,150 530,125 590,132"/>
    </svg>
    <div class="muted small">Иллюстративные значения. График пока не связан с API.</div>
  </div>

  <div class="panel">
    <h2>Рекомендации системы</h2>
    <div class="recommendation">
      <span class="tag green">УСИЛИТЬ</span>
      <div class="rec-title">Найти объявления-лидеры</div>
      <div class="rec-text">Сравнить стоимость контакта и объём обращений. Масштабировать только после проверки стабильности результата.</div>
    </div>
    <div class="recommendation">
      <span class="tag yellow">ОПТИМИЗИРОВАТЬ</span>
      <div class="rec-title">Проверить конверсию</div>
      <div class="rec-text">Найти объявления с просмотрами, но низкой долей контактов. Проверить цену, фото и предложение.</div>
    </div>
    <div class="recommendation">
      <span class="tag red">КОНТРОЛЬ</span>
      <div class="rec-title">Проверить расходы</div>
      <div class="rec-text">Сопоставить расходы с обращениями по каждому объявлению, прежде чем менять бюджет.</div>
    </div>
  </div>
</section>

<section class="panel table-panel">
  <div class="table-head">
    <h2 style="margin:0">Эффективность объявлений</h2>
    <select id="filter" aria-label="Фильтр объявлений">
      <option value="all">Все объявления</option>
      <option value="good">Эффективные</option>
      <option value="bad">Требуют внимания</option>
    </select>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>ОБЪЯВЛЕНИЕ</th><th>ПРОСМОТРЫ</th><th>КОНТАКТЫ</th>
        <th>РАСХОДЫ</th><th>₽ / КОНТАКТ</th><th>ОЦЕНКА</th>
      </tr></thead>
      <tbody id="ads"></tbody>
    </table>
  </div>
  <div class="muted small" style="margin-top:12px">
    Пример данных для проверки интерфейса. Оценки не являются реальными рекомендациями.
  </div>
</section>

<footer>
  Avito Analytics · Демонстрационный прототип · Реальные данные будут доступны после настройки интеграции.
</footer>
</div>

<script>
const base = [
 {name:"Объявление №1 · Категория A",views:3240,contacts:112,spend:9800},
 {name:"Объявление №2 · Категория B",views:2180,contacts:76,spend:7200},
 {name:"Объявление №3 · Категория A",views:1840,contacts:19,spend:8100},
 {name:"Объявление №4 · Категория C",views:1260,contacts:8,spend:5600},
 {name:"Объявление №5 · Категория B",views:3960,contacts:171,spend:17500}
];

const fmt = n => Math.round(n).toLocaleString("ru-RU");
const rub = n => n.toLocaleString("ru-RU",{maximumFractionDigits:2})+" ₽";

function render() {
  const period = Number(document.getElementById("period").value);
  const filter = document.getElementById("filter").value;
  const factor = period / 30;
  const rows = base.map(a => ({
    ...a,
    views:Math.round(a.views*factor),
    contacts:Math.round(a.contacts*factor),
    spend:Math.round(a.spend*factor)
  })).map(a => ({
    ...a,
    cost:a.contacts ? a.spend/a.contacts : null,
    rate:a.views ? a.contacts/a.views*100 : 0
  }));

  const views = rows.reduce((s,a)=>s+a.views,0);
  const contacts = rows.reduce((s,a)=>s+a.contacts,0);
  const spend = rows.reduce((s,a)=>s+a.spend,0);

  document.getElementById("views").textContent=fmt(views);
  document.getElementById("contacts").textContent=fmt(contacts);
  document.getElementById("spend").textContent=rub(spend);
  document.getElementById("cpc").textContent=contacts?rub(spend/contacts):"—";

  const tbody = document.getElementById("ads");
  tbody.replaceChildren();

  rows.forEach(a=>{
    const good = a.cost !== null && a.cost <= spend/Math.max(contacts,1);
    if(filter==="good" && !good) return;
    if(filter==="bad" && good) return;

    const tr=document.createElement("tr");
    const values=[
      a.name,fmt(a.views),fmt(a.contacts),rub(a.spend),
      a.cost===null?"Нет контактов":rub(a.cost)
    ];
    values.forEach((value,i)=>{
      const td=document.createElement("td");
      td.textContent=value;
      if(i===0) td.style.fontWeight="600";
      tr.appendChild(td);
    });
    const status=document.createElement("td");
    const badge=document.createElement("span");
    badge.className="status "+(good?"good":"bad");
    badge.textContent=good?"Ниже средней стоимости":"Выше средней стоимости";
    status.appendChild(badge);
    tr.appendChild(status);
    tbody.appendChild(tr);
  });

  if(!tbody.children.length){
    const tr=document.createElement("tr");
    const td=document.createElement("td");
    td.colSpan=6;
    td.className="empty";
    td.textContent="Нет объявлений для выбранного фильтра.";
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
}

document.getElementById("period").addEventListener("change",render);
document.getElementById("filter").addEventListener("change",render);
render();
</script>
</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/health")
def health():
    return {"status": "ok", "app": "Avito Analytics"}, 200


@app.route("/callback")
def callback():
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return (
            "<h1>Ошибка авторизации</h1>"
            "<p>Avito вернул ошибку авторизации.</p>"
        ), 400

    if code:
        # Код получен, но обмен на токен пока не реализован.
        # Не сохраняем и не показываем код авторизации.
        return """
        <h1>Avito Analytics</h1>
        <p>Код авторизации получен.</p>
        <p>Обмен кода на токен ещё не настроен.</p>
        """, 200

    return """
    <h1>Avito Analytics</h1>
    <p>Callback работает. Код авторизации не передан.</p>
    """, 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
