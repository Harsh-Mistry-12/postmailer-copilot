# Made with love by Harsh Mistry (OpenSoure Weekend)
"""
OSW Email Automation — Structured Logging
==========================================
* Writes human-readable coloured output to STDOUT.
* Writes machine-readable JSON lines to  logs/run_<timestamp>.jsonl
* Exposes helpers for emitting send-status records that feed the dashboard.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import colorlog

from .config import settings

# ── Module-level logger ───────────────────────────────────────────────────────
_LOG_FORMAT = (
    "%(log_color)s%(asctime)s  %(levelname)-8s%(reset)s "
    "%(cyan)s%(name)s%(reset)s — %(message)s"
)
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_COLOR_MAP = {
    "DEBUG": "white",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}


def _build_console_handler() -> logging.Handler:
    handler = colorlog.StreamHandler(sys.stdout)
    handler.setFormatter(
        colorlog.ColoredFormatter(_LOG_FORMAT, datefmt=_DATE_FMT, log_colors=_COLOR_MAP)
    )
    return handler


class _SafeEncoder(json.JSONEncoder):
    """Falls back to str() for any type that json cannot serialise natively."""

    def default(self, o: Any) -> Any:  # noqa: ANN401
        try:
            return super().default(o)
        except TypeError:
            return str(o)


class _JsonlHandler(logging.FileHandler):
    """Writes each log record as a compact JSON line."""

    def emit(self, record: logging.LogRecord) -> None:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # attach any extra kwargs added via logger.info("msg", extra={...})
        for k, v in record.__dict__.items():
            if k not in logging.LogRecord.__dict__ and not k.startswith("_"):
                payload[k] = v
        try:
            self.stream.write(json.dumps(payload, cls=_SafeEncoder, ensure_ascii=False) + "\n")
            self.flush()
        except Exception:  # noqa: BLE001
            self.handleError(record)


# Session-specific log file
_SESSION_START = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
_LOG_FILE: Path | None = None


def get_logger(name: str = "osw_mailer") -> logging.Logger:
    """Return (or create) the named logger, wired to console + JSONL file."""
    global _LOG_FILE

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    level = getattr(logging, settings.log_level, logging.INFO)
    logger.setLevel(level)

    # Console
    logger.addHandler(_build_console_handler())

    # JSONL file
    log_dir: Path = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    _LOG_FILE = log_dir / f"run_{_SESSION_START}.jsonl"
    file_handler = _JsonlHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


# ── Structured send-event helper ──────────────────────────────────────────────

_SEND_LOG_FILE: Path | None = None
_send_records: list[dict[str, Any]] = []


def _get_send_log_path() -> Path:
    global _SEND_LOG_FILE
    if _SEND_LOG_FILE is None:
        log_dir: Path = settings.log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        _SEND_LOG_FILE = log_dir / f"send_events_{_SESSION_START}.jsonl"
    return _SEND_LOG_FILE


def log_send_event(
    *,
    recipient_email: str,
    recipient_name: str,
    company: str,
    company_type: str,
    status: str,          # "success" | "failed" | "skipped"
    attempt: int = 1,
    error: str | None = None,
    llm_output: str | None = None,
) -> None:
    """Append one structured send-event record to the JSONL send log."""
    record: dict[str, Any] = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "recipient_email": recipient_email,
        "recipient_name": recipient_name,
        "company": company,
        "company_type": company_type,
        "status": status,
        "attempt": attempt,
    }
    if error:
        record["error"] = error
    if llm_output:
        record["llm_output"] = llm_output

    _send_records.append(record)

    path = _get_send_log_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_send_records() -> list[dict[str, Any]]:
    """Return in-memory list of all send events recorded this session."""
    return list(_send_records)


def get_log_file_path() -> Path | None:
    return _LOG_FILE


def get_send_log_file_path() -> Path | None:
    return _SEND_LOG_FILE
