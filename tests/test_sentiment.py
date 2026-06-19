import unittest
from unittest.mock import patch

from portfolio_agent.sentiment import _ai_layer_status, _match_ticker, score_text, themes_for_text


class SentimentTests(unittest.TestCase):
    def test_single_letter_ticker_does_not_match_inside_words(self):
        title = "Stock Market Today: Nasdaq Jumps, Oil Is Now Close to Pre-Iran War Prices — Live Updates"
        self.assertEqual(_match_ticker(title, ["SPY", "V"], fallback="MARKET"), "MARKET")

    def test_sentiment_scoring_and_themes(self):
        score, label, terms = score_text("Nvidia shares rally as AI demand and earnings beat expectations")
        self.assertGreater(score, 0)
        self.assertEqual(label, "positive")
        self.assertIn("beat", terms)
        self.assertIn("AI / semiconductors", themes_for_text("AI chip demand drives earnings growth"))

    def test_llm_enabled_without_model_falls_back_cleanly(self):
        class Config:
            class Universe:
                benchmark = "SPY"

            universe = Universe()

        with patch.dict("os.environ", {"LLM_SENTIMENT_ENABLED": "true"}, clear=True):
            layer = _ai_layer_status([], {"investment_posture": "balanced", "overall_score": 0.0}, Config())
        self.assertEqual(layer["status"], "llm_not_configured")
        self.assertEqual(layer["provider"], "ollama")


if __name__ == "__main__":
    unittest.main()
