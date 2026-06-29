"""Monitor agent — tracks workflow metrics and health."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class MonitorAgent(BaseAgent):
    """
    Tracks execution metrics, errors, costs, and performance.
    Writes a JSON report to logs/monitor_<workflow_id>.json.
    """

    prompt_name = "monitor"

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        workflow_id = input_data.get("workflow_id", "unknown")
        steps = input_data.get("steps_results", [])
        router_usage = input_data.get("router_usage", {})

        # Aggregate metrics
        total_tokens = router_usage.get("total_tokens", 0) or sum(
            s.get("tokens_used", 0) for s in steps
        )
        total_cost = router_usage.get("total_cost_usd", 0.0)
        failed_steps = [s for s in steps if s.get("status") == "failed"]
        completed_steps = [s for s in steps if s.get("status") == "completed"]

        avg_confidence = (
            sum(s.get("confidence", 0) for s in completed_steps) / len(completed_steps)
            if completed_steps
            else 0.0
        )
        avg_latency = (
            sum(s.get("elapsed_s", 0) for s in steps) / len(steps)
            if steps
            else 0.0
        )
        total_elapsed = sum(s.get("elapsed_s", 0) for s in steps)

        # Per-provider breakdown from router_usage
        per_provider = router_usage.get("per_provider", {})

        # Health assessment
        failure_rate = len(failed_steps) / len(steps) if steps else 0
        if failure_rate == 0:
            health = "healthy"
        elif failure_rate < 0.3:
            health = "degraded"
        else:
            health = "critical"

        report = {
            "workflow_id": workflow_id,
            "timestamp": time.time(),
            "total_steps": len(steps),
            "completed_steps": len(completed_steps),
            "failed_steps": len(failed_steps),
            "failure_rate": round(failure_rate, 3),
            "avg_confidence": round(avg_confidence, 3),
            "avg_latency_s": round(avg_latency, 2),
            "total_elapsed_s": round(total_elapsed, 2),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "per_provider": per_provider,
            "health": health,
            "errors": [
                {"step": s.get("step_id"), "error": s.get("error")}
                for s in failed_steps
            ],
        }

        # Persist report to logs/
        self._save_report(workflow_id, report)

        return report

    def _save_report(self, workflow_id: str, report: dict[str, Any]):
        """Save monitoring report as JSON file."""
        try:
            log_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "logs",
            )
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(log_dir, f"monitor_{workflow_id}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info(f"Monitor report saved: {path}")
        except Exception as e:
            logger.warning(f"Could not save monitor report: {e}")
