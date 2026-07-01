"""Keyword agent — 3-layer architecture: Data Harvest → LLM Reasoning → Validation."""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from agents.base import BaseAgent

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

VALID_INTENTS = {"informational", "commercial", "transactional", "navigational"}


class KeywordAgent(BaseAgent):
    """
    3-Layer Keyword Research Agent:
      Layer 1 — Data Harvest   : Google Autocomplete + SERP heading scraper (no LLM)
      Layer 2 — LLM Reasoning  : Analysis & clustering of harvested data
      Layer 3 — Validation     : Schema validation, fallbacks, quality signals
    """

    prompt_name = "keyword"

    # ──────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ──────────────────────────────────────────────────────────────

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        seed_keyword = (
            input_data.get("keyword")
            or input_data.get("primary_keyword")
            or input_data.get("selected_topic")
            or ""
        ).strip()

        if not seed_keyword:
            logger.warning("[Keyword] No seed keyword provided, using empty string")

        # ── Layer 1: Data Harvest ──────────────────────────────────
        logger.info(f"[Keyword] Layer 1 — Harvesting data for: '{seed_keyword}'")
        harvested = await self._harvest_data(seed_keyword)
        logger.info(
            f"[Keyword] Harvested: {len(harvested['autocomplete_suggestions'])} autocomplete, "
            f"{len(harvested['serp_headings'])} SERP headings"
        )

        # ── Layer 2: LLM Reasoning ────────────────────────────────
        logger.info("[Keyword] Layer 2 — LLM reasoning on harvested data")
        enriched_input = {
            **input_data,
            "seed_keyword": seed_keyword,
            "autocomplete_suggestions": harvested["autocomplete_suggestions"],
            "serp_headings": harvested["serp_headings"],
            "competitor_titles": harvested["competitor_titles"],
            "people_also_ask_hints": harvested["people_also_ask_hints"],
            "data_sources_used": harvested["sources"],
        }
        messages = self._build_messages(enriched_input)
        raw = await llm_func(
            messages=messages,
            model=self.config.model,
            temperature=0.4,          # lower temp for more deterministic keyword reasoning
            max_tokens=self.config.max_tokens,
        )
        parsed = self._parse_output(raw)

        # ── Layer 3: Validation ────────────────────────────────────
        logger.info("[Keyword] Layer 3 — Validating output")
        validated = self._validate_output(parsed, seed_keyword, harvested)

        return validated

    # ──────────────────────────────────────────────────────────────
    # LAYER 1 — DATA HARVEST
    # ──────────────────────────────────────────────────────────────

    async def _harvest_data(self, keyword: str) -> dict[str, Any]:
        """Run all data harvest tasks concurrently."""
        autocomplete_task = self._get_autocomplete(keyword)
        serp_task = self._scrape_serp_headings(keyword)

        results = await asyncio.gather(
            autocomplete_task, serp_task, return_exceptions=True
        )

        autocomplete = results[0] if not isinstance(results[0], Exception) else []
        serp_data = results[1] if not isinstance(results[1], Exception) else {}

        if isinstance(results[0], Exception):
            logger.warning(f"[Keyword] Autocomplete failed: {results[0]}")
        if isinstance(results[1], Exception):
            logger.warning(f"[Keyword] SERP scrape failed: {results[1]}")

        sources = []
        if autocomplete:
            sources.append("google_autocomplete")
        if serp_data.get("headings"):
            sources.append("serp_heading_scraper")
        sources.append("llm_reasoning")

        return {
            "autocomplete_suggestions": autocomplete,
            "serp_headings": serp_data.get("headings", []),
            "competitor_titles": serp_data.get("titles", []),
            "people_also_ask_hints": self._extract_paa_hints(autocomplete, keyword),
            "sources": sources,
        }

    async def _get_autocomplete(self, keyword: str) -> list[str]:
        """
        Fetch Google Autocomplete suggestions.
        Uses the public Toolbar endpoint — no API key required.
        Returns list of suggestion strings.
        """
        suggestions = []
        queries = [
            keyword,
            f"{keyword} adalah",
            f"{keyword} cara",
            f"apa itu {keyword}",
            f"manfaat {keyword}",
        ]

        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            for q in queries[:3]:   # limit to 3 queries to avoid rate limiting
                try:
                    encoded = quote_plus(q)
                    url = (
                        f"https://suggestqueries.google.com/complete/search"
                        f"?q={encoded}&hl=id&gl=id&output=toolbar"
                    )
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        # Parse XML response
                        root = ET.fromstring(resp.text)
                        for suggestion in root.iter("suggestion"):
                            data = suggestion.get("data", "")
                            if data and data not in suggestions:
                                suggestions.append(data)
                    await asyncio.sleep(0.3)   # polite delay
                except Exception as e:
                    logger.debug(f"[Keyword] Autocomplete query '{q}' failed: {e}")
                    continue

        return suggestions[:20]    # cap at 20 suggestions

    async def _scrape_serp_headings(self, keyword: str) -> dict[str, list[str]]:
        """
        Scrape DuckDuckGo HTML results to extract competitor page titles.
        DDG is more scraping-friendly than Google. Returns top title/heading data.
        """
        titles = []
        headings = []
        try:
            encoded = quote_plus(keyword)
            url = f"https://html.duckduckgo.com/html/?q={encoded}&kl=id-id"

            async with httpx.AsyncClient(
                timeout=15.0,
                headers=_HEADERS,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)

            if resp.status_code != 200:
                return {"titles": [], "headings": []}

            html = resp.text

            # Extract result titles from DDG HTML results
            title_pattern = re.compile(
                r'class="result__a"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
            )
            for m in title_pattern.finditer(html):
                raw = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if raw and len(raw) > 5 and raw not in titles:
                    titles.append(raw)

            # Extract snippet text as heading proxies
            snippet_pattern = re.compile(
                r'class="result__snippet"[^>]*>(.*?)</[^>]+>', re.IGNORECASE | re.DOTALL
            )
            for m in snippet_pattern.finditer(html):
                raw = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if raw and len(raw) > 20 and raw not in headings:
                    headings.append(raw[:120])

        except Exception as e:
            logger.warning(f"[Keyword] SERP scrape error: {e}")

        return {"titles": titles[:10], "headings": headings[:15]}

    def _extract_paa_hints(self, suggestions: list[str], keyword: str) -> list[str]:
        """
        Derive 'People Also Ask' style questions from autocomplete suggestions.
        Filters suggestions that start with question words.
        """
        question_starters = ("apa", "bagaimana", "cara", "berapa", "mengapa",
                              "kenapa", "siapa", "kapan", "dimana", "apakah",
                              "how", "what", "why", "when", "where")
        paa = []
        for s in suggestions:
            s_lower = s.lower().strip()
            if any(s_lower.startswith(q) for q in question_starters):
                # Format as a question
                question = s.strip()
                if not question.endswith("?"):
                    question += "?"
                if question not in paa:
                    paa.append(question)
        return paa[:8]

    # ──────────────────────────────────────────────────────────────
    # LAYER 3 — VALIDATION
    # ──────────────────────────────────────────────────────────────

    def _validate_output(
        self,
        parsed: dict[str, Any],
        seed: str,
        harvested: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate LLM output, apply fallbacks, and enrich with harvest data."""
        errors: list[str] = []
        warnings: list[str] = []

        # ── primary_keyword ────────────────────────────────────────
        pk = parsed.get("primary_keyword", "").strip()
        if not pk:
            pk = seed
            errors.append("primary_keyword kosong — fallback ke seed keyword")
        elif len(pk) < 3:
            pk = seed
            errors.append("primary_keyword terlalu pendek — fallback ke seed keyword")
        parsed["primary_keyword"] = pk

        # ── secondary_keywords ────────────────────────────────────
        sec = [k for k in parsed.get("secondary_keywords", []) if isinstance(k, str) and k.strip()]
        if len(sec) < 3:
            # Enrich from autocomplete if LLM gave too few
            extras = [s for s in harvested["autocomplete_suggestions"] if s not in sec]
            sec = (sec + extras)[:8]
            warnings.append(f"secondary_keywords diperkaya dari autocomplete data")
        parsed["secondary_keywords"] = sec[:8]

        # ── long_tail_keywords ────────────────────────────────────
        lt = [k for k in parsed.get("long_tail_keywords", []) if isinstance(k, str) and k.strip()]
        if len(lt) < 3:
            extras = [
                s for s in harvested["autocomplete_suggestions"]
                if s not in lt and len(s.split()) >= 3
            ]
            lt = (lt + extras)[:10]
            warnings.append("long_tail_keywords diperkaya dari autocomplete data")
        parsed["long_tail_keywords"] = lt[:10]

        # ── search_intent ─────────────────────────────────────────
        intent = parsed.get("search_intent", "").lower().strip()
        if intent not in VALID_INTENTS:
            parsed["search_intent"] = "informational"
            errors.append(f"search_intent '{intent}' tidak valid — fallback ke informational")

        # ── keyword_clusters ─────────────────────────────────────
        clusters = parsed.get("keyword_clusters", [])
        if not clusters or not isinstance(clusters, list):
            # Build a minimal cluster from available data
            parsed["keyword_clusters"] = [
                {
                    "theme": "Topik Utama",
                    "keywords": sec[:4],
                    "intent": parsed["search_intent"],
                }
            ]
            warnings.append("keyword_clusters fallback — dibuat dari secondary_keywords")

        # ── people_also_ask ───────────────────────────────────────
        paa = parsed.get("people_also_ask", [])
        if not paa:
            paa = harvested["people_also_ask_hints"]
            parsed["people_also_ask"] = paa
            if paa:
                warnings.append("people_also_ask diambil dari harvest data (autocomplete)")

        # ── topical_gaps ──────────────────────────────────────────
        gaps = parsed.get("topical_gaps", [])
        if not gaps:
            parsed["topical_gaps"] = []
            warnings.append("topical_gaps tidak terisi — perlu ditambahkan manual")

        # ── featured_snippet_queries ──────────────────────────────
        fsq = parsed.get("featured_snippet_queries", [])
        if not fsq:
            # Derive from PAA and autocomplete
            parsed["featured_snippet_queries"] = paa[:4]

        # ── semantic_entities ─────────────────────────────────────
        entities = parsed.get("semantic_entities", [])
        if not entities:
            warnings.append("semantic_entities kosong — perlu ditambahkan manual")

        # ── opportunity_score (1-10) ──────────────────────────────
        score = parsed.get("opportunity_score")
        if not isinstance(score, (int, float)) or not (1 <= score <= 10):
            # Heuristic: more autocomplete data = more opportunity signals
            n = len(harvested["autocomplete_suggestions"])
            parsed["opportunity_score"] = min(10, max(3, n // 2))
            warnings.append("opportunity_score dihitung secara heuristik")

        # ── data_sources ──────────────────────────────────────────
        parsed["data_sources"] = harvested["sources"]

        # ── validation meta ───────────────────────────────────────
        parsed["_validation_passed"] = len(errors) == 0
        parsed["_validation_errors"] = errors
        parsed["_validation_warnings"] = warnings

        if errors:
            logger.warning(f"[Keyword] Validation errors: {errors}")
        if warnings:
            logger.info(f"[Keyword] Validation warnings: {warnings}")

        return parsed
