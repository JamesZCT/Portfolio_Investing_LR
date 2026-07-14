from __future__ import annotations

import unittest

from portfolio_agent.information_signs import _commentary_signal, _parse_rss_items, build_information_signs_payload


class InformationSignsTests(unittest.TestCase):
    def test_rss_parser_filters_for_lance_roberts(self) -> None:
        raw = b"""<?xml version='1.0'?>
        <rss xmlns:dc='http://purl.org/dc/elements/1.1/'><channel>
          <item><title>Market Risk Warning</title><dc:creator>Lance Roberts</dc:creator>
            <pubDate>Mon, 13 Jul 2026 12:00:00 +0000</pubDate><link>https://example.com/lance</link>
            <description><![CDATA[<p>Breadth is weakening.</p>]]></description></item>
          <item><title>Other Author</title><dc:creator>Someone Else</dc:creator><link>https://example.com/other</link></item>
        </channel></rss>"""
        rows = _parse_rss_items(raw, author_filter="lance roberts")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Market Risk Warning")
        self.assertEqual(rows[0]["summary"], "Breadth is weakening.")

    def test_commentary_classification_is_informational(self) -> None:
        self.assertEqual(_commentary_signal("Margin debt risk warning", "overbought market"), "cautionary")
        payload = build_information_signs_payload("us", mode="sandbox")
        self.assertEqual(payload["decision_policy"]["portfolio_weight"], 0.0)
        self.assertEqual(payload["primary_signs"][0]["decision_use"], "information_only")


if __name__ == "__main__":
    unittest.main()
