import tempfile
import unittest
from pathlib import Path

from chat_analytics.store import ChatStore


class ChatStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ChatStore(str(Path(self.tmp.name) / "test.sqlite3"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_upserts_chat_and_counts_messages(self):
        self.assertTrue(self.store.save_chat("42", {"id": "chat-1", "item_id": 123}))
        self.assertTrue(self.store.save_chat("42", {"id": "chat-1", "item_id": 456}))
        self.assertTrue(self.store.save_message("42", "chat-1", {"id": "m-1", "created": "2026-11-05T10:00:00Z"}))
        self.assertFalse(self.store.save_message("42", "chat-1", {"id": "m-1", "created": "2026-11-05T10:00:00Z"}))
        status = self.store.status("42")
        self.assertEqual(status["chats"], 1)
        self.assertEqual(status["messages"], 1)
        self.assertEqual(self.store.recent_chats("42")[0]["item_id"], "456")

    def test_accounts_are_isolated(self):
        self.store.save_chat("42", {"id": "same"})
        self.store.save_chat("43", {"id": "same"})
        self.assertEqual(self.store.status("42")["chats"], 1)
        self.assertEqual(self.store.status("43")["chats"], 1)


if __name__ == "__main__":
    unittest.main()
