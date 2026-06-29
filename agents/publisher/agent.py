"""Publisher agent — publishes approved content to WordPress via REST API."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class PublisherAgent(BaseAgent):
    """
    Publishes article to WordPress via REST API.

    Required environment variables:
        WP_URL      — WordPress site URL, e.g. https://example.com
        WP_USERNAME — WordPress username (Application Password user)
        WP_APP_PASSWORD — WordPress Application Password (no spaces)

    Publishes as 'draft' by default; set publish_status='publish' to go live.
    """

    prompt_name = "publisher"

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        title = input_data.get("title", "Untitled Article")
        content = input_data.get("content", input_data.get("optimized_content", ""))
        excerpt = input_data.get("excerpt", "")
        meta_title = input_data.get("meta_title", title)
        meta_description = input_data.get("meta_description", excerpt)
        publish_status = input_data.get("publish_status", "draft")
        tags = input_data.get("tags", [])
        categories = input_data.get("categories", [])

        # Check if WordPress credentials are configured
        wp_url = os.environ.get("WP_URL", "").rstrip("/")
        wp_user = os.environ.get("WP_USERNAME", "")
        wp_pass = os.environ.get("WP_APP_PASSWORD", "")

        if not all([wp_url, wp_user, wp_pass]):
            logger.warning("WordPress credentials not configured — saving as draft locally")
            return {
                "published": False,
                "post_id": 0,
                "url": "",
                "status": "local_draft",
                "message": (
                    "WordPress credentials not configured. "
                    "Set WP_URL, WP_USERNAME, WP_APP_PASSWORD env vars."
                ),
                "title": title,
                "content_length": len(content),
            }

        try:
            post_id, post_url = await self._publish_to_wordpress(
                wp_url=wp_url,
                username=wp_user,
                app_password=wp_pass,
                title=title,
                content=content,
                excerpt=excerpt,
                status=publish_status,
                tags=tags,
                categories=categories,
            )
            logger.info(f"Published to WordPress: post_id={post_id}, url={post_url}")
            return {
                "published": True,
                "post_id": post_id,
                "url": post_url,
                "status": publish_status,
                "message": f"Article '{title}' published successfully as {publish_status}",
                "meta_title": meta_title,
                "meta_description": meta_description,
            }
        except Exception as e:
            logger.error(f"WordPress publish failed: {e}")
            return {
                "published": False,
                "post_id": 0,
                "url": "",
                "status": "failed",
                "message": f"Publish failed: {e}",
            }

    async def _publish_to_wordpress(
        self,
        wp_url: str,
        username: str,
        app_password: str,
        title: str,
        content: str,
        excerpt: str,
        status: str,
        tags: list,
        categories: list,
    ) -> tuple[int, str]:
        """Send POST request to WordPress REST API."""
        endpoint = f"{wp_url}/wp-json/wp/v2/posts"

        # Basic auth with Application Password
        credentials = f"{username}:{app_password}"
        token = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": status,
        }
        if categories:
            payload["categories"] = categories
        if tags:
            payload["tags"] = tags

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        post_id = data.get("id", 0)
        post_url = data.get("link", "")
        return post_id, post_url
