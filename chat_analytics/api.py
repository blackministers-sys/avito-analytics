"""Protected JSON API for running one-click Messenger sync and reports."""
import hmac
import os

from flask import Blueprint, jsonify, request

from .avito_client import AvitoAPIError
from .report import build_period_report
from .sync_service import sync_account

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
