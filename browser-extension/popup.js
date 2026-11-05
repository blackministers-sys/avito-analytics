const byId = (id) => document.getElementById(id);

async function activeAvitoTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url?.startsWith("https://www.avito.ru/")) {
    throw new Error("Открой Avito и нужный экран в активной вкладке.");
  }
  return tab;
}

byId("inspect").addEventListener("click", async () => {
  const button = byId("inspect");
  const status = byId("status");
  button.disabled = true;
  status.textContent = "Анализирую только структуру видимых элементов…";
  try {
    const tab = await activeAvitoTab();
    const injected = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const visible = (el) => {
          const r = el.getBoundingClientRect();
          const s = getComputedStyle(el);
          return r.width > 0 && r.height > 0 && s.display !== "none" &&
            s.visibility !== "hidden" && Number(s.opacity) !== 0;
        };
        const signature = (el) => {
          const classes = [...el.classList].slice(0, 5).map(x => x.slice(0, 80));
          return [el.tagName.toLowerCase(), ...classes.map(x => "." + x)].join("");
        };
        const all = [...document.querySelectorAll("body *")].filter(visible);
        const groups = new Map();
        for (const el of all) {
          const key = signature(el);
          if (!groups.has(key)) groups.set(key, { signature: key, count: 0, examples: [] });
          const group = groups.get(key);
          group.count += 1;
          if (group.examples.length < 3) {
            const r = el.getBoundingClientRect();
            group.examples.push({
              role_present: el.hasAttribute("role"),
              aria_label_present: el.hasAttribute("aria-label"),
              data_attribute_names: [...el.attributes].map(a => a.name).filter(n => n.startsWith("data-")).slice(0, 12),
              child_count: el.children.length,
              depth: (() => { let d=0,n=el; while(n.parentElement && d<20){d++;n=n.parentElement;} return d; })(),
              rect: { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) }
            });
          }
        }
        const ranked = [...groups.values()].sort((a,b)=>b.count-a.count).slice(0,80);
        return {
          page_kind_hint: location.pathname.toLowerCase().includes("messenger") ? "messenger_path" : "other_path",
          title_length: document.title.length,
          viewport: { width: innerWidth, height: innerHeight },
          visible_element_count: all.length,
          repeated_element_signatures: ranked,
          note: "Only visible DOM structure metadata. No message text, names, aria-label values, URLs, form values, cookies or network data were collected."
        };
      }
    });
    const structure = injected?.[0]?.result;
    if (!structure) throw new Error("Не удалось прочитать структуру страницы.");
    const payload = {
      schema: "avito-visible-dom-diagnostic",
      schema_version: "0.2.0",
      captured_at: new Date().toISOString(),
      screen: "visible_dom_structure",
      page_origin: "https://www.avito.ru",
      structure
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    await chrome.downloads.download({
      url,
      filename: `avito-dom-diagnostic-${new Date().toISOString().slice(0,10)}.json`,
      saveAs: true
    });
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    status.textContent = "Диагностика сохранена локально. Повтори её на втором экране.";
  } catch (error) {
    status.textContent = error?.message || "Не удалось снять диагностику.";
  } finally {
    button.disabled = false;
  }
});

byId("export").addEventListener("click", async () => {
  const button = byId("export");
  const status = byId("status");
  const account = byId("account").value.trim();
  const dateFrom = byId("dateFrom").value || null;
  const dateTo = byId("dateTo").value || null;

  if (!account) {
    status.textContent = "Укажи название аккаунта, чтобы не перепутать выгрузки.";
    byId("account").focus();
    return;
  }
  if (dateFrom && dateTo && dateFrom > dateTo) {
    status.textContent = "Дата начала периода не может быть позже даты окончания.";
    return;
  }

  button.disabled = true;
  status.textContent = "Читаю только выделенный тобой текст на текущей вкладке…";
  try {
    const tab = await activeAvitoTab();
    const injected = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        text: window.getSelection()?.toString().trim() || "",
        page_title: document.title,
        page_url: location.origin + location.pathname
      })
    });
    const captured = injected?.[0]?.result;
    if (!captured?.text) {
      throw new Error("Текст не выделен. Выдели сообщения в чате и повтори экспорт.");
    }

    const payload = {
      schema: "avito-chat-selection-export",
      schema_version: "0.1.0",
      exported_at: new Date().toISOString(),
      source: { type: "explicit_user_selection", page_title: captured.page_title, page_path: captured.page_url },
      account: { label: account },
      period: { from: dateFrom, to: dateTo },
      conversations: [{
        source_chat_ref: null,
        capture_method: "selected_visible_text",
        raw_text: captured.text,
        messages: []
      }],
      limitations: [
        "Экспорт содержит только текст, который пользователь явно выделил на странице.",
        "Сообщения не разделяются автоматически на отдельные записи и отправителей.",
        "Вложения, скрытая история и другие чаты не собираются."
      ]
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const objectUrl = URL.createObjectURL(blob);
    const safeDate = new Date().toISOString().slice(0, 10);
    await chrome.downloads.download({
      url: objectUrl,
      filename: `avito-chat-export-${safeDate}.json`,
      saveAs: true
    });
    setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
    status.textContent = "JSON сформирован и сохранён локально. На сервер ничего не отправлялось.";
  } catch (error) {
    status.textContent = error?.message || "Не удалось сформировать экспорт.";
  } finally {
    button.disabled = false;
  }
});
