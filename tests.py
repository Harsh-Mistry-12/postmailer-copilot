# Made with love by Harsh Mistry (OpenSoure Weekend)
"""
OSW Email Automation — Test Suite
==================================
Runs offline / unit-level tests that do NOT require real SMTP or Groq credentials.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from osw_mailer.models import Recipient, load_recipients
from osw_mailer.renderer import _bullets_to_html, render_email
from osw_mailer.personalizer import _build_user_prompt, _clean_bullets


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_recipient(**kwargs) -> Recipient:
    defaults = dict(
        email="test@example.com",
        name="Test User",
        company_name="Test Corp",
        company_type="corporate",
        city="Bangalore",
        state="Karnataka",
        capacity="200",
        industry="Software",
        llm_benefit_bullets=(
            "• Networking with 500+ practitioners\n"
            "• Workshops led by experts\n"
            "• Cutting-edge project exposure\n"
            "• Career opportunities\n"
            "• Latest developer tool insights"
        ),
    )
    defaults.update(kwargs)
    return Recipient(**defaults)


# ── Model tests ───────────────────────────────────────────────────────────────

class TestRecipient(unittest.TestCase):

    def test_display_name_first_word(self):
        r = _make_recipient(name="Alice Johnson")
        self.assertEqual(r.display_name, "Alice")

    def test_display_name_fallback(self):
        r = _make_recipient(name="")
        self.assertEqual(r.display_name, "there")

    def test_normalised_type_lowercase(self):
        r = _make_recipient(company_type="  Corporate  ")
        self.assertEqual(r.normalised_type, "corporate")

    def test_to_dict_keys(self):
        r = _make_recipient()
        d = r.to_dict()
        for key in ("email", "name", "company_name", "company_type", "city", "state"):
            self.assertIn(key, d)


# ── CSV loader tests ──────────────────────────────────────────────────────────

class TestCSVLoader(unittest.TestCase):

    def _write_csv(self, content: str, tmp_path: Path) -> Path:
        f = tmp_path / "test.csv"
        f.write_text(textwrap.dedent(content), encoding="utf-8")
        return f

    def test_loads_valid_rows(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.csv"
            path.write_text(
                "email,name,company_name,company_type,city,state\n"
                "a@b.com,Alice,Acme,corporate,Delhi,Delhi\n",
                encoding="utf-8",
            )
            recipients = load_recipients(path)
            self.assertEqual(len(recipients), 1)
            self.assertEqual(recipients[0].email, "a@b.com")

    def test_skips_invalid_email(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.csv"
            path.write_text(
                "email,name,company_name,company_type\n"
                "not-an-email,Bob,Corp,startup\n",
                encoding="utf-8",
            )
            recipients = load_recipients(path)
            self.assertEqual(len(recipients), 0)

    def test_missing_required_columns_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.csv"
            path.write_text("email,name\na@b.com,Carol\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_recipients(path)

    def test_limit_respected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.csv"
            rows = "email,name,company_name,company_type\n"
            for i in range(10):
                rows += f"u{i}@x.com,User{i},Corp{i},startup\n"
            path.write_text(rows, encoding="utf-8")
            recipients = load_recipients(path, limit=3)
            self.assertEqual(len(recipients), 3)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_recipients("/nonexistent/path.csv")


# ── Renderer tests ────────────────────────────────────────────────────────────

class TestRenderer(unittest.TestCase):

    def test_bullets_to_html_basic(self):
        raw = "• First bullet\n• Second bullet"
        html = _bullets_to_html(raw)
        self.assertIn("<li>First bullet</li>", html)
        self.assertIn("<li>Second bullet</li>", html)

    def test_bullets_to_html_strips_prefix(self):
        raw = "- dash bullet\n* asterisk bullet"
        html = _bullets_to_html(raw)
        self.assertIn("<li>dash bullet</li>", html)

    def test_render_email_contains_recipient_name(self):
        r = _make_recipient(name="Zara Ahmed", company_name="FOSS United")
        html = render_email(r)
        self.assertIn("Zara", html)
        self.assertIn("FOSS United", html)

    def test_render_email_contains_bullets(self):
        r = _make_recipient()
        html = render_email(r)
        self.assertIn("<li>", html)


# ── Personalizer unit tests ────────────────────────────────────────────────────

class TestPersonalizer(unittest.TestCase):

    def test_clean_bullets_caps_at_5(self):
        raw = "\n".join(f"• Bullet {i}" for i in range(8))
        result = _clean_bullets(raw)
        self.assertEqual(result.count("•"), 5)

    def test_clean_bullets_converts_dashes(self):
        raw = "- First\n- Second"
        result = _clean_bullets(raw)
        self.assertTrue(result.startswith("•"))

    def test_build_user_prompt_contains_company(self):
        r = _make_recipient(company_name="OpenSrc Devs")
        prompt = _build_user_prompt(r)
        self.assertIn("OpenSrc Devs", prompt)

    def test_build_user_prompt_contains_industry(self):
        r = _make_recipient(industry="FinTech")
        prompt = _build_user_prompt(r)
        self.assertIn("FinTech", prompt)

    def test_generate_bullets_mocked(self):
        """
        Verify generate_benefit_bullets uses the Groq client and returns
        cleaned bullet text — without making a real API call.
        """
        r = _make_recipient()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="• A\n• B\n• C\n• D\n• E"))
        ]

        async def _run():
            with patch(
                "osw_mailer.personalizer._get_client",
                return_value=MagicMock(
                    chat=MagicMock(
                        completions=MagicMock(
                            create=AsyncMock(return_value=mock_response)
                        )
                    )
                ),
            ):
                from osw_mailer.personalizer import generate_benefit_bullets
                bullets = await generate_benefit_bullets(r)
                return bullets

        bullets = asyncio.run(_run())
        self.assertEqual(bullets.count("•"), 5)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
