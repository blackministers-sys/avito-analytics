"""Protected JSON API for running one-click Messenger sync and reports."""
import hmac
import os

from flask import Blueprint, jsonify, request
from hashlib import sha256

from .store import ChatStore

from .avito_client import AvitoAPIError
from .report import build_period_report
from .sync_service import sync_account, _parse_bound

chat_api = Blueprint("chat_api", __name__)


def authorized(value):
    expected = os.getenv("CHAT_ANALYZER_ACCESS_KEY", "")
    return bool(expected and value and hmac.compare_digest(expected, value))


@chat_api.post("/api/chat-analyzer/sync")
def run_chat_sync():
    if not authorized(request.headers.get("X-Chat-Analyzer-Key")):
        return jsonify({"error": "Доступ не настроен или ключ неверный."}), 401
    body = request.get_json(silent=True) or {}
    date_from = body.get("date_from")
    date_to = body.get("date_to")
    if not date_from or not date_to:
        return jsonify({"error": "Укажи начало и окончание периода."}), 400
    try:
        sync = sync_account(date_from=date_from, date_to=date_to)
        report = build_period_report(sync["account_id"], date_from, date_to)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except AvitoAPIError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        return jsonify({"error": "Ошибка выгрузки. Проверь настройки сервера и журнал приложения."}), 500
    return jsonify({"sync": sync, "report": report})


@chat_api.get("/chat-analyzer")
def chat_analyzer_home():
    from flask import render_template_string
    page = """<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Avito Chat Analyzer</title><style>
    body{font:16px system-ui;background:#f4f8f5;color:#17241d;margin:0;padding:24px}
    main{max-width:760px;margin:24px auto;background:white;border:1px solid #dce7df;border-radius:18px;padding:24px}
    h1{margin-top:0}label{display:block;font-size:13px;font-weight:700;margin:12px 0}
    input{display:block;box-sizing:border-box;width:100%;padding:12px;border:1px solid #d6e0d9;border-radius:9px;margin-top:5px;font:inherit}
    button{background:#37684f;color:white;border:0;border-radius:10px;padding:14px 18px;font-weight:700;cursor:pointer}
    button:disabled{opacity:.5}#status{white-space:pre-wrap;color:#53675b;margin:16px 0}
    .metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.metric{background:#eef5f0;padding:12px;border-radius:10px}
    .metric b{display:block;font-size:24px}@media(max-width:600px){.metrics{grid-template-columns:repeat(2,1fr)}}
    </style><main><h1>Avito Chat Analyzer</h1><p>Выбери период и получи аналитику переписок.</p>
    <label>Ключ доступа<input id="key" type="password" autocomplete="off"></label>
    <label>Период с<input id="from" type="date"></label><label>по<input id="to" type="date"></label>
    <button id="run">Выгрузить чаты и построить отчёт</button><div id="status">Выгрузка выполняется сервером через официальный Messenger API, если для аккаунта есть доступ.</div><div id="out"></div>
    <script>
    document.getElementById("run").onclick=async()=>{
      const key=document.getElementById("key").value.trim(),from=document.getElementById("from").value,to=document.getElementById("to").value;
      const status=document.getElementById("status"),out=document.getElementById("out"),button=document.getElementById("run");
      if(!key||!from||!to){status.textContent="Заполни ключ доступа и период.";return;}
      if(from>to){status.textContent="Начало периода позже окончания.";return;}
      button.disabled=true;out.replaceChildren();status.textContent="Загружаю историю чатов. При большом количестве диалогов это может занять несколько минут.";
      try{
        const res=await fetch("/api/chat-analyzer/sync",{method:"POST",headers:{"Content-Type":"application/json","X-Chat-Analyzer-Key":key},body:JSON.stringify({date_from:from,date_to:to})});
        const data=await res.json();if(!res.ok)throw new Error(data.error||"Ошибка выгрузки.");
        const s=data.report.summary,grid=document.createElement("div");grid.className="metrics";
        const vals=[["Диалоги",s.conversations_with_messages],["Сообщения",s.messages_in_period],["Клиенты",s.customer_messages],["Ответы продавца",s.seller_messages],["Ждут ответа",s.conversations_awaiting_seller_reply],["Неизвестный автор",s.unknown_sender_messages]];
        for(const [name,val] of vals){const d=document.createElement("div");d.className="metric";const b=document.createElement("b");b.textContent=val;const span=document.createElement("span");span.textContent=name;d.append(b,span);grid.append(d);}
        out.append(grid);const topics=document.createElement("pre");topics.textContent=JSON.stringify(s.topics,null,2);out.append(topics);
        status.textContent="Готово. Чатов: "+data.sync.chats_received+"; сообщений загружено: "+data.sync.messages_fetched+"; ошибок отдельных чатов: "+data.sync.failed_chats_count+"; статус: "+data.sync.sync_status+".";
      }catch(e){status.textContent=e.message;}finally{button.disabled=false;}
    };
    </script></main></html>"""
    return render_template_string(page)


