"""Local HTTP gate service (loopback only) for userscripts / CLI / scripts.

Endpoints:
    GET /status   current fraud score state (see build_status)
    GET /health   health check
Fail-closed: when the state is unknown, allowed=false, so the gate never
lets a high-risk session through by accident.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .config import Config
from .i18n import english
from .models import LEVEL_META, level_for

log = logging.getLogger(__name__)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def build_status(report, cfg: Config) -> dict:
    threshold = cfg.gate_threshold
    if report is None:
        allowed, reason, score, ip = False, "no_data", None, None
    elif report.score is None:
        allowed, reason, score, ip = False, "unknown_score", None, report.ip
    elif report.score > threshold:
        allowed, reason, score, ip = False, "score_exceeds_threshold", report.score, report.ip
    else:
        allowed, reason, score, ip = True, None, report.score, report.ip
    level = level_for(score, cfg.low_max, cfg.medium_max)
    return {
        "ok": True,
        "app": "ipguard",
        "version": __version__,
        "allowed": allowed,
        "blocked_reason": reason,
        "ip": ip,
        "score": score,
        "threshold": threshold,
        "risk": LEVEL_META[level].key,
        # Stable English label: this is a machine-facing API.
        "risk_label": english(LEVEL_META[level].label),
        "source": getattr(report, "source", None),
        "fetched_at": report.fetched_at.isoformat() if report and report.fetched_at else None,
    }


class GateServer:
    """Minimal JSON API server. `state_holder` must provide `.lock` and `.report`."""

    def __init__(self, host: str, port: int, token: str, state_holder, cfg: Config):
        holder, config = state_holder, cfg
        expected_token = token

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # keep the log quiet
                pass

            def _send(self, code: int, payload: dict) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "X-Gate-Token, Content-Type")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self) -> bool:
                if not expected_token:
                    return True
                q = parse_qs(urlparse(self.path).query)
                if q.get("token", [None])[0] == expected_token:
                    return True
                return self.headers.get("X-Gate-Token") == expected_token

            def do_OPTIONS(self) -> None:  # noqa: N802
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "X-Gate-Token, Content-Type")
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._send(401, {"ok": False, "error": "invalid_token"})
                    return
                path = urlparse(self.path).path
                if path in ("/health", "/healthz"):
                    self._send(200, {"ok": True})
                elif path == "/status":
                    with holder.lock:
                        report = holder.report
                    self._send(200, build_status(report, config))
                else:
                    self._send(404, {"ok": False, "error": "not_found"})

        self._httpd = _Server((host, port), Handler)

    def start(self) -> None:
        threading.Thread(target=self._httpd.serve_forever, name="ipguard-gate", daemon=True).start()
        log.info("Gate service started: http://%s:%s/status", *self._httpd.server_address[:2])

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
