"""Minimal dependency-free i18n: English/Chinese UI strings.

Usage:
    from .i18n import tr, set_language, current_language

    set_language("zh")                 # or "en", "system"
    tr("risk.low")                     # localized text
    tr("widget.ip", ip="1.2.3.4")      # with formatting
"""
from __future__ import annotations

import locale
import logging
import os

log = logging.getLogger(__name__)

# All UI strings live here. Keys used by models/LEVEL_META are "risk.*";
# everything else is consumed directly by UI modules.
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "risk.unknown": "Unknown",
        "risk.low": "Low risk",
        "risk.medium": "Medium risk",
        "risk.high": "High risk",
        "widget.checking": "Checking…",
        "widget.waiting": "Waiting for first check…",
        "widget.ip": "IP: {ip}",
        "widget.source.live": "live",
        "widget.source.cache": "cached",
        "widget.source.stale": "stale cache",
        "widget.fetched_at": "updated at {time}",
        "widget.warn": "⛔ Fraud score {score} exceeds gate threshold {threshold} — do not access sensitive sites",
        "widget.btn.refresh.tip": "Refresh now",
        "widget.btn.hide.tip": "Hide to tray",
        "menu.show_widget": "Show/Hide widget",
        "menu.refresh": "Refresh now",
        "menu.hide_to_tray": "Hide to tray",
        "menu.gate": "Local gate service (HTTP API)",
        "menu.on_top": "Widget always on top",
        "menu.open_page": "View Scamalytics page in browser",
        "menu.quit": "Quit IPGuard",
        "menu.language": "Language",
        "notify.level_up.title": "IPGuard risk increased",
        "notify.level_up.body": "IP {ip} fraud score {score} ({label})",
        "notify.ip_change.title": "IPGuard proxy node changed",
        "notify.ip_change.body": "{old} → {new}\nRe-evaluating fraud score…",
        "notify.danger.title": "⛔ IPGuard security gate",
        "notify.danger.body": "Fraud score {score} exceeds threshold {threshold} ({label}) — do not access sensitive sites!",
        "probe.failed": "Failed to detect external IP (all sources unreachable)",
        "cli.allowed": "✅ ALLOW    IP {ip}  fraud score {score} ≤ {threshold}, safe to access",
        "cli.blocked": "⛔ BLOCK    IP {ip}  fraud score {score} > {threshold}, do not access sensitive sites",
        "cli.unknown": "⚠️  UNKNOWN  could not get fraud score (IP: {ip}), verify manually before access",
    },
    "zh": {
        "risk.unknown": "未知",
        "risk.low": "低风险",
        "risk.medium": "中风险",
        "risk.high": "高风险",
        "widget.checking": "检测中…",
        "widget.waiting": "等待首次检测…",
        "widget.ip": "IP: {ip}",
        "widget.source.live": "实时",
        "widget.source.cache": "缓存",
        "widget.source.stale": "过期缓存",
        "widget.fetched_at": "更新于 {time}",
        "widget.warn": "⛔ 欺诈分 {score} 超过门控阈值 {threshold} — 请勿访问敏感网站",
        "widget.btn.refresh.tip": "立即刷新",
        "widget.btn.hide.tip": "隐藏到托盘",
        "menu.show_widget": "显示/隐藏悬浮窗",
        "menu.refresh": "立即刷新",
        "menu.hide_to_tray": "隐藏到托盘",
        "menu.gate": "本地门控服务（HTTP API）",
        "menu.on_top": "悬浮窗置顶",
        "menu.open_page": "在浏览器中查看 Scamalytics 页面",
        "menu.quit": "退出 IPGuard",
        "menu.language": "语言",
        "notify.level_up.title": "IPGuard 风险升级",
        "notify.level_up.body": "IP {ip} 欺诈分 {score}（{label}）",
        "notify.ip_change.title": "IPGuard 代理节点已切换",
        "notify.ip_change.body": "{old} → {new}\n正在重新评估欺诈分…",
        "notify.danger.title": "⛔ IPGuard 安全门控",
        "notify.danger.body": "欺诈分 {score} 超过阈值 {threshold}（{label}），请勿访问敏感网站！",
        "probe.failed": "外网 IP 探测失败（所有源均不可达）",
        "cli.allowed": "✅ 允许    IP {ip}  欺诈分 {score} ≤ {threshold}，可以访问敏感网站",
        "cli.blocked": "⛔ 拦截    IP {ip}  欺诈分 {score} > {threshold}，建议不要访问敏感网站",
        "cli.unknown": "⚠️  未知    无法获取欺诈分（IP: {ip}），请手动确认后再访问",
    },
}

LANGUAGES = (("en", "English"), ("zh", "中文"))


class I18n:
    def __init__(self, lang: str | None = None):
        self._lang = "en"
        self.set_language(lang or "system")

    def set_language(self, lang: str) -> str:
        """Resolve "system" from the environment; unknown codes fall back to English."""
        if lang == "system":
            lang = self._detect()
        self._lang = lang if lang in STRINGS else "en"
        return self._lang

    @staticmethod
    def _detect() -> str:
        # locale.getdefaultlocale() was removed in newer Pythons; use the stable APIs.
        candidates = [
            locale.getlocale()[0],
            os.environ.get("LC_ALL", ""),
            os.environ.get("LANG", ""),
        ]
        for c in candidates:
            if c and c.lower().startswith("zh"):
                return "zh"
        return "en"

    def t(self, key: str, **fmt) -> str:
        text = STRINGS.get(self._lang, STRINGS["en"]).get(key) or STRINGS["en"].get(key) or key
        return text.format(**fmt) if fmt else text


_current = I18n()


def tr(key: str, **fmt) -> str:
    """Translate a key into the currently active language."""
    return _current.t(key, **fmt)


def set_language(lang: str) -> str:
    return _current.set_language(lang)


def current_language() -> str:
    return _current._lang


def english(key: str) -> str:
    """Stable English text for machine-readable surfaces (HTTP API etc.)."""
    return STRINGS["en"].get(key, key)
