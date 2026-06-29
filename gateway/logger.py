"""Logger — structured logging for gateway requests."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("gateway")


def log_request(
    provider: str,
    url: str,
    status_code: int,
    latency_ms: float,
    tokens: int = 0,
    model: str = "",
):
    """Log an LLM API request."""
    entry = {
        "provider": provider,
        "url": url,
        "model": model,
        "status": status_code,
        "latency_ms": round(latency_ms, 1),
        "tokens": tokens,
    }
    logger.info(json.dumps(entry))


def log_workflow_step(
    workflow_id: str,
    step_id: str,
    agent: str,
    status: str,
    confidence: float = 0,
    error: str | None = None,
):
    """Log a workflow step execution."""
    entry = {
        "workflow_id": workflow_id,
        "step_id": step_id,
        "agent": agent,
        "status": status,
        "confidence": confidence,
    }
    if error:
        entry["error"] = error

    if status == "failed":
        logger.error(json.dumps(entry))
    else:
        logger.info(json.dumps(entry))


def setup_logging(log_dir: str = "logs", level: str = "INFO"):
    """Configure logging to file + console."""
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "agent.log")

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
