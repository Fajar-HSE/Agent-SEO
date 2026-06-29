"""Monitor agent — tracks workflow metrics and health."""

from __future__ import annotations

import time
from typing import Any

from agents.base import BaseAgent


class MonitorAgent(BaseAgent):
    """Tracks execution metrics, errors, costs, and performance."""

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        workflow_id = input_data.get("workflow_id", "unknown")
        steps = input_data.get("steps_results", [])

        total_tokens = sum(s.get("tokens_used", 0) for s in steps)
        failed_steps = sum(1 for s in steps if s.get("status") == "failed")
        avg_confidence = (
            sum(s.get("confidence", 0) for s in steps) / len(steps) if steps else 0
        )

        return {
            "workflow_id": workflow_id,
            "total_steps": len(steps),
            "failed_steps": failed_steps,
            "total_tokens": total_tokens,
            "avg_confidence": round(avg_confidence, 3),
            "health": "healthy" if failed_steps == 0 else "degraded",
            "timestamp": time.time(),
        }
