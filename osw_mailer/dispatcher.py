"""
OSW Email Automation — Async SMTP Dispatcher
============================================
Sends personalised HTML emails via aiosmtplib (async STARTTLS SMTP).

Key features
------------
* Async connection pool — one connection per worker (via asyncio.Semaphore guard)
* Rate limiting   — configurable concurrent-send cap + inter-group delay
* Retry           — tenacity exponential back-off on transient SMTP errors
* Structured logs — emits send events to the logger module
"""

from __future__ import annotations

import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import aiosmtplib
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings
from .logger import get_logger, log_send_event
from .models import Recipient
from .renderer import render_email

log = get_logger(__name__)

# ── Retryable SMTP exception types ────────────────────────────────────────────
_RETRYABLE = (
    aiosmtplib.SMTPConnectError,
    aiosmtplib.SMTPServerDisconnected,
    aiosmtplib.SMTPResponseException,
    asyncio.TimeoutError,
    ConnectionError,
)


# ── MIME builder ──────────────────────────────────────────────────────────────

def _build_message(recipient: Recipient, html_body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"🚀 {recipient.company_name} × OpenSource Weekend — You're Invited!"
    )
    msg["From"] = formataddr((settings.sender_name, settings.sender_email))
    msg["To"] = formataddr((recipient.name, recipient.email))
    msg["Reply-To"] = settings.sender_email

    # Plain-text fallback
    plain = (
        f"Hi {recipient.display_name},\n\n"
        f"We'd love to invite {recipient.company_name} to OpenSource Weekend.\n\n"
        f"{recipient.llm_benefit_bullets}\n\n"
        "Register your interest at: https://opensourceweekend.dev\n\n"
        "— OpenSource Weekend Team\n\n"
        "To unsubscribe: https://opensourceweekend.dev/unsubscribe"
    )
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


# ── Per-email send (with retry) ────────────────────────────────────────────────

async def _send_one(recipient: Recipient, attempt_num: int = 1) -> bool:
    """
    Render + send a single email.
    Returns ``True`` on success, ``False`` on final failure.
    """
    html_body = render_email(recipient)
    msg = _build_message(recipient, html_body)

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(_RETRYABLE),
            stop=stop_after_attempt(settings.max_retries),
            wait=wait_exponential(
                min=settings.retry_min_wait, max=settings.retry_max_wait
            ),
            reraise=True,
        ):
            with attempt:
                await aiosmtplib.send(
                    msg,
                    hostname=settings.smtp_host,
                    port=settings.smtp_port,
                    username=settings.smtp_username,
                    password=settings.smtp_password,
                    start_tls=True,
                    timeout=30,
                )

        log.info("✓  Sent → %s (%s)", recipient.email, recipient.company_name)
        log_send_event(
            recipient_email=recipient.email,
            recipient_name=recipient.name,
            company=recipient.company_name,
            company_type=recipient.company_type,
            status="success",
            attempt=attempt_num,
            llm_output=recipient.llm_benefit_bullets,
        )
        return True

    except Exception as exc:  # noqa: BLE001
        log.error(
            "✗  Failed → %s (%s): %s", recipient.email, recipient.company_name, exc
        )
        log_send_event(
            recipient_email=recipient.email,
            recipient_name=recipient.name,
            company=recipient.company_name,
            company_type=recipient.company_type,
            status="failed",
            attempt=attempt_num,
            error=str(exc),
            llm_output=recipient.llm_benefit_bullets,
        )
        return False


# ── Batch dispatcher ──────────────────────────────────────────────────────────

async def dispatch_batch(recipients: list[Recipient]) -> dict[str, int]:
    """
    Send emails to all recipients concurrently, respecting:
    - ``settings.max_concurrent_sends`` — semaphore concurrency cap
    - ``settings.send_delay_seconds``   — pause between each batch group

    Returns
    -------
    dict with keys ``sent``, ``failed``, ``total``
    """
    sem = asyncio.Semaphore(settings.max_concurrent_sends)
    sent = 0
    failed = 0

    async def _guarded_send(r: Recipient) -> bool:
        async with sem:
            result = await _send_one(r)
            await asyncio.sleep(settings.send_delay_seconds)
            return result

    log.info("Dispatching %d emails …", len(recipients))
    results = await asyncio.gather(*[_guarded_send(r) for r in recipients])

    for ok in results:
        if ok:
            sent += 1
        else:
            failed += 1

    return {"sent": sent, "failed": failed, "total": len(recipients)}
