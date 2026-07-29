"""URL ingest extracts the *article*, not the whole page chrome.

The regex strip this replaced had no notion of document structure, so a docs site's nav
menu landed in the same text stream as the content and dominated the first chunk. The
fixture is the real https://docs.n8n.io/ — the page that surfaced the bug — so the
regression can't quietly come back.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.rag.chunking import chunk_text
from app.rag.loaders import extract_main_content, load_url, strip_html

FIXTURE = Path(__file__).parent / "fixtures" / "docs-n8n-io.html"

#: Nav/header/footer labels that surround the article on docs.n8n.io. None of these are
#: content; if they reappear, boilerplate is leaking into the ingest again.
NAV_NOISE = ("Changelog", "Get started", "Deploy", "Contribute", "Forum")


@pytest.fixture(scope="module")
def n8n_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_the_old_behaviour_really_was_nav_dominated(n8n_html: str) -> None:
    """Pins the bug itself, so this test file documents what was wrong."""
    old = strip_html(n8n_html)
    # The nav menu is the first thing in the stream — before any article text.
    assert "Forum" in old[:300]
    assert "Changelog" in old[:300]
    assert sum(old[:1500].count(n) for n in NAV_NOISE) >= 5


def test_extraction_drops_the_nav_and_keeps_the_article(n8n_html: str) -> None:
    text = extract_main_content(n8n_html, "https://docs.n8n.io/")

    for noise in NAV_NOISE:
        assert noise not in text, f"nav label {noise!r} leaked into the extracted content"

    # The actual lede survives.
    assert "workflow automation" in text.lower()
    assert "n8n" in text


def test_the_first_chunk_is_content_not_a_menu(n8n_html: str) -> None:
    """What the bug actually cost: the first chunk is what retrieval most often returns."""
    chunks = chunk_text(extract_main_content(n8n_html, "https://docs.n8n.io/"), 1000, 150)
    assert chunks, "extraction produced nothing to chunk"
    first = chunks[0].content
    assert not any(noise in first for noise in NAV_NOISE)
    assert "workflow automation" in first.lower()


def test_headings_are_preserved_for_chunk_boundaries(n8n_html: str) -> None:
    """Markdown output gives the recursive chunker structure to split on."""
    assert "# " in extract_main_content(n8n_html, "https://docs.n8n.io/")


def test_falls_back_to_strip_html_for_a_page_it_cannot_parse() -> None:
    """A stub page must still ingest — today's behaviour beats failing outright."""
    bare = "<html><body><p>Tiny page.</p></body></html>"
    out = extract_main_content(bare, "https://example.com/")
    assert "Tiny page." in out
    assert "<" not in out


def test_malformed_html_does_not_raise() -> None:
    out = extract_main_content("<html><body><p>unclosed", "https://example.com/")
    assert "unclosed" in out


async def test_load_url_uses_main_content_extraction(n8n_html: str) -> None:
    """The whole path, through the real loader, with the network mocked."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=n8n_html, headers={"content-type": "text/html"})

    text = await load_url("https://docs.n8n.io/", transport=httpx.MockTransport(handler))
    assert "workflow automation" in text.lower()
    for noise in NAV_NOISE:
        assert noise not in text


async def test_non_html_content_is_untouched() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="plain, not markup", headers={"content-type": "text/plain"})

    text = await load_url("https://example.com/a.txt", transport=httpx.MockTransport(handler))
    assert text == "plain, not markup"
