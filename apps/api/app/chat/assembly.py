"""Prompt assembly (docs/06 §2 order):

`[system persona + guardrails]` → `[retrieved context]` → `[long-term memory summary]` →
`[recent message window]` → `[current user turn]`.
"""

from __future__ import annotations

from typing import Any

from app.llm.types import Message

# The builder's Tone selector is a style hint, not a behaviour override, so it is appended
# to the agent's own system prompt rather than replacing any of it. Mapping the labels to
# concrete instructions makes them mean something to the model — "Concise" on its own does
# not reliably shorten a reply.
_TONE_DIRECTIVES = {
    "friendly": "Write in a warm, friendly tone.",
    "professional": "Write in a polished, professional tone.",
    "concise": "Keep replies short and to the point; omit filler and preamble.",
    "empathetic": "Acknowledge the person's situation and respond with empathy.",
    "playful": "Write with a light, playful tone while staying accurate and helpful.",
    "technical": "Write precisely and technically; prefer exact terms over simplification.",
}


def tone_directive(persona: dict[str, Any] | None) -> str | None:
    """The style instruction for an agent's configured tone, if any."""
    tone = (persona or {}).get("tone")
    if not isinstance(tone, str) or not tone.strip():
        return None
    tone = tone.strip()
    return _TONE_DIRECTIVES.get(tone.lower()) or f"Write in a {tone} tone."


def compose_system_prompt(system_prompt: str | None, persona: dict[str, Any] | None) -> str | None:
    """Combine the agent's system prompt with its persona-derived style directives.

    Every surface (dashboard chat, widget, channels, playground) builds its prompt through
    this so a persona change takes effect everywhere at once.
    """
    parts = [p for p in (system_prompt or "").strip().split("\n\n") if p.strip()]
    directive = tone_directive(persona)
    if directive:
        parts.append(directive)
    return "\n\n".join(parts) or None


def build_messages(
    *,
    system_prompt: str | None,
    context_block: str,
    memory_summary: str | None,
    history: list[Message],
    user_message: str,
    window_messages: int,
) -> list[Message]:
    """Assemble the message list for a turn, trimming history to the recent window.

    The system prompt and current user turn are never dropped; oldest history is trimmed
    first (the summarized older turns live in ``memory_summary``).
    """
    messages: list[Message] = []
    if system_prompt:
        messages.append(Message(role="system", content=system_prompt))
    if context_block:
        messages.append(Message(role="system", content=context_block))
    if memory_summary:
        messages.append(
            Message(role="system", content=f"Conversation summary so far:\n{memory_summary}")
        )
    # Keep only the most recent `window_messages` history entries.
    window = history[-window_messages:] if window_messages > 0 else []
    messages.extend(window)
    messages.append(Message(role="user", content=user_message))
    return messages
