"""Document loaders — extract plain text by source type / mime type (docs/06 §2)."""

from __future__ import annotations

import csv
import io
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

from app.core.logging import get_logger

log = get_logger("rag.loaders")

_TAG_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANKLINES_RE = re.compile(r"\n\s*\n\s*")


class LoaderError(Exception):
    """Raised when a document cannot be parsed into text."""


def strip_html(html: str) -> str:
    html = _TAG_RE.sub(" ", html)
    text = _HTML_RE.sub(" ", html)
    text = _WS_RE.sub(" ", text)
    return _BLANKLINES_RE.sub("\n\n", text).strip()


def _is_blocked_host(host: str) -> bool:
    """SSRF guard: reject loopback / private / link-local / reserved destinations."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


async def load_url(url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise LoaderError("Only http(s) URLs are supported.")
    # Skip the SSRF DNS check when a test transport is injected (no real network).
    if transport is None and _is_blocked_host(parsed.hostname):
        raise LoaderError("Refusing to fetch a private/loopback URL.")
    async with httpx.AsyncClient(
        timeout=30.0, follow_redirects=True, transport=transport
    ) as client:
        resp = await client.get(url, headers={"User-Agent": "BotForge-Ingest/1.0"})
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        body = resp.text
    if "html" in content_type or body.lstrip().lower().startswith(("<!doctype", "<html")):
        return strip_html(body)
    return body.strip()


def load_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p)


def load_docx(data: bytes) -> str:
    import docx  # python-docx

    document = docx.Document(io.BytesIO(data))
    return "\n\n".join(p.text for p in document.paragraphs if p.text.strip())


def load_csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return ""
    header, *body = rows
    lines = []
    for row in body:
        pairs = [f"{h}: {v}" for h, v in zip(header, row, strict=False) if v]
        if pairs:
            lines.append("; ".join(pairs))
    return "\n".join(lines) if lines else "\n".join(", ".join(r) for r in rows)


def load_bytes(data: bytes, *, filename: str | None, mime_type: str | None) -> str:
    """Dispatch to a parser by mime type / extension."""
    name = (filename or "").lower()
    mime = (mime_type or "").lower()
    if "pdf" in mime or name.endswith(".pdf"):
        return load_pdf(data)
    if "word" in mime or "officedocument.wordprocessing" in mime or name.endswith(".docx"):
        return load_docx(data)
    if "csv" in mime or name.endswith(".csv"):
        return load_csv(data)
    # txt, markdown, json, or anything else → decode as text.
    return data.decode("utf-8", errors="replace").strip()
