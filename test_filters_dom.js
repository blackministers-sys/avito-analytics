const fs = require('fs');
const assert = require('assert');
const { JSDOM } = require('jsdom');

// Execute the real inline filtering script from app.py against a small DOM fixture.
const source = fs.readFileSync('app.py', 'utf8');
const match = source.match(/<script>\s*([\s\S]*?)<\/script>/);
assert(match, 'Could not find the inline filtering script in app.py');

const html = `<!doctype html><html><body>
  <div class="metric"><div class="value"></div><div class="small"></div></div>
  <div class="metric"><div class="value"></div><div class="small"></div></div>
  <div class="metric"><div class="value"></div><div class="small"></div></div>
  <div class="metric"><div class="value"></div><div class="small"></div></div>
  <div id="recommendationsList"></div>
  <div id="recommendationScopeNotice" hidden></div>
  <select id="filterCity"><option value="">Все города</option></select>
  <select id="filterCategory"><option value="">Все категории</option></select>
  <select id="filterStatus"><option value="">Все оценки</option></select>
  <select id="filterContacts"><option value="">Любое количество</option><option value="yes">Есть контакты</option><option value="no">Нет контактов</option></select>
  <select id="sortBy"><option value="default">Исходный порядок</option><option value="contacts">Контакты: больше</option><option value="cpaAsc">CPA: дешевле</option></select>
  <button id="resetFilters" type="button">Сбросить</button><div id="filterCount"></div>
  <table><tbody>
    <tr class="data-row" data-city="Омск" data-category="Авто" data-summary-category="Авто · Запчасти · A" data-status="Хорошо" data-shows="100" data-views="20" data-contacts="2" data-rate="10" data-spend="200" data-cpa="100" data-name="A"><td>A</td></tr>
    <tr class="data-row" data-city="Ростов" data-category="Авто" data-summary-category="Авто · Запчасти · B" data-status="Слабо" data-shows="200" data-views="30" data-contacts="0" data-rate="0" data-spend="50" data-cpa="1e30" data-name="B"><td>B</td></tr>
    <tr class="data-row" data-city="Омск" data-category="Запчасти" data-summary-category="Запчасти · Кузов · C" data-status="Хорошо" data-shows="300" data-views="60" data-contacts="6" data-rate="10" data-spend="300" data-cpa="50" data-name="C"><td>C</td></tr>
  </tbody></table>
  <table id="citySummaryTable"><tbody></tbody></table>
  <table id="categorySummaryTable"><tbody></tbody></table>
</body></html>`;
const dom = new JSDOM(html, { runScripts: 'outside-only' });
const { document, Event } = dom.window;
dom.window.eval(match[1]);
const city = document.getElementById('filterCity');
const category = document.getElementById('filterCategory');
const contacts = document.getElementById('filterContacts');
const sort = document.getElementById('sortBy');
const count = document.getElementById('filterCount');
const visibleNames = () => [...document.querySelectorAll('.data-row:not([hidden])')].map(r => r.dataset.name);
const metric = i => document.querySelectorAll('.metric .value')[i].textContent;

// Initial state includes all listings and aggregate KPIs.
assert.deepStrictEqual(visibleNames(), ['A', 'B', 'C']);
assert.strictEqual(count.textContent, 'Показано объявлений: 3 из 3');
assert.strictEqual(metric(0), '600');
assert.strictEqual(metric(2), '8');

// Category filter uses the main Avito category, while the summary retains detailed grouping.
category.value = 'Авто';
category.dispatchEvent(new Event('change'));
assert.deepStrictEqual(visibleNames(), ['A', 'B']);
assert.strictEqual(count.textContent, 'Показано объявлений: 2 из 3');
assert.strictEqual(document.querySelectorAll('#categorySummaryTable tbody tr').length, 2);
document.getElementById('resetFilters').click();

// City filter narrows listing rows and rebuilds summary groups and KPIs.
city.value = 'Омск';
city.dispatchEvent(new Event('change'));
assert.deepStrictEqual(visibleNames(), ['A', 'C']);
assert.strictEqual(count.textContent, 'Показано объявлений: 2 из 3');
assert.strictEqual(metric(0), '400');
assert.strictEqual(metric(2), '8');
assert.deepStrictEqual([...document.querySelectorAll('#citySummaryTable tbody tr')].map(r => r.dataset.city), ['Омск']);
assert.deepStrictEqual([...document.querySelectorAll('#categorySummaryTable tbody tr')].map(r => r.dataset.summaryCategory).sort(), ['Авто · Запчасти · A', 'Запчасти · Кузов · C']);
assert.strictEqual(document.getElementById('recommendationsList').hidden, true);
assert.strictEqual(document.getElementById('recommendationScopeNotice').hidden, false);

// Contact filter and sort apply together; zero-contact listings are excluded.
contacts.value = 'yes';
contacts.dispatchEvent(new Event('change'));
sort.value = 'contacts';
sort.dispatchEvent(new Event('change'));
assert.deepStrictEqual(visibleNames(), ['C', 'A']);
assert.strictEqual(count.textContent, 'Показано объявлений: 2 из 3');

// Reset restores all rows, initial order, summaries and recommendation scope.
document.getElementById('resetFilters').click();
assert.deepStrictEqual(visibleNames(), ['A', 'B', 'C']);
assert.strictEqual(count.textContent, 'Показано объявлений: 3 из 3');
assert.strictEqual(document.getElementById('recommendationsList').hidden, false);
assert.strictEqual(document.getElementById('recommendationScopeNotice').hidden, true);
assert.strictEqual(document.querySelectorAll('#citySummaryTable tbody tr').length, 2);
console.log('Filter and sorting browser-DOM tests passed.');
