"""
RewriterAgent — AEO/GEO/E-E-A-T article rewrite skill.

Implements the full Non-Commodity Content Framework:
1. Fetch source article from URL
2. Diagnose weaknesses
3. Reframe strategy
4. Write rewrite with all required components
5. Generate SEO metadata + internal link recommendations
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from agents.base import BaseAgent
from gateway.fetcher import WebFetcher

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RewriterAgent(BaseAgent):
    """
    Rewrites an existing article (from URL) into an AEO/GEO-optimized version.

    Input keys:
    - source_url (required): URL of the article to rewrite
    - target_keyword (optional): override detected keyword
    - extra_context (optional): real data, brand voice, or case studies from user
    - language (optional): "id" | "en" — defaults to "id"

    Output keys:
    - title, meta_description, slug, focus_keyword
    - content (full Markdown article)
    - diagnosis (source article weaknesses)
    - seo_metadata (full SEO block)
    - internal_links (recommendations)
    - word_count, excerpt
    - source_title, source_url
    """

    prompt_name = "rewriter"

    def __init__(self, config_path: str | None = None):
        super().__init__(config_path)
        self.fetcher = WebFetcher(timeout=25.0, max_chars=12000)
        self._diagnosis_prompt = self._load_prompt_file("aeo_diagnosis.txt")

    def _load_prompt_file(self, filename: str) -> str:
        """Load a named prompt file from prompts/ directory."""
        path = os.path.join(_ROOT, "prompts", filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        logger.warning(f"Prompt file not found: {path}")
        return ""

    # ──────────────────────────────────────────────────────────────────────
    # Main execution
    # ──────────────────────────────────────────────────────────────────────

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        source_url = input_data.get("source_url", "").strip()
        target_keyword = input_data.get("target_keyword", "").strip()
        extra_context = input_data.get("extra_context", "").strip()
        language = input_data.get("language", "id")

        if not source_url:
            raise ValueError("source_url is required for RewriterAgent")

        # ── Step 1: Fetch source article ────────────────────────────
        logger.info(f"[Rewriter] Fetching source article: {source_url}")
        fetched = await self.fetcher.fetch(source_url)

        if fetched.get("error"):
            raise RuntimeError(f"Failed to fetch article: {fetched['error']}")

        if not fetched.get("content") or len(fetched["content"]) < 200:
            raise RuntimeError(
                "Fetched content too short — page may require JavaScript or be blocked"
            )

        logger.info(
            f"[Rewriter] Fetched: '{fetched['title']}' "
            f"({fetched['word_count']} words, {len(fetched['headings'])} headings)"
        )

        # ── Step 2: Diagnose source article ─────────────────────────
        diagnosis_result = await self._diagnose(fetched, language, llm_func)
        detected_keyword = (
            target_keyword
            or diagnosis_result.get("detected_keyword", "")
            or fetched.get("title", "")
        )

        logger.info(
            f"[Rewriter] Diagnosis complete — AEO score: "
            f"{diagnosis_result.get('aeo_readiness_score', 0)}/100, "
            f"keyword: '{detected_keyword}'"
        )

        # ── Step 3: Rewrite ─────────────────────────────────────────
        rewrite_input = {
            "source_url": source_url,
            "source_title": fetched["title"],
            "source_content": fetched["content"],
            "source_headings": fetched["headings"],
            "target_keyword": detected_keyword,
            "secondary_keywords": diagnosis_result.get("detected_secondary_keywords", []),
            "extra_context": extra_context,
            "language": language,
            "diagnosis_summary": diagnosis_result.get("top_weaknesses", []),
            "reframe_opportunity": diagnosis_result.get("reframe_opportunity", ""),
            "target_audience": diagnosis_result.get("target_audience", ""),
        }

        messages = self._build_messages(rewrite_input)
        logger.info("[Rewriter] Generating rewrite...")

        raw = await llm_func(
            messages=messages,
            model=self.config.model,
            temperature=0.75,        # slightly creative for hooks & insights
            max_tokens=6000,         # long-form article
        )

        parsed = self._parse_output(raw)

        # ── Step 4: Assemble output ──────────────────────────────────
        content = parsed.get("content", parsed.get("raw_text", ""))

        # Unwrap nested JSON — models sometimes return the whole article JSON
        # as a string value inside the outer JSON
        if isinstance(content, str) and content.strip().startswith("{"):
            try:
                inner = json.loads(content.strip())
                if isinstance(inner, dict) and inner.get("content"):
                    parsed.update(inner)
                    content = inner.get("content", content)
            except (json.JSONDecodeError, Exception):
                pass

        # Also check if parsed itself has a nested JSON string as raw_text
        if not content or (isinstance(content, str) and content.strip().startswith("{")):
            raw_text = parsed.get("raw_text", "")
            if raw_text and not raw_text.strip().startswith("{"):
                content = raw_text

        # Pull updated fields from parsed after any unwrapping
        title = parsed.get("title", "")
        meta_description = parsed.get("meta_description", "")
        slug = parsed.get("slug", "")
        focus_keyword = parsed.get("focus_keyword", detected_keyword)
        secondary_keywords = parsed.get("secondary_keywords", [])
        excerpt = parsed.get("excerpt", "")
        seo_meta = parsed.get("seo_metadata", {})
        int_links = parsed.get("internal_links", {})
        word_count = len(content.split()) if content else 0

        # Inject actual word count into seo_metadata
        seo_meta["word_count"] = word_count

        return {
            "source_url": source_url,
            "source_title": fetched["title"],
            "title": title or fetched["title"],
            "meta_description": meta_description,
            "slug": slug,
            "focus_keyword": focus_keyword,
            "secondary_keywords": secondary_keywords,
            "content": content,
            "excerpt": excerpt,
            "word_count": word_count,
            "diagnosis": {
                "source_diagnosis": diagnosis_result,
                "rewrite_diagnosis": parsed.get("diagnosis", {}),
            },
            "seo_metadata": seo_meta,
            "internal_links": int_links,
            "aeo_readiness_score_before": diagnosis_result.get("aeo_readiness_score", 0),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Diagnosis step
    # ──────────────────────────────────────────────────────────────────────

    async def _diagnose(
        self,
        fetched: dict[str, Any],
        language: str,
        llm_func,
    ) -> dict[str, Any]:
        """Run quick diagnosis on the source article."""
        if not self._diagnosis_prompt:
            # Fallback: minimal diagnosis without LLM
            return {
                "top_weaknesses": [
                    "Diagnosis prompt not found — proceeding with rewrite directly"
                ],
                "detected_keyword": "",
                "aeo_readiness_score": 0,
            }

        diag_input = {
            "source_url": fetched["url"],
            "source_title": fetched["title"],
            "source_content": fetched["content"][:4000],  # truncate for diagnosis
            "source_headings": fetched["headings"],
            "language": language,
        }

        messages = [
            {"role": "system", "content": self._diagnosis_prompt},
            {"role": "user", "content": json.dumps(diag_input, ensure_ascii=False, indent=2)},
        ]

        try:
            raw = await llm_func(
                messages=messages,
                model=self.config.model,
                temperature=0.3,
                max_tokens=1500,
            )
            result = self._parse_output(raw)
            if isinstance(result, dict) and "top_weaknesses" in result:
                return result
        except Exception as e:
            logger.warning(f"[Rewriter] Diagnosis LLM call failed: {e}")

        return {
            "top_weaknesses": ["Diagnosis skipped"],
            "detected_keyword": "",
            "aeo_readiness_score": 0,
        }
