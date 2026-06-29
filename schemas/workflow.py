"""Workflow-level schemas for step tracking and results."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    """Tracks execution state of a single workflow step."""

    step_id: str
    agent: str
    status: str = "pending"  # pending | running | completed | failed | skipped
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    elapsed_s: float = 0.0
    error: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0
    retries: int = 0
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


class WorkflowResult(BaseModel):
    """Final result envelope for a completed workflow run."""

    workflow_id: str
    workflow_name: str
    status: str  # completed | partial | failed
    steps_total: int
    steps_completed: int
    steps_failed: int
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    elapsed_s: float = 0.0
    steps: list[WorkflowStep] = Field(default_factory=list)
    final_output: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
