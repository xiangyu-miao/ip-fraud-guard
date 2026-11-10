"""Unit tests for core logic: parser / risk bands / IP validation / cache / i18n.

Run: python -m unittest discover -s tests -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ipguard import i18n
from ipguard.config import RequestConfig
from ipguard.models import IpReport, RiskLevel, is_valid_ip, level_for, utcnow
from ipguard.scamalytics import ScamalyticsScraper, parse_html

SAMPLE = (Path(__file__).parent / "samples" / "scamalytics_sample.html").read_text("utf-8")


class TestParseHtml(unittest.TestCase):
    def test_sample_fields(self):
        f = parse_html(SAMPLE)
        self.assertEqual(f["score"], 37)
        self.assertEqual(f["risk_text"], "high")
        rows = f["rows"]
        self.assertEqual(rows["isp name"], "M247 Europe SRL")
        self.assertEqual(rows["hostname"], "route-1.2.3.4.m247.com")
        self.assertEqual(rows["asn"], "9009")
        self.assertEqual(rows["country name"], "Netherlands")
        self.assertNotIn("connection type", rows)  # "n/a" values are filtered
        flags = f["flags"]
        self.assertIs(flags.get("datacenter"), True)
        self.assertIs(flags.get("anonymizing vpn"), False)
        self.assertIs(flags.get("server"), True)

    def test_score_from_embedded_json_only(self):
        # Falls back to the embedded JSON when the explicit text is missing.
        html = '<html><body><pre>"ip":"9.9.9.9", "score":"42", "risk":"high"</pre></body></html>'
        f = parse_html(html)
        self.assertEqual(f["score"], 42)

    def test_score_missing(self):
        f = parse_html("<html><body>nothing useful here</body></html>")
        self.assertIsNone(f.get("score"))

    def test_score_out_of_range_ignored(self):
        f = parse_html("<div>Fraud Score: 999</div>")
        self.assertIsNone(f.get("score"))


class TestRiskLevel(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(level_for(0), RiskLevel.LOW)
        self.assertEqual(level_for(15), RiskLevel.LOW)
        self.assertEqual(level_for(16), RiskLevel.MEDIUM)
        self.assertEqual(level_for(30), RiskLevel.MEDIUM)
        self.assertEqual(level_for(31), RiskLevel.HIGH)
        self.assertEqual(level_for(100), RiskLevel.HIGH)
        self.assertEqual(level_for(None), RiskLevel.UNKNOWN)

    def test_danger(self):
        self.assertTrue(IpReport(ip="1.2.3.4", score=21).is_danger(20))
        self.assertFalse(IpReport(ip="1.2.3.4", score=20).is_danger(20))
        self.assertFalse(IpReport(ip="1.2.3.4", score=None).is_danger(20))


class TestValidIp(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(is_valid_ip("8.8.8.8"))
        self.assertTrue(is_valid_ip(" 1.2.3.4 "))
        self.assertTrue(is_valid_ip("2606:4700::1111"))
        self.assertFalse(is_valid_ip("999.1.1.1"))
        self.assertFalse(is_valid_ip("not-an-ip"))


class TestCache(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            scraper = ScamalyticsScraper(Path(td), RequestConfig(), cache_ttl=1800)
            rep = IpReport(ip="1.2.3.4", score=12, isp="Test ISP", fetched_at=utcnow(), source="scamalytics")
            scraper._write_cache(rep)
            got = scraper.get_cached("1.2.3.4")
            self.assertIsNotNone(got)
            self.assertEqual(got.score, 12)
            self.assertEqual(got.isp, "Test ISP")
            self.assertEqual(got.ip, "1.2.3.4")
            self.assertIsNone(scraper.get_cached("5.6.7.8"))

    def test_corrupt_cache_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            scraper = ScamalyticsScraper(Path(td), RequestConfig())
            (Path(td) / "1.2.3.4.json").write_text("{not json")
            self.assertIsNone(scraper.get_cached("1.2.3.4"))


class TestI18n(unittest.TestCase):
    def test_languages(self):
        i18n.set_language("en")
        self.assertEqual(i18n.tr("risk.low"), "Low risk")
        i18n.set_language("zh")
        self.assertEqual(i18n.tr("risk.low"), "低风险")
        self.assertEqual(i18n.tr("widget.ip", ip="1.2.3.4"), "IP: 1.2.3.4")

    def test_unknown_falls_back_to_english(self):
        i18n.set_language("xx")
        self.assertEqual(i18n.current_language(), "en")
        self.assertEqual(i18n.tr("risk.high"), "High risk")
        i18n.set_language("system")  # restore


if __name__ == "__main__":
    unittest.main()
