"""Structured logging that cannot emit submitted content or secrets.

The formatter emits JSON lines. A redaction filter is installed as defence in
depth: any record whose message or arguments contain a sensitive key name has
that value replaced before it reaches a handler. Application code is expected
never to pass submitted text to the logger in the first place; the filter
exists so that a mistake degrades to a redaction rather than a disclosure.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

#: Keys whose values must never be written to logs.
SENSITIVE_KEYS = frozenset(
    {
        "text",
        "content",
        "original_text",
        "display_text",
        "analysis_text",
        "password",
        "current_password",
        "new_password",
        "token",
        "session_token",
        "guest_token",
        "csrf_token",
        "secret",
        "secret_key",
        "encryption_key",
        "authorization",
        "cookie",
        "set-cookie",
        "email",
        "filename",
    }
)

REDACTED = "[redacted]"

#: Attributes every LogRecord carries; these are framework metadata, not payload.
_RESERVED_RECORD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None)))

#: Keys that carry free-form submitted content. Once one appears in a log line,
#: the remainder of that line is unbounded content and is dropped entirely.
CONTENT_KEYS = frozenset({"text", "content", "original_text", "display_text", "analysis_text"})

#: ``key=value`` / ``key: value`` for discrete secrets — redact the single token.
_INLINE_SECRET = re.compile(
    r"(?i)\b("
    + "|".join(re.escape(k) for k in sorted(SENSITIVE_KEYS - CONTENT_KEYS))
    + r")\b\s*[=:]\s*\"?[^\s,\"}]+"
)

#: ``key=…`` for content fields — redact through end of line.
_INLINE_CONTENT = re.compile(
    r"(?i)\b(" + "|".join(re.escape(k) for k in sorted(CONTENT_KEYS)) + r")\b\s*[=:].*$",
    re.MULTILINE,
)


def redact_value(key: str, value: Any) -> Any:
    """Return ``value`` or a redaction marker when ``key`` is sensitive."""
    return REDACTED if key.lower() in SENSITIVE_KEYS else value


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive keys in a mapping."""
    clean: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_KEYS:
            clean[key] = REDACTED
        elif isinstance(value, dict):
            clean[key] = redact_mapping(value)
        else:
            clean[key] = value
    return clean


def redact_text(message: str) -> str:
    """Redact ``key=value`` pairs naming a sensitive field.

    Content keys redact through end of line because the value is unbounded
    free text; discrete secrets redact only the value token.
    """
    message = _INLINE_CONTENT.sub(lambda m: f"{m.group(1)}={REDACTED}", message)
    return _INLINE_SECRET.sub(lambda m: f"{m.group(1)}={REDACTED}", message)


class RedactionFilter(logging.Filter):
    """Defence-in-depth filter that scrubs sensitive values from records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if isinstance(record.args, dict):
            record.args = redact_mapping(record.args)
        # Only scrub caller-supplied `extra` fields. LogRecord's own attributes
        # (notably `filename`, meaning the *source* file) are diagnostic, and
        # redacting them would throw away the location of the log call.
        for key in list(vars(record)):
            if key not in _RESERVED_RECORD_ATTRS and key.lower() in SENSITIVE_KEYS:
                setattr(record, key, REDACTED)
        return True


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per record."""

    _RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None)))

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in self._RESERVED and not key.startswith("_") and key != "taskName":
                payload[key] = value
        if record.exc_info:
            # Type and message only — never the traceback, which can embed content.
            exc_type = record.exc_info[0]
            payload["error_type"] = exc_type.__name__ if exc_type else "Unknown"
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter and redaction filter on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn's access log echoes full URLs; paths carry opaque IDs only, but the
    # duplicate handler would bypass our formatter.
    for name in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
