"""Read-only Avito Business API client for Messenger data.

This module never sends messages, marks chats as read, or changes account state.
"""
from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote

import requests


class AvitoAPIError(RuntimeError):
    pass


class AvitoClient:
    BASE_URL = "https://api.avito.ru"
    PAGE_SIZE = 100

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 session: requests.Session | None = None):
        self.client_id = client_id or os.getenv("AVITO_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("AVITO_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise AvitoAPIError("Не заданы AVITO_CLIENT_ID и AVITO_CLIENT_SECRET.")
        self.session = session or requests.Session()
        self._token = ""
        self._token_expires_at = 0.0

    def _access_token(self, force: bool = False) -> str:
        if not force and self._token and time.time() < self._token_expires_at - 60:
            return self._token
        response = self.session.post(
            f"{self.BASE_URL}/token",
            data={"grant_type": "client_credentials", "client_id": self.client_id,
                  "client_secret": self.client_secret},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        if not response.ok:
            raise AvitoAPIError(f"Avito OAuth вернул HTTP {response.status_code}.")
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise AvitoAPIError("Avito OAuth не вернул access_token.")
        self._token = str(token)
        self._token_expires_at = time.time() + int(payload.get("expires_in", 86400))
        return self._token

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        for attempt in range(2):
            response = self.session.get(
                f"{self.BASE_URL}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self._access_token(force=attempt == 1)}"},
                timeout=30,
            )
            if response.status_code == 401 and attempt == 0:
                continue
            if response.status_code == 429:
                raise AvitoAPIError("Avito API ограничил частоту запросов (HTTP 429); повторите синхронизацию позже.")
            if not response.ok:
                raise AvitoAPIError(f"Avito API вернул HTTP {response.status_code} для {path}.")
            try:
                data = response.json()
            except ValueError as exc:
                raise AvitoAPIError("Avito API вернул некорректный JSON.") from exc
            if not isinstance(data, dict):
                raise AvitoAPIError("Неожиданный формат ответа Avito API.")
            return data
        raise AvitoAPIError("Не удалось обновить токен Avito.")

    def account(self) -> dict:
        return self._get("/core/v1/accounts/self")

    @staticmethod
    def _items(payload: dict, key: str) -> list[dict]:
        value = payload.get(key)
        if value is None and isinstance(payload.get("result"), dict):
            value = payload["result"].get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        return []

    def list_chats(self, user_id: int, max_pages: int = 11) -> list[dict]:
        chats: list[dict] = []
        for page in range(max_pages):
            offset = page * self.PAGE_SIZE
            payload = self._get(
                f"/messenger/v2/accounts/{int(user_id)}/chats",
                {"limit": self.PAGE_SIZE, "offset": offset, "chat_types": ["u2i"]},
            )
            batch = self._items(payload, "chats")
            if not batch:
                break
            chats.extend(batch)
            if len(batch) < self.PAGE_SIZE:
                break
        else:
            raise AvitoAPIError("Достигнут безопасный предел загрузки чатов (1100). Нужна следующая порция синхронизации.")
        return chats

    def list_messages(self, user_id: int, chat_id: str, max_pages: int = 11) -> list[dict]:
        messages: list[dict] = []
        safe_chat_id = quote(str(chat_id), safe="")
        for page in range(max_pages):
            offset = page * self.PAGE_SIZE
            payload = self._get(
                f"/messenger/v3/accounts/{int(user_id)}/chats/{safe_chat_id}/messages/",
                {"limit": self.PAGE_SIZE, "offset": offset},
            )
            batch = self._items(payload, "messages")
            if not batch:
                break
            messages.extend(batch)
            if len(batch) < self.PAGE_SIZE:
                break
        else:
            raise AvitoAPIError(f"Достигнут безопасный предел истории для чата {chat_id}.")
        return messages
