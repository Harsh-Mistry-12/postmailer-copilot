# Made with love by Harsh Mistry (OpenSoure Weekend)
"""
OSW Email Automation — Main Entry Point
========================================
Usage:
    python main.py --csv recipients.csv [--limit 200] [--dry-run]

Flags:
    --csv        Path to recipient CSV file (required)
    --limit      Max emails to process (overrides .env NO_OF_EMAIL_TO_PROCESS)
    --dry-run    Render & personalise but do NOT send emails (for testing)
    --no-dash    Skip the terminal dashboard at the end
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

# ── Local imports ──────────────────────────────────────────────────────────────
from osw_mailer.config import settings
from osw_mailer.dashboard import show_dashboard
from osw_mailer.dispatcher import dispatch_batch
from osw_mailer.logger import get_logger
from osw_mailer.models import load_recipients
from osw_mailer.personalizer import personalise_all

console = Console()
log = get_logger("osw_mailer.main")


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="osw-mailer",
        description="OSW Enterprise Email Automation — Personalised outreach at scale.",
    )
    parser.add_argument(
        "--csv",
        required=True,
        type=Path,
        metavar="PATH",
        help="Path to the recipients CSV file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Override the batch limit (overrides .env NO_OF_EMAIL_TO_PROCESS).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Personalise emails but skip actual SMTP sending.",
    )
    parser.add_argument(
        "--no-dash",
        action="store_true",
        help="Skip the terminal dashboard at the end.",
    )
    return parser.parse_args()


# ── Async pipeline ─────────────────────────────────────────────────────────────

async def run(args: argparse.Namespace) -> None:
    # ── 1. Resolve batch limit ─────────────────────────────────────────────────
    limit: int | None = args.limit if args.limit is not None else settings.batch_limit
    limit_display = str(limit) if limit else "Max (all)"

    console.rule("[bold magenta]✦  OSW Email Automation  ✦[/bold magenta]")
    log.info("Starting OSW Email Automation")
    log.info("CSV        : %s", args.csv)
    log.info("Batch limit: %s", limit_display)
    log.info("Dry-run    : %s", args.dry_run)
    log.info("Model      : %s", settings.groq_model)

    # ── 2. Load recipients ─────────────────────────────────────────────────────
    try:
        recipients = load_recipients(args.csv, limit=limit)
    except (FileNotFoundError, ValueError) as exc:
        log.error("Failed to load CSV: %s", exc)
        sys.exit(1)

    if not recipients:
        log.warning("No valid recipients found — nothing to send.")
        sys.exit(0)

    console.print(
        f"[bold green]✓[/] Loaded [bold]{len(recipients)}[/] valid recipients."
    )

    # ── 3. LLM Personalisation ─────────────────────────────────────────────────
    console.print("\n[bold cyan]Step 1/2:[/] Generating personalised content via Groq LLM …")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Personalising …", total=len(recipients))

        # Wrap personalise_all to tick the progress bar per recipient
        sem = asyncio.Semaphore(settings.max_concurrent_sends)

        async def _personalise_tracked(r) -> None:
            async with sem:
                from osw_mailer.personalizer import generate_benefit_bullets
                try:
                    r.llm_benefit_bullets = await generate_benefit_bullets(r)
                except Exception as exc:  # noqa: BLE001
                    log.error("LLM failed for %s: %s", r.email, exc)
                    r.llm_benefit_bullets = (
                        "• Networking with 500+ open-source practitioners\n"
                        "• Hands-on workshops led by industry experts\n"
                        "• Exposure to cutting-edge open-source projects\n"
                        "• Career & collaboration opportunities\n"
                        "• Insights into the latest developer tools & trends"
                    )
                finally:
                    progress.advance(task)

        await asyncio.gather(*[_personalise_tracked(r) for r in recipients])

    console.print(
        f"[bold green]✓[/] Personalisation complete for {len(recipients)} recipients."
    )

    # ── 4. Dry-run preview ─────────────────────────────────────────────────────
    if args.dry_run:
        log.info("DRY RUN — skipping SMTP send.  Showing first recipient preview:")
        from osw_mailer.renderer import render_email
        preview_html = render_email(recipients[0])
        preview_path = Path("logs") / "dry_run_preview.html"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(preview_html, encoding="utf-8")
        console.print(
            f"[bold yellow]DRY RUN:[/] HTML preview saved → [underline]{preview_path}[/]"
        )
        metrics = {"sent": 0, "failed": 0, "total": len(recipients)}
    else:
        # ── 5. SMTP batch dispatch ─────────────────────────────────────────────
        console.print(
            f"\n[bold cyan]Step 2/2:[/] Dispatching {len(recipients)} emails via SMTP …"
        )
        metrics = await dispatch_batch(recipients)
        console.print(
            f"[bold green]✓[/] Dispatch complete — "
            f"Sent: {metrics['sent']}, Failed: {metrics['failed']}"
        )

    # ── 6. Dashboard ───────────────────────────────────────────────────────────
    if not args.no_dash:
        show_dashboard(metrics)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
