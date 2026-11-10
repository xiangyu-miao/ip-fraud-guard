"""Scamalytics page scraping and parsing.

Design notes:
- Cache-first: the same IP is not re-requested within the TTL. Scamalytics
  scores are not second-level data, so frequent refreshing is both pointless
  and impolite, and may trigger rate limiting. IP changes bypass the cache.
- Layered parsing (verified against the live page, 2026-11):
  1) explicit text ``Fraud Score: N``;
  2) fallback: the embedded "IP Fraud Risk API" JSON preview ``"score":"N"``;
  3) fields from <th>/<td> table rows; booleans from .risk yes/no divs.
- On network failure, the last cached report is returned (source=stale-cache).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .config import RequestConfig
from .models import IpReport, is_valid_ip, report_from_dict, report_to_dict, utcnow

log = logging.getLogger(__name__)

BASE_URL = "https://scamalytics.com/ip/{ip}"
_CACHE_VERSION = 1

_SCORE_FWD = re.compile(r"Fraud\s*Score\s*:\s*(\d{1,3})", re.I)
_SCORE_JSON = re.compile(r'"score"\s*:\s*"?(\d{1,3})"?', re.I)
_RISK_JSON = re.compile(r'"risk"\s*:\s*"(\w+)"', re.I)
_CF_MARKERS = ("just a moment", "cf-browser-verification", "cf-chl")


class ScamalyticsError(Exception):
    pass


class ParseError(ScamalyticsError):
    pass


def parse_html(html: str) -> dict:
    """Parse a Scamalytics IP page into a field dict. Best-effort on redesigns."""
    fields: dict = {}
    flat = re.sub(r"\s+", " ", html)

    m = _SCORE_FWD.search(flat) or _SCORE_JSON.search(flat)
    if m and 0 <= int(m.group(1)) <= 100:
        fields["score"] = int(m.group(1))
    m = _RISK_JSON.search(flat)
    if m:
        fields["risk_text"] = m.group(1).lower()

    rows: dict = {}
    flags: dict = {}
    soup = BeautifulSoup(html, "lxml")
    section: str | None = None
    for row in soup.find_all("tr"):
        ths = row.find_all("th", recursive=False)
        tds = row.find_all("td", recursive=False)
        # Section title rows (e.g. "Operator" / "Datacenter" / "Proxies"):
        # <th class="title ...">
        title = next((t for t in ths if "title" in (t.get("class") or [])), None)
        if title is not None:
            section = title.get_text(" ", strip=True).lower()
            continue
        # Boolean rows: the td contains <div class="risk yes/no">
        risk = row.find("div", class_="risk")
        if risk is not None:
            label = ths[0].get_text(" ", strip=True).lower() if ths else section or "unknown"
            flags[label] = risk.get_text(" ", strip=True).lower().startswith("yes")
            continue
        # Plain key/value rows
        if len(ths) == 1 and len(tds) >= 1:
            label = ths[0].get_text(" ", strip=True).lower()
            value = tds[0].get_text(" ", strip=True)
            if label and value and value.lower() not in ("n/a", "not available", "-"):
                rows[label] = value

    fields["rows"] = rows
    fields["flags"] = flags
    return fields


def _pick(rows: dict, *keys: str) -> str | None:
    for k in keys:
        v = rows.get(k)
        if v:
            return v
    return None


def report_from_fields(ip: str, fields: dict) -> IpReport:
    rows = fields.get("rows", {})
    flags = fields.get("flags", {})
    return IpReport(
        ip=ip,
        score=fields.get("score"),
        risk_text=fields.get("risk_text"),
        isp=_pick(rows, "isp name", "organization name", "isp"),
        hostname=_pick(rows, "hostname"),
        asn=_pick(rows, "asn"),
        country=_pick(rows, "country name", "country"),
        connection_type=_pick(rows, "connection type", "usage type"),
        is_datacenter=flags.get("datacenter"),
        flags=flags,
        fetched_at=utcnow(),
        source="scamalytics",
    )


class ScamalyticsScraper:
    """Scraper + on-disk cache (one JSON file per IP)."""

    def __init__(self, cache_dir: Path, req_cfg: RequestConfig, cache_ttl: int = 1800):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl
        self.timeout = req_cfg.timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": req_cfg.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _cache_path(self, ip: str) -> Path:
        return self.cache_dir / f"{ip}.json"

    def get_cached(self, ip: str) -> IpReport | None:
        try:
            data = json.loads(self._cache_path(ip).read_text("utf-8"))
            if data.get("version") != _CACHE_VERSION:
                return None
            return report_from_dict(data)
        except (OSError, ValueError):
            return None

    def _write_cache(self, report: IpReport) -> None:
        if not report.ip:
            return
        data = report_to_dict(report)
        data["version"] = _CACHE_VERSION
        tmp = self._cache_path(report.ip).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        os.replace(tmp, self._cache_path(report.ip))

    def fetch(self, ip: str | None, *, force: bool = False) -> IpReport:
        """Fetch the fraud score report for an IP.

        - within TTL and not forced: returns the cache (zero network requests);
        - on fetch failure: falls back to the last cached report
          (source=stale-cache, error explains why);
        - no cache and failure: returns an empty report carrying the error.
        """
        if not ip or not is_valid_ip(ip):
            return IpReport(ip=ip, error="Invalid or missing external IP")

        cached = self.get_cached(ip)
        age = None
        if cached and cached.fetched_at:
            age = (utcnow() - cached.fetched_at).total_seconds()
        if not force and cached and cached.score is not None and age is not None and 0 <= age < self.cache_ttl:
            cached.source = "cache"
            return cached

        last_err: Exception | None = None
        for attempt in (1, 2):
            try:
                r = self._session.get(BASE_URL.format(ip=ip), timeout=self.timeout)
                if any(m in r.text[:4000].lower() for m in _CF_MARKERS):
                    raise ParseError("Blocked by Cloudflare challenge")
                r.raise_for_status()
                fields = parse_html(r.text)
                if fields.get("score") is None:
                    raise ParseError("Fraud Score not found on page (site redesign?)")
                report = report_from_fields(ip, fields)
                self._write_cache(report)
                return report
            except (requests.RequestException, ParseError, ValueError) as e:
                last_err = e
                if attempt == 1:
                    time.sleep(1.5)

        if cached:
            cached.source = "stale-cache"
            cached.error = f"Refresh failed: {last_err} (showing last cache)"
            return cached
        report = IpReport(ip=ip)
        report.error = f"Scrape failed: {last_err}"
        return report
