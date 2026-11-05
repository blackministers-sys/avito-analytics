"""Orchestrate an initial read-only import of Avito Messenger history."""
from __future__ import annotations

from .avito_client import AvitoClient
from .store import ChatStore


def sync_account(client: AvitoClient | None = None, store: ChatStore | None = None) -> dict:
    client = client or AvitoClient()
    store = store or ChatStore()
    account = client.account()
    user_id = account.get("id") or account.get("user_id")
    if user_id is None:
        raise RuntimeError("Avito не вернул ID аккаунта в /core/v1/accounts/self.")
    account_id = str(user_id)
    chats = client.list_chats(int(user_id))
    saved_messages = 0
    saved_chats = 0
    for chat in chats:
        if store.save_chat(account_id, chat):
            saved_chats += 1
        chat_id = chat.get("id") or chat.get("chat_id")
        if chat_id is None:
            continue
        for message in client.list_messages(int(user_id), str(chat_id)):
            if store.save_message(account_id, str(chat_id), message):
                saved_messages += 1
    store.record_sync(account_id, len(chats), saved_messages, "ok")
    return {
        "account_id": account_id,
        "chats_received": len(chats),
        "chats_saved_or_updated": saved_chats,
        "new_messages_saved": saved_messages,
        "status": store.status(account_id),
    }
