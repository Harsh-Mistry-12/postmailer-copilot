"""
OSW Email Automation — Groq LLM Personalizer
=============================================
Generates up to 5 concise, recipient-tailored bullet points answering:
  "How can the OpenSource Weekend Conference benefit you?"

Uses tenacity for automatic retry + exponential back-off on transient failures.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from groq import AsyncGroq, RateLimitError, APIConnectionError, APIStatusError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from .config import settings
from .logger import get_logger

if TYPE_CHECKING:
    from .models import Recipient

log = get_logger(__name__)

# ── Groq async client (singleton) ─────────────────────────────────────────────
_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.groq_api_key)
    return _client


# ── Prompt builders ───────────────────────────────────────────────────────────

_AUDIENCE_HINTS: dict[str, str] = {
    "corporate":   "a corporate enterprise / business organization",
    "startup":     "an early-stage startup / entrepreneurial venture",
    "community":   "an open-source or tech community / user group",
    "student":     "a student group, college club, or academic institution",
    "individual":  "an individual developer, freelancer, or tech enthusiast",
    "ngo":         "a non-profit organization / NGO",
    "government":  "a government body or public-sector entity",
}


def _build_system_prompt() -> str:
    return (
        "You are a sharp, persuasive copywriter crafting tailored event outreach.\n"
        "Your task: write exactly 5 bullet points (each starting with '•') explaining "
        "how the OpenSource Weekend (OSW) Conference benefits the recipient's specific "
        "organization type.\n\n"
        "Rules:\n"
        "- Maximum 5 bullets. Never fewer.\n"
        "- Each bullet ≤ 20 words — concise and impactful.\n"
        "- Tailor language to the recipient's sector and needs.\n"
        "- Focus on practical, real-world benefits — not platitudes.\n"
        "- No preamble, no sign-off — output ONLY the bullet list.\n"
        "- Use '•' as the bullet character."
    )


def _build_user_prompt(recipient: "Recipient") -> str:
    audience_hint = _AUDIENCE_HINTS.get(
        recipient.normalised_type,
        f"a {recipient.company_type} organization",
    )

    parts: list[str] = [
        f"Recipient name: {recipient.name}",
        f"Organization: {recipient.company_name} ({audience_hint})",
    ]
    if recipient.industry:
        parts.append(f"Industry / sector: {recipient.industry}")
    if recipient.city and recipient.state:
        parts.append(f"Location: {recipient.city}, {recipient.state}")
    if recipient.capacity:
        parts.append(f"Organization size / capacity: {recipient.capacity}")

    parts.append(
        "\nQuestion to answer: "
        "\"How can the OpenSource Weekend Conference benefit your organization?\""
    )
    return "\n".join(parts)


# ── Core generation function ──────────────────────────────────────────────────

async def generate_benefit_bullets(recipient: "Recipient") -> str:
    """
    Call Groq LLM and return the personalised 5-bullet string.
    Retries up to ``settings.max_retries`` times with exponential back-off
    on rate-limit or transient connectivity errors.

    Raises
    ------
    Exception
        If all retries are exhausted.
    """
    client = _get_client()

    retryable = (RateLimitError, APIConnectionError, asyncio.TimeoutError)

    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(retryable),
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(
            min=settings.retry_min_wait, max=settings.retry_max_wait
        ),
        before_sleep=before_sleep_log(log, log.level),  # type: ignore[arg-type]
        reraise=True,
    ):
        with attempt:
            log.debug(
                "LLM call for %s <%s>", recipient.company_name, recipient.email
            )
            response = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": _build_system_prompt()},
                    {"role": "user",   "content": _build_user_prompt(recipient)},
                ],
                temperature=0.7,
                max_tokens=300,
            )

    raw = response.choices[0].message.content or ""
    bullets = _clean_bullets(raw)
    log.debug(
        "LLM generated %d bullets for %s", bullets.count("•"), recipient.email
    )
    return bullets


def _clean_bullets(raw: str) -> str:
    """Normalise whitespace and ensure every line starts with '•'."""
    lines = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Accept "-", "*", "–", numbered bullets and convert to "•"
        if line[0] in ("-", "*", "–") or (line[0].isdigit() and line[1:3] in (". ", ") ")):
            line = "• " + line.lstrip("-*–0123456789.) ").strip()
        elif not line.startswith("•"):
            line = "• " + line
        lines.append(line)
    # Cap at 5 bullets
    return "\n".join(lines[:5])


# ── Batch personalizer ────────────────────────────────────────────────────────

async def personalise_all(
    recipients: list["Recipient"],
    concurrency: int = 10,
) -> None:
    """
    Personalise all recipients concurrently, respecting a semaphore-based
    concurrency limit to avoid hammering the Groq rate limit.

    Mutates each :class:`Recipient` in place by setting ``llm_benefit_bullets``.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _personalise(r: "Recipient") -> None:
        async with sem:
            try:
                r.llm_benefit_bullets = await generate_benefit_bullets(r)
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "LLM personalisation failed for %s (%s): %s",
                    r.email, r.company_name, exc,
                )
                r.llm_benefit_bullets = (
                    "• Networking with 500+ open-source practitioners\n"
                    "• Hands-on workshops led by industry experts\n"
                    "• Exposure to cutting-edge open-source projects\n"
                    "• Career & collaboration opportunities\n"
                    "• Insights into the latest developer tools & trends"
                )

    tasks = [_personalise(r) for r in recipients]
    await asyncio.gather(*tasks)
    log.info("LLM personalisation complete for %d recipients.", len(recipients))
