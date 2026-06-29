"""FetcherAgent — fetches source article from URL, no LLM needed."""

from __future__ import annotations

import logging
from typing import Any

from agents.base import BaseAgent
from gateway.fetcher import WebFetcher

logger = logging.getLogger(__name__)


class FetcherAgent(BaseAgent):
    """
    Fetches and extracts readable content from a URL.
    Does NOT call LLM — pure HTTP fetch + HTML parsing.

    Input:
    - keyword: the URL to fetch (passed as --keyword in CLI)
    - source_url: alternative key for URL

    Output:
    - url, title, meta_description, content, word_count, headings, error
    """

    prompt_name = ""  # No LLM needed

    def __init__(self, config_path: str | None = None):
        super().__init__(config_path)
        self.fetcher = WebFetcher(timeout=25.0, max_chars=12000)

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        # Accept URL from either 'keyword' or 'source_url'
        url = (
            input_data.get("source_url", "")
            or input_data.get("keyword", "")
        ).strip()

        if not url:
            raise ValueError("No URL provided. Pass URL as --keyword or source_url")

        # Validate looks like a URL
        if not url.startswith(("http://", "https://")):
            raise ValueError(
                f"Input '{url[:60]}' does not look like a URL. "
                "For rewrite workflow, --keyword should be the article URL."
            )

        logger.info(f"[Fetcher] Fetching: {url}")
        result = await self.fetcher.fetch(url)

        if result.get("error"):
            raise RuntimeError(f"[Fetcher] Failed to fetch '{url}': {result['error']}")

        if not result.get("content") or len(result["content"]) < 200:
            raise RuntimeError(
                f"[Fetcher] Content too short ({len(result.get('content',''))} chars). "
                "The page may require JavaScript rendering or blocked bot access."
            )

        logger.info(
            f"[Fetcher] OK: '{result['title']}' "
            f"— {result['word_count']} words, {len(result['headings'])} headings"
        )

        return {
            "url": result["url"],
            "title": result["title"],
            "meta_description": result["meta_description"],
            "headings": result["headings"],
            "content": result["content"],
            "word_count": result["word_count"],
        }
