import unittest
import pandas as pd
from chat_analytics.analyzer import analyze_conversations, classify_text, normalize_messages

class ChatAnalyticsTests(unittest.TestCase):
    def test_price_topic(self):
        self.assertIn("Цена / дорого", classify_text("Для меня дорого, скидка есть?"))

    def test_silence_is_not_refusal(self):
        frame = pd.DataFrame([
            {"conversation_id":"1","text":"Здравствуйте, товар актуален?","sender":"Покупатель"},
            {"conversation_id":"1","text":"Да, в наличии","sender":"Продавец"},
        ])
        result, _ = analyze_conversations(frame)
        self.assertEqual(result.iloc[0]["status_signal"], "Последнее сообщение продавца — исход неизвестен")

    def test_normalize(self):
        raw = pd.DataFrame({"Чат":["10"],"Сообщение":["Добрый день"]})
        normalized = normalize_messages(raw, {"conversation_id":"Чат","text":"Сообщение"})
        self.assertEqual(len(normalized), 1)

    def test_ad_title(self):
        raw = pd.DataFrame({"Чат":["10"],"Сообщение":["Есть в наличии?"],"Объявление":["Серебряная цепь"]})
        normalized = normalize_messages(raw, {"conversation_id":"Чат","text":"Сообщение","ad_title":"Объявление"})
        result, _ = analyze_conversations(normalized)
        self.assertEqual(result.iloc[0]["ad_title"], "Серебряная цепь")

if __name__ == "__main__":
    unittest.main()
