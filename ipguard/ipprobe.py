"""External IP probing: multi-source failover, inherits the system proxy.

requests has trust_env enabled by default, so it picks up the system proxy
(macOS System Settings proxy / Windows IE proxy / HTTP_PROXY env vars):
- proxy tool in "system proxy" mode -> the probe returns the proxy's egress IP;
- TUN/enhanced mode -> traffic goes out directly, still correct;
- SOCKS5 proxies need PySocks (included in requirements.txt).
"""
from __future__ import annotations

import logging

import requests

from .config import RequestConfig
from .models import is_valid_ip

log = logging.getLogger(__name__)

# Ordered by reliability/accessibility; tried in sequence until a valid IP comes back.
IP_SOURCES = [
    "https://api.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://api.ip.sb/ip",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
]


class IpProbe:
    def __init__(self, req_cfg: RequestConfig):
        self._timeout = req_cfg.timeout
        self._session = requests.Session()
        self._session.headers["User-Agent"] = req_cfg.user_agent

    def current_ip(self) -> str | None:
        """Return the current external (post-proxy) IP; None if all sources fail."""
        for url in IP_SOURCES:
            try:
                r = self._session.get(url, timeout=self._timeout)
                ip = r.text.strip()
                if is_valid_ip(ip):
                    return ip
                log.debug("Probe source returned unexpected content %s: %r", url, r.text[:80])
            except requests.RequestException as e:
                log.debug("Probe source failed %s: %s", url, e)
        return None
