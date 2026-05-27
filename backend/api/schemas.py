"""Shared Pydantic schemas for API boundaries."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConversationInput(BaseModel):
    message: str = Field(min_length=1)
    channel: str = "web"


class MemoryNodeInput(BaseModel):
    content: str
    type: str = "knowledge"
    parent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


class SkillDraftInput(BaseModel):
    name: str
    trigger: str = "manual"
    steps: list[str] | str = Field(default_factory=list)


class SkillReviewInput(BaseModel):
    reviewer: str = "human"
    notes: str | None = None
    evidence: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)
    rollback_plan: str | None = None


class ApiStatus(BaseModel):
    status: Literal["success", "failed", "ok", "running", "healthy"]
    error: str | None = None
