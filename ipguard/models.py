"""Data models: IP report, risk levels and helpers."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RiskLevel(IntEnum):
    """Risk level; score bands are defined by config low_max / medium_max."""
    UNKNOWN = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass(frozen=True)
class LevelMeta:
    key: str
    label: str      # i18n key, resolved with i18n.tr()
    color: str      # UI color
    emoji: str


LEVEL_META = {
    RiskLevel.UNKNOWN: LevelMeta("unknown", "risk.unknown", "#8E8E93", "⚪"),
    RiskLevel.LOW:     LevelMeta("low",     "risk.low",     "#2FBF71", "🟢"),
    RiskLevel.MEDIUM:  LevelMeta("medium",  "risk.medium",  "#F5A623", "🟡"),
    RiskLevel.HIGH:    LevelMeta("high",    "risk.high",    "#FF3B30", "🔴"),
}


def level_for(score: int | None, low_max: int = 15, medium_max: int = 30) -> RiskLevel:
    """Map a score to a risk level: <=low_max LOW; <=medium_max MEDIUM; else HIGH; None UNKNOWN."""
    if score is None:
        return RiskLevel.UNKNOWN
    if score <= low_max:
        return RiskLevel.LOW
    if score <= medium_max:
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


def is_valid_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s.strip())
        return True
    except ValueError:
        return False


@dataclass
class IpReport:
    """Snapshot of one fraud score lookup."""
    ip: str | None = None
    score: int | None = None
    risk_text: str | None = None          # "risk" field from the page's embedded JSON (informational)
    isp: str | None = None
    hostname: str | None = None
    asn: str | None = None
    country: str | None = None
    connection_type: str | None = None
    is_datacenter: bool | None = None
    flags: dict = field(default_factory=dict)   # proxy-related booleans (anonymizing vpn / tor / ...)
    fetched_at: datetime | None = None    # when the data was scraped (UTC)
    checked_at: datetime | None = None    # when it was last checked (may come from cache)
    source: str = "unknown"               # scamalytics / cache / stale-cache
    error: str | None = None

    def risk_level(self, low_max: int = 15, medium_max: int = 30) -> RiskLevel:
        return level_for(self.score, low_max, medium_max)

    def is_danger(self, gate_threshold: int) -> bool:
        """True when the score exceeds the gate threshold (block sensitive sites)."""
        return self.score is not None and self.score > gate_threshold


def report_to_dict(r: IpReport) -> dict:
    return {
        "ip": r.ip,
        "score": r.score,
        "risk_text": r.risk_text,
        "isp": r.isp,
        "hostname": r.hostname,
        "asn": r.asn,
        "country": r.country,
        "connection_type": r.connection_type,
        "is_datacenter": r.is_datacenter,
        "flags": r.flags,
        "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
    }


def report_from_dict(d: dict) -> IpReport | None:
    try:
        fetched = d.get("fetched_at")
        return IpReport(
            ip=d.get("ip"),
            score=d.get("score"),
            risk_text=d.get("risk_text"),
            isp=d.get("isp"),
            hostname=d.get("hostname"),
            asn=d.get("asn"),
            country=d.get("country"),
            connection_type=d.get("connection_type"),
            is_datacenter=d.get("is_datacenter"),
            flags=d.get("flags") or {},
            fetched_at=datetime.fromisoformat(fetched) if fetched else None,
            source="cache",
        )
    except (TypeError, ValueError):
        return None
