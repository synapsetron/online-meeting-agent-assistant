"""Structured logging for the backend.

Every log call is an *event*: a short snake_case name as the message plus
key/value fields passed via ``log_event`` (or ``extra=``). Session and meeting
ids are attached automatically from context variables, so any line can be
traced to one WebSocket session.

Environment:
  LOG_LEVEL   DEBUG | INFO (default) | WARNING ...
  LOG_FORMAT  console (default, human readable) | json (one object per line)
  LOG_FILE    optional path; always written as JSON lines (for analysis/thesis)

Privacy: transcript text, API keys and tokens must never be logged. Fields with
sensitive names are redacted by the formatter as a safety net; callers should
log counts/ids instead of content.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_id", default=None
)
meeting_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "meeting_id", default=None
)

_REDACT_KEYS = {
    "api_key", "apikey", "authorization", "token", "password", "secret",
    "text", "transcript", "content", "message_text",
}
_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName", "session_id", "meeting_id"}
_NOISY_LOGGERS = (
    "httpx", "httpx2", "httpcore", "anthropic", "websockets", "asyncio",
    "uvicorn.access", "watchfiles", "watchfiles.main",
)
_IGNORED_EXTRAS = {"color_message"}  # uvicorn adds ANSI-colored duplicates

_LEVEL_COLORS = {
    "DEBUG": "\033[36m", "INFO": "\033[32m", "WARNING": "\033[33m",
    "ERROR": "\033[31m", "CRITICAL": "\033[35m",
}
_RESET = "\033[0m"
_DIM = "\033[2m"


def set_session_context(session_id: str | None, meeting_id: str | None = None) -> None:
    session_id_var.set(session_id)
    meeting_id_var.set(meeting_id)


def log_event(
    logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any
) -> None:
    """Emit a structured event. Field names clashing with LogRecord get a ``f_`` prefix."""
    safe = {(f"f_{k}" if k in _RESERVED else k): v for k, v in fields.items()}
    logger.log(level, event, extra=safe, stacklevel=2)


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _RESERVED or key in _IGNORED_EXTRAS or key.startswith("_"):
            continue
        out[key] = "[redacted]" if key.lower() in _REDACT_KEYS else value
    return out


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = session_id_var.get()
        record.meeting_id = meeting_id_var.get()
        return True


def _fmt_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4g}" if abs(value) < 1e-3 else f"{value:.3f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, default=str, ensure_ascii=False)
    text = str(value)
    return json.dumps(text, ensure_ascii=False) if " " in text else text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        sid = getattr(record, "session_id", None)
        if sid:
            payload["session"] = sid
        mid = getattr(record, "meeting_id", None)
        if mid:
            payload["meeting"] = mid
        payload.update(_extras(record))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    def __init__(self, color: bool) -> None:
        super().__init__()
        self._color = color

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        level = record.levelname
        short = record.name.removeprefix("server.").replace("agents.", "").replace("api.", "")
        parts = [ts, f"{level:<7}", f"{short:<16}", record.getMessage()]
        sid = getattr(record, "session_id", None)
        if sid:
            parts.append(f"session={sid[:8]}")
        parts.extend(f"{k}={_fmt_value(v)}" for k, v in _extras(record).items())
        line = " ".join(parts)
        if self._color:
            c = _LEVEL_COLORS.get(level, "")
            line = f"{_DIM}{ts}{_RESET} {c}{level:<7}{_RESET} {short:<16} {c}{record.getMessage()}{_RESET} " + " ".join(
                parts[4:]
            )
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging() -> None:
    level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    fmt = os.environ.get("LOG_FORMAT", "console").lower()

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(level)

    stream = logging.StreamHandler(sys.stderr)
    stream.addFilter(_ContextFilter())
    stream.setFormatter(
        JsonFormatter() if fmt == "json" else ConsoleFormatter(color=sys.stderr.isatty())
    )
    root.addHandler(stream)

    log_file = os.environ.get("LOG_FILE")
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.addFilter(_ContextFilter())
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)

    quiet = logging.WARNING if level > logging.DEBUG else logging.INFO
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(quiet)
