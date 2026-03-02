# Made with love by Harsh Mistry (OpenSoure Weekend)
"""
OSW Email Automation — Rich Terminal Dashboard
===============================================
Displays a live, colour-coded metrics summary after each run using the
`rich` library so operators can audit results at a glance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .logger import get_log_file_path, get_send_log_file_path, get_send_records

_console = Console()


def _pct(num: int, total: int) -> str:
    if total == 0:
        return "—"
    return f"{num / total * 100:.1f}%"


def show_dashboard(metrics: dict[str, Any]) -> None:
    """
    Render a post-run terminal dashboard.

    Parameters
    ----------
    metrics:
        Dict returned by :func:`dispatcher.dispatch_batch`, e.g.
        ``{"sent": 195, "failed": 5, "total": 200}``.
    """
    sent   = metrics.get("sent", 0)
    failed = metrics.get("failed", 0)
    total  = metrics.get("total", 0)

    _console.rule(
        "[bold magenta]✦  OSW Email Automation — Run Summary  ✦[/bold magenta]"
    )

    # ── Summary panel ─────────────────────────────────────────────────────────
    summary_lines = [
        f"[bold white]Total processed:[/] {total}",
        f"[bold green]  ✓ Sent successfully:[/] {sent}  ({_pct(sent, total)})",
        f"[bold red]  ✗ Failed:[/]            {failed}  ({_pct(failed, total)})",
        f"[dim]Run completed at: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}[/]",
    ]
    _console.print(
        Panel(
            "\n".join(summary_lines),
            title="[bold cyan]Batch Metrics[/]",
            border_style="bright_blue",
            padding=(1, 3),
        )
    )

    # ── Per-status breakdown table ─────────────────────────────────────────────
    records = get_send_records()
    if records:
        table = Table(
            box=box.SIMPLE_HEAD,
            show_footer=False,
            highlight=True,
            title="[bold]Last 20 Records[/]",
        )
        table.add_column("Recipient",     style="cyan",   no_wrap=True)
        table.add_column("Company",       style="magenta")
        table.add_column("Type",          style="yellow")
        table.add_column("Status",        justify="center")
        table.add_column("Attempt",       justify="center", style="dim")

        for rec in records[-20:]:
            status_text = (
                Text("✓ success", style="bold green")
                if rec["status"] == "success"
                else Text("✗ failed",  style="bold red")
            )
            table.add_row(
                rec.get("recipient_email", ""),
                rec.get("company", ""),
                rec.get("company_type", ""),
                status_text,
                str(rec.get("attempt", 1)),
            )

        _console.print(table)

    # ── Log file paths ─────────────────────────────────────────────────────────
    log_path      = get_log_file_path()
    send_log_path = get_send_log_file_path()

    _console.print(
        Panel(
            "\n".join([
                f"[bold]Application log:[/]   {log_path or 'N/A'}",
                f"[bold]Send events log:[/]   {send_log_path or 'N/A'}",
            ]),
            title="[bold cyan]Log Files[/]",
            border_style="dim",
            padding=(1, 3),
        )
    )

    _console.rule("[dim]End of report[/dim]")
