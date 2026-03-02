# Made with love by Harsh Mistry (OpenSoure Weekend)
"""
OSW Email Automation — Configuration
=====================================
Loads and validates all runtime settings from the .env file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Resolve project root → always load the .env next to this package
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)


def _require(key: str) -> str:
    """Return env-var or raise a descriptive error."""
    val = os.getenv(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"Required environment variable '{key}' is missing or empty. "
            f"Please set it in your .env file."
        )
    return val


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    # ── Batch size ──────────────────────────────────────────────────────────
    no_of_email_to_process: str | int = field(
        default_factory=lambda: os.getenv("NO_OF_EMAIL_TO_PROCESS", "Max").strip()
    )

    # ── Groq LLM ────────────────────────────────────────────────────────────
    groq_api_key: str = field(default_factory=lambda: _require("GROQ_API_KEY"))
    groq_model: str = field(
        default_factory=lambda: os.getenv(
            "GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
        )
    )

    # ── SMTP ────────────────────────────────────────────────────────────────
    smtp_host: str = field(
        default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com")
    )
    smtp_port: int = field(default_factory=lambda: _int("SMTP_PORT", 587))
    smtp_username: str = field(default_factory=lambda: _require("SMTP_USERNAME"))
    smtp_password: str = field(default_factory=lambda: _require("SMTP_PASSWORD"))
    sender_name: str = field(
        default_factory=lambda: os.getenv("SENDER_NAME", "OpenSource Weekend Team")
    )
    sender_email: str = field(default_factory=lambda: _require("SENDER_EMAIL"))

    # ── Rate limiting ───────────────────────────────────────────────────────
    max_concurrent_sends: int = field(
        default_factory=lambda: _int("MAX_CONCURRENT_SENDS", 10)
    )
    send_delay_seconds: float = field(
        default_factory=lambda: _float("SEND_DELAY_SECONDS", 1.0)
    )

    # ── Retry policy ────────────────────────────────────────────────────────
    max_retries: int = field(default_factory=lambda: _int("MAX_RETRIES", 3))
    retry_min_wait: int = field(
        default_factory=lambda: _int("RETRY_MIN_WAIT_SECONDS", 2)
    )
    retry_max_wait: int = field(
        default_factory=lambda: _int("RETRY_MAX_WAIT_SECONDS", 30)
    )

    # ── Logging ─────────────────────────────────────────────────────────────
    log_dir: Path = field(
        default_factory=lambda: _PROJECT_ROOT
        / os.getenv("LOG_DIR", "logs")
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper()
    )

    @property
    def batch_limit(self) -> int | None:
        """Return None for 'Max', otherwise the integer limit."""
        raw = str(self.no_of_email_to_process).strip().lower()
        if raw == "max":
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    @property
    def sender_formatted(self) -> str:
        return f"{self.sender_name} <{self.sender_email}>"


# Singleton — import this everywhere
settings = Config()
