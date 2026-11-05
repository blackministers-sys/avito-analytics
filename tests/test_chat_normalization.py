import unittest

from chat_analytics.normalization import (
    MessageNormalizationError,
    normalize_message,
)


class NormalizeMessageTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {
            "message_id": "id",
            "text": "content.text",
            "timestamp": "created_at",
            "sender": "direction",
            "attachments": "content.attachments",
        }

    def test_normalizes_known_sender_and_utc_timestamp(self):
        result = normalize_message(
            {
                "id": "m-1",
                "created_at": "2026-10-01T12:30:00+03:00",
                "direction": "buyer",
                "content": {"text": "Здравствуйте", "attachments": [{"type": "image", "id": "a1"}]},
            },
            account_id="internal-1",
            conversation_id="chat-1",
            source_type="official_api",
            field_map=self.mapping,
        )
        self.assertEqual(result["sender_type"], "customer")
        self.assertEqual(result["timestamp"], "2026-10-01T09:30:00+00:00")
        self.assertEqual(result["text"], "Здравствуйте")
        self.assertEqual(result["attachments"][0]["source_id"], "a1")
        self.assertEqual(result["account_id"], "internal-1")

    def test_unknown_sender_is_not_guessed(self):
        result = normalize_message(
            {"id": "m-2", "content": {"text": "Добрый день"}, "direction": "other"},
            account_id="a",
            conversation_id="c",
            source_type="browser_import",
            field_map=self.mapping,
        )
        self.assertEqual(result["sender_type"], "unknown")
        self.assertIsNone(result["timestamp"])

    def test_requires_message_id_and_text(self):
        with self.assertRaises(MessageNormalizationError):
            normalize_message(
                {"content": {"text": "x"}},
                account_id="a",
                conversation_id="c",
                source_type="test",
                field_map=self.mapping,
            )

    def test_rejects_ambiguous_numeric_timestamp(self):
        with self.assertRaises(MessageNormalizationError):
            normalize_message(
                {"id": "m", "content": {"text": "x"}, "created_at": 1790841600},
                account_id="a",
                conversation_id="c",
                source_type="test",
                field_map=self.mapping,
            )


if __name__ == "__main__":
    unittest.main()
