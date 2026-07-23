"""Pydantic contracts for PR Guardian.

Two layers of schema:

1. Raw per-prompt LLM output (``StyleOutput``, ``SecurityOutput``,
   ``HistoryOutput``) — mirrors exactly what each prompt in ``prompts/``
   asks the model to return. Parsing failure here means "malformed
   structured output" (requirement #12, retryable at the ANALYZING stage).
2. The unified ``Finding`` — the one contract every review comment must
   satisfy before it is allowed near the GitHub API (requirement #17,
   the "Finding Schema" from REQUIREMENTS.md section 6).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Unified finding contract (REQUIREMENTS.md section 6)
# ---------------------------------------------------------------------------


class HistoricalReference(BaseModel):
    pr: int
    reason: str


class Finding(BaseModel):
    rule_id: str
    severity: Literal["critical", "high", "medium", "low"]
    confidence: float = Field(ge=0.0, le=1.0)
    path: str
    line: int = Field(gt=0)
    side: Literal["LEFT", "RIGHT"] = "RIGHT"
    evidence: Optional[str] = None
    message: str
    suggestion: Optional[str] = None
    historical_reference: Optional[HistoricalReference] = None

    @field_validator("path")
    @classmethod
    def _no_path_traversal(cls, v: str) -> str:
        if v.startswith("/") or ".." in v.split("/"):
            raise ValueError(f"suspicious path outside the diff: {v!r}")
        return v


# ---------------------------------------------------------------------------
# Raw per-prompt LLM outputs
# ---------------------------------------------------------------------------


class StyleComment(BaseModel):
    file: str
    line: int
    issue: str
    suggestion: str


class StyleOutput(BaseModel):
    summary: str
    comments: list[StyleComment] = Field(default_factory=list)
    score: int = Field(ge=1, le=10)


class SecurityFinding(BaseModel):
    file: str
    line: int
    severity: Literal["critical", "high", "medium", "low"]
    category: str
    issue: str
    remediation: str


class SecurityOutput(BaseModel):
    summary: str
    findings: list[SecurityFinding] = Field(default_factory=list)
    risk_level: Literal["critical", "high", "medium", "low", "none"]


class HistoryInsight(BaseModel):
    file: str
    line: int
    type: Literal["regression", "pattern_violation", "related_context", "incomplete_work"]
    reference: str
    insight: str
    recommendation: str


class HistoryOutput(BaseModel):
    summary: str
    history_insights: list[HistoryInsight] = Field(default_factory=list)
    patterns_confirmed: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
