"""Data contracts for agent input/output — all inter-agent communication."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    """Standardized input contract for every agent."""

    task_id: str = Field(default="", description="Unique task identifier")
    workflow_id: str = Field(default="", description="Parent workflow identifier")
    agent_name: str = Field(default="", description="Name of the receiving agent")
    input: dict[str, Any] = Field(default_factory=dict, description="Agent-specific input payload")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO timestamp when task was created",
    )


class AgentOutput(BaseModel):
    """Standardized output contract for every agent."""

    task_id: str = Field(default="", description="Echoed task identifier")
    workflow_id: str = Field(default="", description="Parent workflow identifier")
    agent_name: str = Field(default="", description="Name of the producing agent")
    input: dict[str, Any] = Field(default_factory=dict, description="Original input payload")
    output: dict[str, Any] = Field(default_factory=dict, description="Agent output payload")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score 0-1")
    next_agent: str = Field(default="", description="Suggested next agent in the chain")
    status: str = Field(default="completed", description="completed | failed | pending_review")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO timestamp when output was produced",
    )
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings")
