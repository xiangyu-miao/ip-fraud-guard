"""Configuration loading and persistence (JSON, per-platform user config dir)."""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

APP_DIR_NAME = "IPGuard"

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def default_config_path() -> Path:
    """Config location: macOS ~/Library/Application Support/IPGuard/config.json;
    Windows %APPDATA%\\IPGuard\\config.json; Linux ~/.config/IPGuard/config.json."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / APP_DIR_NAME / "config.json"


@dataclass
class GateServerConfig:
    """Local gate HTTP service (loopback only)."""
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 17654
    token: str = ""          # empty = no auth; otherwise require X-Gate-Token header or ?token=


@dataclass
class RequestConfig:
    timeout: float = 10.0
    user_agent: str = _DEFAULT_UA


@dataclass
class UIConfig:
    always_on_top: bool = True
    opacity: float = 0.96
    start_hidden: bool = False
    pos_x: int | None = None     # last widget position
    pos_y: int | None = None


@dataclass
class Config:
    # Polling: probe the external IP every ip_check_interval seconds (lightweight);
    # fraud score results are cached for score_cache_ttl seconds — the same IP is
    # not re-requested from Scamalytics within the TTL.
    ip_check_interval: int = 60
    score_cache_ttl: int = 1800
    # Risk band thresholds (colors)
    low_max: int = 15
    medium_max: int = 30
    # Gate threshold: score > gate_threshold blocks sensitive sites (notify + gate API)
    gate_threshold: int = 20
    # UI language: "system" | "en" | "zh"
    language: str = "system"
    # Notification switches
    notify_on_level_up: bool = True
    notify_on_ip_change: bool = True
    notify_on_danger: bool = True

    gate_server: GateServerConfig = field(default_factory=GateServerConfig)
    request: RequestConfig = field(default_factory=RequestConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        path = Path(path).expanduser() if path else default_config_path()
        data: dict = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text("utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, ValueError) as e:
                log.warning("Could not read config file, using defaults: %s", e)

        known = {f.name for f in dataclasses.fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known and k not in ("gate_server", "request", "ui")}
        cfg = cls(
            gate_server=GateServerConfig(**{k: v for k, v in data.get("gate_server", {}).items()
                                            if k in {"enabled", "host", "port", "token"}}),
            request=RequestConfig(**{k: v for k, v in data.get("request", {}).items()
                                     if k in {"timeout", "user_agent"}}),
            ui=UIConfig(**{k: v for k, v in data.get("ui", {}).items()
                           if k in {"always_on_top", "opacity", "start_hidden", "pos_x", "pos_y"}}),
            **kwargs,
        )
        cfg.path = path
        return cfg

    def save(self) -> None:
        if self.path is None:
            return
        data = dataclasses.asdict(self)
        data.pop("path", None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, self.path)

    @property
    def cache_dir(self) -> Path:
        assert self.path is not None
        return self.path.parent / "cache"
