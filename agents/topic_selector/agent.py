"""TopicSelectorAgent — interactive selection of trending topics."""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class TopicSelectorAgent(BaseAgent):
    """Presents a list of trending topics and lets the user choose one."""

    prompt_name = ""  # No LLM needed for this step

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        topics = input_data.get("topics", [])
        if not topics:
            raise ValueError("No trending topics found to select from.")

        # Check for headless/CI mode
        no_human = os.environ.get("NO_HUMAN_APPROVAL", "").lower() in ("1", "true", "yes")

        if no_human:
            selected = topics[0]
            logger.info(f"[TopicSelector] Auto-selected top trend: {selected['title']}")
            return {
                "selected_topic": selected["title"],
                "topic_details": selected,
                "keyword": selected["title"],
                "timestamp": time.time(),
            }

        # Interactive Terminal selector
        print("\n" + "=" * 70)
        print("  PILIH TOPIK YANG SEDANG TREN / VIRAL")
        print("=" * 70)
        for idx, item in enumerate(topics, 1):
            origin_str = f"[{item.get('origin', 'Trends')}]"
            print(f"  [{idx}] {item['title']} - {origin_str}")
            if item.get("traffic") and item["traffic"] != "N/A":
                print(f"      Pencarian: {item['traffic']}")
            if item.get("description"):
                print(f"      Konteks: {item['description']}")
            print("-" * 70)

        while True:
            try:
                choice = input(f"  Pilih topik [1-{len(topics)}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                # Fallback to first trend if input is interrupted
                selected = topics[0]
                return {
                    "selected_topic": selected["title"],
                    "topic_details": selected,
                    "keyword": selected["title"],
                    "timestamp": time.time(),
                }

            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(topics):
                    selected = topics[choice_idx]
                    print(f"\n  👉 Pilihan Anda: {selected['title']}\n")
                    return {
                        "selected_topic": selected["title"],
                        "topic_details": selected,
                        "keyword": selected["title"],
                        "timestamp": time.time(),
                    }
                else:
                    print(f"  Pilihan salah. Harap pilih angka 1-{len(topics)}.")
            except ValueError:
                print("  Input tidak valid. Harap masukkan angka indeks.")
