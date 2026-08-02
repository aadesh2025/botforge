"""An unfilled `.env` placeholder must read as unset — never as its own comment text.

The outage these pin (ADR-044): `.env.example` documents unset variables as
``KEY=<spaces># [HUMAN] note``. python-dotenv only strips a trailing comment when something
precedes it, so on a blank line the comment *became the value*. `GEMINI_API_KEY` resolved to
the literal string ``# [HUMAN] Google Gemini free tier``, which is non-empty — it passed every
"is a key configured?" guard and was sent to Google as a real key. The published agent then
answered every visitor with empty content and HTTP 200, silently, for an unknown period.

The second half of the file is the constraint that makes the fix safe: values legitimately
contain `#`, and truncating at the first one would trade this bug for a worse, quieter one.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"


def _settings(**raw: str) -> Settings:
    """Build Settings from raw values, bypassing the developer's own .env."""
    return Settings(_env_file=None, **raw)  # type: ignore[arg-type]


def test_comment_only_value_is_unset_not_the_comment() -> None:
    s = _settings(gemini_api_key="   # [HUMAN] Google Gemini free tier")
    assert s.gemini_api_key is None


def test_every_placeholder_shape_in_the_file_resolves_to_unset() -> None:
    """The exact strings shipped in .env.example, not a paraphrase of them."""
    for raw in ("# [HUMAN]", "  # [HUMAN] paid", "\t# optional", "# generate a random string"):
        assert _settings(openai_api_key=raw).openai_api_key is None, raw


def test_a_dropped_placeholder_falls_back_to_the_field_default() -> None:
    """Dropping the key must let the default apply — not force None onto a non-optional field."""
    assert _settings(smtp_host="# [HUMAN] e.g. smtp.resend.com").smtp_host == ""
    assert _settings(env="# dev | test | prod").env == "dev"
    assert _settings(auth_rate_limit="# requests per window").auth_rate_limit == 30


def test_values_containing_a_hash_are_preserved() -> None:
    """The reason this is not "strip everything after the first #".

    A JWT signing key, a DB password or a URL fragment may legitimately contain '#'. Truncating
    there would silently corrupt them — a quieter failure than the one being fixed.
    """
    assert _settings(secret_key="abc#def").secret_key == "abc#def"
    assert _settings(api_base_url="http://x/y#frag").api_base_url == "http://x/y#frag"
    assert _settings(smtp_pass="p#ss#word").smtp_pass == "p#ss#word"


def test_ordinary_values_are_untouched() -> None:
    s = _settings(groq_api_key="gsk_realkey", env="prod")
    assert s.groq_api_key == "gsk_realkey"
    assert s.env == "prod"


def test_env_example_never_reintroduces_the_broken_line_shape() -> None:
    """Defence in depth: the code fix can't reach non-Python readers of this file.

    `.env` is also handed to containers via compose's `env_file`, which parses it with its own
    rules. So the file itself must not contain the trap, independent of `Settings`.
    """
    offenders = [
        line
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip())
        and not stripped.startswith("#")
        and "=" in stripped
        and stripped.split("=", 1)[1].lstrip().startswith("#")
    ]
    assert offenders == [], f"comment shares a line with a blank value: {offenders}"
