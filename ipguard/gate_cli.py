"""Command-line gate: python -m ipguard.gate_cli / scripts/ipguard-gate.

Exit codes:
    0 = allowed (score <= threshold)
    1 = blocked (score > threshold)
    2 = unknown / error (fail-closed, verify manually)

Example (macOS/Linux):
    ipguard-gate && open -a "Safari" "https://claude.ai" || echo "blocked"

Implementation: queries the running IPGuard gate service first (instant);
if it is not running, probes the IP and scrapes independently, reusing the
same on-disk cache (no duplicate Scamalytics requests).
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

from .config import Config
from .i18n import set_language, tr
from .ipprobe import IpProbe
from .models import LEVEL_META, level_for
from .scamalytics import ScamalyticsScraper


def _query_running_app(cfg: Config) -> tuple[int | None, str | None]:
    """Ask the running IPGuard gate service; returns (score, ip) or (None, None)."""
    url = f"http://{cfg.gate_server.host}:{cfg.gate_server.port}/status"
    headers = {"X-Gate-Token": cfg.gate_server.token} if cfg.gate_server.token else {}
    try:
        r = requests.get(url, headers=headers, timeout=1.5)
        if r.status_code == 200:
            d = r.json()
            score = d.get("score")
            if score is not None:
                return score, d.get("ip")
    except (requests.RequestException, ValueError):
        pass
    return None, None


def run_check(cfg: Config, max_score: int | None = None, as_json: bool = False) -> int:
    """Run one gate check, print the result and return the exit code."""
    set_language(cfg.language)
    threshold = cfg.gate_threshold if max_score is None else max_score

    score, ip = _query_running_app(cfg)
    source = "app" if score is not None else None
    if score is None:
        probe_ip = IpProbe(cfg.request).current_ip()
        if probe_ip:
            report = ScamalyticsScraper(cfg.cache_dir, cfg.request, cfg.score_cache_ttl).fetch(probe_ip)
            score, ip, source = report.score, report.ip, report.source
        else:
            score, ip = None, None

    if score is None:
        code, verdict = 2, "unknown"
    elif score > threshold:
        code, verdict = 1, "blocked"
    else:
        code, verdict = 0, "allowed"

    risk = level_for(score, cfg.low_max, cfg.medium_max)
    payload = {
        "allowed": verdict == "allowed",
        "exit_code": code,
        "ip": ip,
        "score": score,
        "threshold": threshold,
        "risk": LEVEL_META[risk].key,
        "source": source,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return code

    if code == 0:
        print(tr("cli.allowed", ip=ip or "--", score=score, threshold=threshold))
    elif code == 1:
        print(tr("cli.blocked", ip=ip or "--", score=score, threshold=threshold))
    else:
        print(tr("cli.unknown", ip=ip or "--"))
    return code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ipguard-gate", description="IPGuard gate check")
    p.add_argument("--max", type=int, default=None, help="Gate threshold; block when the score exceeds it (default: config)")
    p.add_argument("--json", action="store_true", help="Print JSON")
    p.add_argument("--config", metavar="PATH", help="Config file path")
    args = p.parse_args(argv)
    cfg = Config.load(args.config)
    return run_check(cfg, max_score=args.max, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
