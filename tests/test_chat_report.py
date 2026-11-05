import unittest

from chat_analytics.report import build_period_report


class FakeStore:
    def __init__(self, messages=None):
        self.messages = messages or [
            {"chat_id": "chat-1", "message": {
                "id": "m1", "created": 1790841600, "author_id": 55,
                "content": {"text": "Здравствуйте, есть в наличии?"}
            }},
            {"chat_id": "chat-1", "message": {
                "id": "m2", "created": 1790841660, "author_id": 100,
                "content": {"text": "Да, есть в наличии"}
            }},
            {"chat_id": "chat-2", "message": {
                "id": "m3", "created": 1790841720,
                "content": {"text": "Дорого"}
            }},
        ]

    def messages_for_period(self, account_id, date_from=None, date_to_exclusive=None):
        return self.messages


class PeriodReportTests(unittest.TestCase):
    def test_counts_messages_and_does_not_guess_unknown_sender(self):
        report = build_period_report(
            "100", "2026-10-01", "2026-10-31", store=FakeStore()
        )
        summary = report["summary"]
        self.assertEqual(summary["conversations_with_messages"], 2)
        self.assertEqual(summary["customer_messages"], 1)
        self.assertEqual(summary["seller_messages"], 1)
        self.assertEqual(summary["unknown_sender_messages"], 1)
        self.assertEqual(summary["conversations_awaiting_seller_reply"], 1)

    def test_response_time_only_when_author_and_time_are_known(self):
        report = build_period_report(
            "100", "2026-10-01", "2026-10-31", store=FakeStore()
        )
        self.assertEqual(report["summary"]["response_time_sample_size"], 1)
        self.assertEqual(report["summary"]["average_first_response_minutes"], 1.0)

    def test_explicit_browser_sender_roles_are_respected(self):
        store = FakeStore([
            {"chat_id": "browser-chat", "message": {
                "id": "b1", "created": 1790841600, "sender_type": "customer",
                "text": "Есть в наличии?"
            }},
            {"chat_id": "browser-chat", "message": {
                "id": "b2", "created": 1790841660, "sender_type": "seller",
                "text": "Да, есть"
            }},
            {"chat_id": "browser-chat", "message": {
                "id": "b3", "created": 1790841720, "sender_type": "unknown",
                "text": "Неизвестный автор"
            }},
        ])
        report = build_period_report(
            "internal-account", "2026-10-01", "2026-10-31", store=store
        )
        summary = report["summary"]
        self.assertEqual(summary["customer_messages"], 1)
        self.assertEqual(summary["seller_messages"], 1)
        self.assertEqual(summary["unknown_sender_messages"], 1)

    def test_rejects_invalid_period(self):
        with self.assertRaises(ValueError):
            build_period_report("100", "2026-10-31", "2026-10-01", store=FakeStore())


if __name__ == "__main__":
    unittest.main()