@chat_api.post("/api/chat-analyzer/import")
def import_browser_chats():
    """Accept an explicit user-initiated export from the Avito browser extension."""
    if not authorized(request.headers.get("X-Chat-Analyzer-Key")):
        return jsonify({"error": "Доступ не настроен или ключ неверный."}), 401
    if request.content_length and request.content_length > 20 * 1024 * 1024:
        return jsonify({"error": "Размер выгрузки превышает 20 МБ."}), 413
    body = request.get_json(silent=True) or {}
    account_id = str(body.get("account_id") or "").strip()
    date_from, date_to = body.get("date_from"), body.get("date_to")
    conversations = body.get("conversations")
    if not account_id or len(account_id) > 100:
        return jsonify({"error": "Не указан корректный ID аккаунта."}), 400
    if not date_from or not date_to:
        return jsonify({"error": "Укажи начало и окончание периода."}), 400
    try:
        start = _parse_bound(date_from)
        end_exclusive = _parse_bound(date_to, end=True)
        if start is None or end_exclusive is None or start >= end_exclusive:
            raise ValueError("Укажи корректный период: дата начала не позже даты окончания.")
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    if not isinstance(conversations, list) or len(conversations) > 1000:
        return jsonify({"error": "Некорректный список диалогов или превышен лимит 1000 диалогов."}), 400
    store = ChatStore()
    chats_saved = messages_saved = messages_received = 0
    failed = []
    for chat in conversations:
        if not isinstance(chat, dict):
            continue
        chat_id = str(chat.get("id") or "").strip()
        if not chat_id or len(chat_id) > 500:
            failed.append({"chat_id": None, "error": "Диалог без корректного идентификатора."})
            continue
        store.save_chat(account_id, {
            "id": chat_id,
            "title": str(chat.get("title") or "")[:500],
            "source": "visible_ui",
        })
        chats_saved += 1
        messages = chat.get("messages") if isinstance(chat.get("messages"), list) else []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            messages_received += 1
            if messages_received > 100000:
                return jsonify({"error": "Превышен лимит 100000 сообщений. Разбей выгрузку на части."}), 413
            text = str(message.get("text") or "").strip()
            created = message.get("created")
            sender = message.get("sender_type")
            if sender not in ("customer", "seller", "unknown"):
                sender = "unknown"
            message_id = str(message.get("id") or "").strip()
            if not message_id:
                digest = sha256(f"{chat_id}|{created}|{sender}|{text}|{index}".encode("utf-8")).hexdigest()
                message_id = "ui:" + digest
            normalized = {
                "id": message_id[:255],
                "created": created if isinstance(created, (str, int, float)) else "",
                "text": text[:10000],
                "sender_type": sender,
                "source": "visible_ui",
            }
            if store.save_message(account_id, chat_id, normalized):
                messages_saved += 1
    collection = body.get("collection") if isinstance(body.get("collection"), dict) else {}
    raw_failures = body.get("failures") if isinstance(body.get("failures"), list) else []
    for item in raw_failures[:100]:
        if isinstance(item, dict):
            failed.append({
                "chat_id": str(item.get("chat_id") or "")[:500] or None,
                "error": str(item.get("error") or "Ошибка сбора")[:240],
            })
        else:
            failed.append({"chat_id": None, "error": str(item)[:240]})
    status = "partial" if failed else "ok"
    store.record_sync(account_id, chats_saved, messages_saved, status)
    report = build_period_report(account_id, str(date_from), str(date_to), store=store)
    return jsonify({
        "import": {
            "account_id": account_id,
            "chats_received": len(conversations),
            "chats_saved": chats_saved,
            "messages_received": messages_received,
            "new_messages_saved": messages_saved,
            "failed_chats_count": len(failed),
            "failed_chats": failed[:50],
            "sync_status": status,
            "collection": collection,
        },
        "report": report,
    }), 200
