import unittest

from chat_analytics.sync_service import sync_account


class FakeClient:
    def account(self):
        return {"id": 77}

    def list_chats(self, user_id):
        assert user_id == 77
        return [{"id": "c1", "item_id": 101}, {"id": "c2", "item_id": 202}]

    def list_messages(self, user_id, chat_id):
        return [{"id": f"{chat_id}-m1", "created": "2026-11-05T10:00:00Z"}]


class FakeStore:
    def __init__(self):
        self.chats = []
        self.messages = []
        self.state = None

    def save_chat(self, account_id, chat):
        self.chats.append((account_id, chat))
        return True

    def save_message(self, account_id, chat_id, message):
        self.messages.append((account_id, chat_id, message))
        return True

    def record_sync(self, account_id, chats_count, messages_count, status):
        self.state = (account_id, chats_count, messages_count, status)

    def status(self, account_id):
        return {"chats": 2, "messages": 2, "status": "ok"}


class SyncServiceTests(unittest.TestCase):
    def test_imports_chats_and_messages_read_only(self):
        store = FakeStore()
        result = sync_account(FakeClient(), store)
        self.assertEqual(result["account_id"], "77")
        self.assertEqual(result["chats_received"], 2)
        self.assertEqual(result["new_messages_saved"], 2)
        self.assertEqual(len(store.messages), 2)
        self.assertEqual(store.state, ("77", 2, 2, "ok"))


if __name__ == "__main__":
    unittest.main()
