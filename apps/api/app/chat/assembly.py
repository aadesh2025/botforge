"""Prompt assembly (docs/06 §2 order):

`[system persona + guardrails]` → `[retrieved context]` → `[long-term memory summary]` →
`[recent message window]` → `[current user turn]`.
"""

from __future__ import annotations

from app.llm.types import Message


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
