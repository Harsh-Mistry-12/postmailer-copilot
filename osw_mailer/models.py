"""
OSW Email Automation — Recipient Data Model & CSV Loader
=========================================================
Loads the input CSV, validates each row, and returns a list of Recipient objects
ready for the LLM personalizer and email dispatcher.

Expected CSV columns (case-insensitive):
    email            — REQUIRED
    name             — REQUIRED
    company_name     — REQUIRED
    company_type     — REQUIRED  (e.g. corporate, startup, community, student)
    city             — optional
    state            — optional
    capacity         — optional  (company / community capacity)
    industry         — optional
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
from email_validator import EmailNotValidError, validate_email

from .logger import get_logger

log = get_logger(__name__)

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Recipient:
    email: str
    name: str
    company_name: str
    company_type: str          # corporate | startup | community | student | individual
    city: str = ""
    state: str = ""
    capacity: Optional[str] = None
    industry: str = ""

    # Populated by personalizer
    llm_benefit_bullets: str = field(default="", repr=False)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def display_name(self) -> str:
        """First name for greeting line."""
        return self.name.split()[0].title() if self.name else "there"

    @property
    def normalised_type(self) -> str:
        """Lower-cased, stripped company type used in prompt building."""
        return self.company_type.strip().lower()

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "name": self.name,
            "company_name": self.company_name,
            "company_type": self.company_type,
            "city": self.city,
            "state": self.state,
            "capacity": self.capacity,
            "industry": self.industry,
        }


# ── Column name aliases ────────────────────────────────────────────────────────
# Maps possible CSV header variants → canonical field names.
_ALIASES: dict[str, str] = {
    "email": "email",
    "email_address": "email",
    "e-mail": "email",
    "name": "name",
    "full_name": "name",
    "contact_name": "name",
    "company_name": "company_name",
    "company": "company_name",
    "organisation": "company_name",
    "organization": "company_name",
    "company_type": "company_type",
    "type": "company_type",
    "category": "company_type",
    "city": "city",
    "state": "state",
    "province": "state",
    "capacity": "capacity",
    "company_capacity": "capacity",
    "size": "capacity",
    "industry": "industry",
    "sector": "industry",
}

_REQUIRED_FIELDS = {"email", "name", "company_name", "company_type"}


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to canonical names using the alias map."""
    mapping = {}
    for col in df.columns:
        key = col.strip().lower().replace(" ", "_").replace("-", "_")
        if key in _ALIASES:
            mapping[col] = _ALIASES[key]
    return df.rename(columns=mapping)


def _validate_email_address(email: str) -> str | None:
    """Return normalised email or None if invalid."""
    try:
        info = validate_email(email, check_deliverability=False)
        return info.normalized
    except EmailNotValidError:
        return None


def load_recipients(csv_path: str | Path, limit: int | None = None) -> list[Recipient]:
    """
    Parse *csv_path*, validate every row, return a list of :class:`Recipient`.

    Parameters
    ----------
    csv_path:
        Absolute or relative path to the input CSV file.
    limit:
        Maximum number of valid recipients to return (``None`` = all).
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV input file not found: {path}")

    log.info("Loading recipients from %s", path)

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = _normalise_columns(df)
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)  # strip whitespace

    # Check required columns exist
    missing = _REQUIRED_FIELDS - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {missing}. "
            f"Found columns: {list(df.columns)}"
        )

    recipients: list[Recipient] = []
    skipped = 0

    for idx, row in df.iterrows():
        # ── Validate e-mail ────────────────────────────────────────────────
        raw_email = row.get("email", "")
        normalised_email = _validate_email_address(raw_email)
        if not normalised_email:
            log.warning("Row %d — invalid e-mail '%s', skipping.", idx + 2, raw_email)
            skipped += 1
            continue

        # ── Required text fields ───────────────────────────────────────────
        name = row.get("name", "").strip()
        company_name = row.get("company_name", "").strip()
        company_type = row.get("company_type", "").strip()

        if not name or not company_name or not company_type:
            log.warning(
                "Row %d — name/company_name/company_type is blank, skipping.", idx + 2
            )
            skipped += 1
            continue

        r = Recipient(
            email=normalised_email,
            name=name,
            company_name=company_name,
            company_type=company_type,
            city=row.get("city", ""),
            state=row.get("state", ""),
            capacity=row.get("capacity") or None,
            industry=row.get("industry", ""),
        )
        recipients.append(r)

        if limit and len(recipients) >= limit:
            log.info("Batch limit of %d reached — stopping CSV parse.", limit)
            break

    log.info(
        "CSV loaded: %d valid recipients, %d skipped.", len(recipients), skipped
    )
    return recipients
