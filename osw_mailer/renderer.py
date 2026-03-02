# Made with love by Harsh Mistry (OpenSoure Weekend)
"""
OSW Email Automation — HTML Template Renderer
=============================================
Turns a :class:`Recipient` (with llm_benefit_bullets already populated)
into a ready-to-send HTML string using the static Jinja2 template.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from .models import Recipient

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_TEMPLATE_NAME = "email_template.html"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _bullets_to_html(raw_bullets: str) -> str:
    """
    Convert the LLM-generated plain-text bullet string to <li> elements.

    Input example::
        • Networking with 500+ developers
        • Hands-on workshops …

    Output example::
        <li>Networking with 500+ developers</li>
        <li>Hands-on workshops …</li>
    """
    lines = []
    for line in raw_bullets.strip().splitlines():
        text = line.lstrip("•▸-* \t").strip()
        if text:
            lines.append(f"<li>{text}</li>")
    return "\n          ".join(lines)


def render_email(recipient: "Recipient") -> str:
    """
    Render the HTML email for a single recipient.

    Parameters
    ----------
    recipient:
        A :class:`Recipient` whose ``llm_benefit_bullets`` field has been
        populated by the personaliser.

    Returns
    -------
    str
        Complete, inline-styled HTML ready for the SMTP mime payload.
    """
    template = _env.get_template(_TEMPLATE_NAME)
    html = template.render(
        recipient_name=recipient.display_name,
        company_name=recipient.company_name,
        benefit_bullets_html=_bullets_to_html(recipient.llm_benefit_bullets),
    )
    return html
