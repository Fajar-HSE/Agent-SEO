"""ApprovalAgent — human-in-the-loop approval step."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ApprovalAgent(BaseAgent):
    """
    Pauses workflow for human review.

    Behavior:
    - In CI/headless mode (NO_HUMAN_APPROVAL=1 env var): auto-approves if quality >= threshold.
    - In interactive mode: prompts the user in the terminal to approve/reject/edit.

    The agent does NOT call the LLM — it's purely a human checkpoint.
    """

    prompt_name = ""  # No prompt needed
    AUTO_APPROVE_THRESHOLD = 0.75  # quality_score / 100

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        quality_score = float(input_data.get("quality_score", 0))
        approved_by_reviewer = input_data.get("approved", False)
        feedback = input_data.get("feedback", "")
        title = input_data.get("title", input_data.get("meta_title", "Article"))
        issues = input_data.get("issues", [])

        # Check for headless/CI mode
        no_human = os.environ.get("NO_HUMAN_APPROVAL", "").lower() in ("1", "true", "yes")

        if no_human:
            return self._auto_approve(
                quality_score, approved_by_reviewer, title, feedback
            )

        # Interactive approval
        return await self._interactive_approve(
            title, quality_score, approved_by_reviewer, feedback, issues, input_data
        )

    def _auto_approve(
        self,
        quality_score: float,
        approved_by_reviewer: bool,
        title: str,
        feedback: str,
    ) -> dict[str, Any]:
        """Auto-approve based on quality score (headless/CI mode)."""
        threshold = self.AUTO_APPROVE_THRESHOLD * 100
        auto_approved = approved_by_reviewer and quality_score >= threshold

        action = "approved" if auto_approved else "rejected"
        reason = (
            f"Auto-{'approved' if auto_approved else 'rejected'}: "
            f"quality_score={quality_score:.0f}, "
            f"reviewer_approved={approved_by_reviewer}, "
            f"threshold={threshold:.0f}"
        )
        logger.info(f"[Approval] {reason}")

        return {
            "approved": auto_approved,
            "action": action,
            "approver": "auto",
            "reason": reason,
            "quality_score": quality_score,
            "timestamp": time.time(),
        }

    async def _interactive_approve(
        self,
        title: str,
        quality_score: float,
        approved_by_reviewer: bool,
        feedback: str,
        issues: list,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Show article summary to human and wait for decision."""
        print("\n" + "=" * 70)
        print("  HUMAN APPROVAL REQUIRED")
        print("=" * 70)
        print(f"  Article  : {title}")
        print(f"  Quality  : {quality_score:.0f}/100")
        print(f"  Reviewer : {'✓ Approved' if approved_by_reviewer else '✗ Not approved'}")
        if feedback:
            print(f"  Feedback : {feedback[:120]}")
        if issues:
            print(f"  Issues   : {len(issues)} found")
            for issue in issues[:3]:
                sev = issue.get("severity", "?")
                desc = issue.get("description", "")
                print(f"             [{sev}] {desc[:80]}")
        print("-" * 70)
        print("  Options:")
        print("    [a] Approve and continue to publish")
        print("    [r] Reject (stop workflow)")
        print("    [s] Skip approval (auto-approve)")
        print("    [v] View full content")
        print("=" * 70)

        while True:
            try:
                choice = input("  Your choice [a/r/s/v]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "r"

            if choice == "a":
                return {
                    "approved": True,
                    "action": "approved",
                    "approver": "human",
                    "reason": "Manually approved by human reviewer",
                    "quality_score": quality_score,
                    "timestamp": time.time(),
                }
            elif choice == "r":
                reason = ""
                try:
                    reason = input("  Rejection reason (optional): ").strip()
                except (EOFError, KeyboardInterrupt):
                    pass
                return {
                    "approved": False,
                    "action": "rejected",
                    "approver": "human",
                    "reason": reason or "Rejected by human reviewer",
                    "quality_score": quality_score,
                    "timestamp": time.time(),
                }
            elif choice == "s":
                return {
                    "approved": True,
                    "action": "skipped",
                    "approver": "human_skip",
                    "reason": "Approval skipped by reviewer",
                    "quality_score": quality_score,
                    "timestamp": time.time(),
                }
            elif choice == "v":
                content = input_data.get(
                    "optimized_content",
                    input_data.get("content", "No content available"),
                )
                print("\n--- CONTENT PREVIEW (first 2000 chars) ---")
                print(content[:2000])
                print("--- END PREVIEW ---\n")
            else:
                print("  Invalid option. Please enter a, r, s, or v.")
