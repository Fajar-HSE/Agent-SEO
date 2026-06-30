"""TrendsAgent — fetches trending topics and reframes them for HR Competency development using LLM."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class TrendsAgent(BaseAgent):
    """Scrapes raw trends and uses LLM to reframe/filter them for HR competency/training."""

    prompt_name = "trends"  # Loads prompts/trends.txt

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        geo = input_data.get("geo", "ID").upper()

        raw_topics = []

        # 1. Fetch general Google Trends
        try:
            trends = await self._fetch_google_trends(geo)
            raw_topics.extend(trends)
        except Exception as e:
            logger.error(f"[Trends] Failed to fetch Google Trends: {e}")

        # 2. Fetch specific Google News search for HR & Competency
        try:
            news_sdm = await self._fetch_google_news_sdm(geo)
            raw_topics.extend(news_sdm)
        except Exception as e:
            logger.error(f"[Trends] Failed to fetch HR News: {e}")

        # Limit raw input to top 30 items to avoid token bloat
        unique_raw = []
        seen = set()
        for t in raw_topics:
            title_lower = t["title"].lower().strip()
            if title_lower not in seen:
                seen.add(title_lower)
                unique_raw.append(t)
        unique_raw = unique_raw[:30]

        logger.info(f"[Trends] Collected {len(unique_raw)} raw source topics. Passing to LLM for curation...")

        # If LLM function is not available (e.g. testing/dry run/no model)
        if not llm_func:
            return {
                "topics": unique_raw[:10],
                "geo": geo,
                "curated": False,
            }

        # 3. Call LLM to reframe and curate the topics
        messages = self._build_messages({
            "raw_topics": unique_raw,
            "geo": geo,
        })

        try:
            raw_response = await llm_func(
                messages=messages,
                model=self.config.model or "Qwen/Qwen2.5-7B-Instruct",
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            parsed = self._parse_output(raw_response)
            curated_topics = parsed.get("topics", [])
            
            if not curated_topics:
                logger.warning("[Trends] LLM returned empty topic list. Falling back to filtered raw topics.")
                curated_topics = unique_raw[:10]

            return {
                "topics": curated_topics,
                "geo": geo,
                "curated": True,
            }
        except Exception as e:
            logger.exception(f"[Trends] LLM call failed: {e}")
            # Fallback to first 10 raw items
            return {
                "topics": unique_raw[:10],
                "geo": geo,
                "curated": False,
            }

    async def _fetch_google_trends(self, geo: str) -> list[dict[str, Any]]:
        """Fetch and parse Google Trends RSS."""
        url = f"https://trends.google.com/trending/rss?geo={geo}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            xml_data = resp.text

        root = ET.fromstring(xml_data)
        items = []
        ns = {"ht": "http://trends.google.com/trending/rss"}

        for item in root.findall(".//item"):
            title = item.find("title")
            title_text = title.text if title is not None else ""
            if not title_text:
                continue

            approx_traffic = item.find("ht:approx_traffic", ns)
            traffic = approx_traffic.text if approx_traffic is not None else "N/A"

            description = item.find("description")
            desc_text = description.text if description is not None else ""

            items.append({
                "title": title_text.strip(),
                "traffic": traffic,
                "description": desc_text.strip() if desc_text else "",
                "origin": "Google Trends",
            })
        return items

    async def _fetch_google_news_sdm(self, geo: str) -> list[dict[str, Any]]:
        """Fetch and parse Google News Search RSS for HR Competency topics."""
        hl = geo.lower()
        # Search query for HR, Competency, Certifications, Training
        query = "kompetensi SDM OR sertifikasi profesi OR pelatihan kerja OR pengembangan karir"
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl={hl}&gl={geo}&ceid={geo}:{hl}"

        logger.info(f"[Trends] Fetching HR News Search: {url}")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            xml_data = resp.text

        root = ET.fromstring(xml_data)
        items = []

        for item in root.findall(".//item"):
            title = item.find("title")
            title_text = title.text if title is not None else ""
            if not title_text:
                continue

            clean_title = title_text
            if " - " in title_text:
                parts = title_text.rsplit(" - ", 1)
                clean_title = parts[0]

            description = item.find("description")
            desc_text = description.text if description is not None else ""

            items.append({
                "title": clean_title.strip(),
                "traffic": "Trending News",
                "description": "",
                "origin": "Google News (SDM)",
            })
        return items
