"""WebFetcher — fetch and extract readable content from a URL."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Headers to mimic a real browser
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


from urllib.parse import urlparse
import socket

def _is_safe_url(url: str) -> bool:
    """Validate URL to prevent SSRF by blocking local/private IP ranges."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        
        hostname = parsed.hostname
        if not hostname:
            return False
            
        hostname_lower = hostname.lower()
        if hostname_lower in ("localhost", "127.0.0.1", "::1"):
            return False
            
        # Resolve to IP to check for private ranges
        ip = socket.gethostbyname(hostname)
        ip_parts = list(map(int, ip.split('.')))
        
        if len(ip_parts) != 4:
            return False
            
        # RFC 1918 private ranges & Loopback & Link-local
        if (
            ip_parts[0] == 10 or
            (ip_parts[0] == 172 and 16 <= ip_parts[1] <= 31) or
            (ip_parts[0] == 192 and ip_parts[1] == 168) or
            (ip_parts[0] == 169 and ip_parts[1] == 254) or
            ip_parts[0] == 127
        ):
            return False
        return True
    except Exception:
        return False


class WebFetcher:
    """Fetches article content from a URL and returns clean text."""

    def __init__(self, timeout: float = 20.0, max_chars: int = 15000):
        self.timeout = timeout
        self.max_chars = max_chars

    async def fetch(self, url: str) -> dict[str, Any]:
        """
        Fetch URL and return extracted content.

        Returns dict with:
        - url, title, meta_description, content (clean text), word_count,
          headings (list), status_code, error (if any)
        """
        logger.info(f"Fetching: {url}")
        
        if not _is_safe_url(url):
            logger.warning(f"Blocked potential SSRF attempt for URL: {url}")
            return {"url": url, "error": "URL target ditolak karena alasan keamanan (SSRF Protection)", "content": ""}

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=_HEADERS,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text

            return self._parse_html(html, url)

        except httpx.HTTPStatusError as e:
            return {"url": url, "error": f"HTTP {e.response.status_code}", "content": ""}
        except Exception as e:
            return {"url": url, "error": str(e), "content": ""}

    def _parse_html(self, html: str, url: str) -> dict[str, Any]:
        """Extract title, meta, headings, and body text from raw HTML."""
        # ── Title ──────────────────────────────────────────────────
        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if m:
            title = self._clean_text(m.group(1))

        # ── Meta description ────────────────────────────────────────
        meta_desc = ""
        m = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if m:
            meta_desc = self._clean_text(m.group(1))

        # ── Headings ────────────────────────────────────────────────
        headings = []
        for m in re.finditer(r"<h([1-4])[^>]*>(.*?)</h\1>", html, re.IGNORECASE | re.DOTALL):
            level = m.group(1)
            text = self._strip_tags(m.group(2)).strip()
            if text:
                headings.append({"level": f"H{level}", "text": text})

        # ── Main body extraction ────────────────────────────────────
        body = html

        # Remove script, style, nav, header, footer, aside, ads
        for tag in ["script", "style", "nav", "header", "footer", "aside",
                    "noscript", "iframe", "form", "button"]:
            body = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", " ", body, flags=re.IGNORECASE | re.DOTALL)

        # Try to isolate <article>, <main>, or <div class*="content|post|entry|article">
        for pattern in [
            r"<article[^>]*>(.*?)</article>",
            r"<main[^>]*>(.*?)</main>",
            r'<div[^>]+class=["\'][^"\']*(?:post|entry|article|content|body)[^"\']*["\'][^>]*>(.*?)</div>',
        ]:
            m = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
            if m and len(m.group(1)) > 500:
                body = m.group(1)
                break

        # Strip all remaining tags
        content = self._strip_tags(body)

        # Normalize whitespace
        content = re.sub(r"\n{3,}", "\n\n", content)
        content = re.sub(r" {2,}", " ", content)
        content = content.strip()

        # Truncate if too long
        if len(content) > self.max_chars:
            content = content[: self.max_chars] + "\n\n[... konten terpotong ...]"

        word_count = len(content.split())

        logger.info(f"Fetched: '{title}' — {word_count} words, {len(headings)} headings")

        return {
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "headings": headings,
            "content": content,
            "word_count": word_count,
            "error": "",
        }

    @staticmethod
    def _strip_tags(html: str) -> str:
        """Remove all HTML tags."""
        return re.sub(r"<[^>]+>", " ", html)

    @staticmethod
    def _clean_text(text: str) -> str:
        """Decode HTML entities and normalize whitespace."""
        entities = {
            "&amp;": "&", "&lt;": "<", "&gt;": ">",
            "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
            "&ndash;": "–", "&mdash;": "—",
        }
        for ent, char in entities.items():
            text = text.replace(ent, char)
        return re.sub(r"\s+", " ", text).strip()
