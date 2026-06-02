"""Logging filter that masks secret-shaped substrings before lines hit
the handler.

Why this and not just discipline? The codebase logs config dicts, error
payloads from external services, and SMTP/IMAP errors that quote the
connection URI. Any of those can carry an API key or password. The
review (`H-LogPII`) flagged that `settings_scrub.py` cleans the API
response but not log lines. This filter is the missing leg of that
defense.

Design notes:
  * `logging.Filter.filter()` runs on every record across every logger
    that mounts it — we mount on the root logger at app startup so all
    handlers inherit it (uvicorn stdout, file handlers, syslog).
  * The mutation is applied to `record.msg` *after* normal % / str.format
    substitution by switching to `record.getMessage()` then clearing
    `args`. This is the standard pattern for filter-based scrubbing.
  * Patterns are conservative — every regex anchors on a recognisable
    prefix (Bearer / sk- / ody_ / xox?-) or a clearly-named field
    (password=, "api_key": ...). Pure-entropy substrings are NOT
    masked: false positives would corrupt useful log content.
"""

import logging
import re
from typing import Iterable, Tuple

# Each entry: (compiled regex, replacement). Replacements keep the
# label/prefix so the masked output remains debuggable ("Bearer ****"
# is more useful than "[redacted]").
_PATTERNS: list = [
    # Bearer / Basic auth headers (case-insensitive on the scheme).
    (re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._\-+/=]{8,}"), r"\1 ****"),
    # OpenAI / Anthropic / generic sk- keys.
    (re.compile(r"\b(sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{16,})"), "sk-****"),
    # HuggingFace tokens.
    (re.compile(r"\b(hf_[A-Za-z0-9]{20,})"), "hf_****"),
    # Odysseus API tokens.
    (re.compile(r"\b(ody_[A-Za-z0-9_\-]{20,})"), "ody_****"),
    # Google API keys (AIzaSy...).
    (re.compile(r"\b(AIza[0-9A-Za-z\-_]{20,})"), "AIza****"),
    # Slack tokens.
    (re.compile(r"\b(xox[abprs]-[A-Za-z0-9\-]{8,})"), "xox-****"),
    # AWS access keys.
    (re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b"), "AWS****"),
    # GitHub personal access tokens / app tokens.
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})"), "gh*_****"),
    # Generic password=value / token=value in URI or query strings.
    (re.compile(r"(?i)\b(password|passwd|pwd|token|api[_-]?key|secret)=([^\s&;\"\']+)"), r"\1=****"),
    # JSON-style "password": "..." / "api_key": "..." etc.
    (re.compile(
        r'(?i)"(password|passwd|pwd|token|api[_-]?key|secret|client[_-]?secret|access[_-]?token|refresh[_-]?token)"\s*:\s*"([^"\\]+)"'
    ), r'"\1": "****"'),
    # SMTP/IMAP "PLAIN base64" auth lines that occasionally land in
    # connection error logs.
    (re.compile(r"(?i)\b(LOGIN|AUTHENTICATE)\s+[^\s]+\s+([A-Za-z0-9+/=]{8,})"), r"\1 **** ****"),
]


def scrub(text: str) -> str:
    """Apply every pattern in sequence and return the masked string.
    Safe on `None` / non-str inputs (returns them unchanged)."""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for rx, repl in _PATTERNS:
        out = rx.sub(repl, out)
    return out


class SecretScrubFilter(logging.Filter):
    """Mount on the root logger to mask secrets across all handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # Materialize the formatted message once, then clear args so
            # downstream formatters don't re-apply substitution.
            msg = record.getMessage()
            scrubbed = scrub(msg)
            if scrubbed != msg:
                record.msg = scrubbed
                record.args = ()
            # Exception info — scrub the textual traceback if present.
            if record.exc_text:
                record.exc_text = scrub(record.exc_text)
        except Exception:
            # Never raise from a logging filter; that would silently drop
            # the original record and confuse operators more than a leak.
            pass
        return True


def install_root_filter() -> SecretScrubFilter:
    """Attach the filter to the root logger AND every already-mounted
    handler. Returns the filter instance so callers can detach in tests.
    Idempotent: calling twice is a no-op."""
    root = logging.getLogger()
    for f in root.filters:
        if isinstance(f, SecretScrubFilter):
            return f
    f = SecretScrubFilter()
    root.addFilter(f)
    for handler in root.handlers:
        handler.addFilter(f)
    return f


def _iter_known_loggers() -> Iterable[Tuple[str, logging.Logger]]:
    """Useful for tests: iterate every named logger plus the root."""
    yield "", logging.getLogger()
    for name in list(logging.root.manager.loggerDict):
        log = logging.getLogger(name)
        if isinstance(log, logging.Logger):
            yield name, log
