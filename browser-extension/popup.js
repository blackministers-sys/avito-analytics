const byId = (id) => document.getElementById(id);

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
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url?.startsWith("https://www.avito.ru/")) {
      throw new Error("Открой Avito и нужный чат в активной вкладке.");
    }
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
      source: {
        type: "explicit_user_selection",
        page_title: captured.page_title,
        page_path: captured.page_url
      },
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