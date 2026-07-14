from __future__ import annotations

import json
from email.message import EmailMessage
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from portfolio_agent.research_digest import build_research_overlay, load_research_notes


class ResearchDigestTests(unittest.TestCase):
    def test_loads_exported_eml_without_publishing_raw_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            message = EmailMessage()
            message["Subject"] = "Lance Roberts: breadth warning"
            message["From"] = "newsletter@realinvestmentadvice.com"
            message["Date"] = "Mon, 13 Jul 2026 12:00:00 +0000"
            message.set_content("Market breadth is weakening. Consider a risk hedge. https://example.com/post")
            path = Path(tmp) / "lance.eml"
            path.write_bytes(message.as_bytes())

            notes = load_research_notes(Path(tmp), tickers=["SPY"])

            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0].source, "newsletter@realinvestmentadvice.com")
            self.assertEqual(notes[0].stance_label, "risk_off")
            self.assertEqual(notes[0].url, "https://example.com/post")

    def test_load_research_notes_scores_risk_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lance.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "title": "Market is overbought and a sell signal is near",
                            "source": "Lance Roberts / RIA",
                            "published": "2026-07-14T12:00:00Z",
                            "summary": "Technical divergence suggests investors should trim risk and keep cash ready.",
                        }
                    ]
                )
            )

            notes = load_research_notes(Path(tmp), tickers=["SPY", "NVDA"])

        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].source, "Lance Roberts / RIA")
        self.assertEqual(notes[0].stance_label, "risk_off")
        self.assertIn("technical trend", notes[0].themes)
        self.assertIn("risk management", notes[0].themes)

    def test_overlay_is_not_configured_without_directory(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            overlay = build_research_overlay("us", ["SPY"])

        self.assertEqual(overlay["status"], "not_configured")
        self.assertEqual(overlay["note_count"], 0)


if __name__ == "__main__":
    unittest.main()
