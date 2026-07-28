"""Prompt assembly unit tests for `app/chat/assembly.py` (no DB / no network)."""

from __future__ import annotations

from app.chat.assembly import compose_system_prompt, tone_directive


def test_tone_directive_maps_known_labels() -> None:
    assert "short" in (tone_directive({"tone": "Concise"}) or "").lower()
    assert "professional" in (tone_directive({"tone": "Professional"}) or "").lower()
    # Case-insensitive: the builder stores the label exactly as displayed.
    assert tone_directive({"tone": "playful"}) == tone_directive({"tone": "Playful"})
    # An unrecognised tone still produces a usable instruction rather than being dropped.
    assert tone_directive({"tone": "Sarcastic"}) == "Write in a Sarcastic tone."
    assert tone_directive({"tone": "  "}) is None
    assert tone_directive({}) is None
    assert tone_directive(None) is None


def test_compose_system_prompt_appends_tone_without_replacing_prompt() -> None:
    """The builder's Tone selector claims to steer the writing style; it was stored on the
    version and never read, so Playful and Formal produced byte-identical replies."""
    out = compose_system_prompt("You are Acme support.", {"tone": "Playful"})
    assert out is not None
    assert out.startswith("You are Acme support.")
    assert "playful" in out.lower()


def test_compose_system_prompt_edge_cases() -> None:
    # No tone configured → the agent's prompt is passed through untouched.
    assert compose_system_prompt("You are Acme support.", {}) == "You are Acme support."
    # Tone alone still yields a prompt when the agent has no system prompt of its own.
    assert "friendly" in (compose_system_prompt(None, {"tone": "Friendly"}) or "").lower()
    assert compose_system_prompt(None, None) is None
    assert compose_system_prompt("   ", {}) is None
