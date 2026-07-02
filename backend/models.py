"""Shared data schemas. Source of truth for backend + frontend. See CONTRACT.md."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SignalKind = Literal["metric", "log", "deploy", "trace", "alert"]
Severity = Literal["sev1", "sev2", "sev3"]
Category = Literal["deploy", "config", "resource", "dependency", "code", "data", "unknown"]
AgentPhase = Literal["start", "thinking", "finding", "done", "error"]


class Signal(BaseModel):
    id: str
    kind: SignalKind
    source: str
    ts: datetime
    title: str
    body: str
    meta: dict[str, Any] = Field(default_factory=dict)


class Incident(BaseModel):
    id: str
    title: str
    severity: Severity
    alert: Signal
    signals: list[Signal] = Field(default_factory=list)
    started_at: datetime


class Hypothesis(BaseModel):
    cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    category: Category = "unknown"


class RCAReport(BaseModel):
    incident_id: str
    summary: str
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    blast_radius: str = ""
    next_steps: list[str] = Field(default_factory=list)
    agents_used: list[str] = Field(default_factory=list)
    latency_ms: int = 0


class AgentEvent(BaseModel):
    ts: datetime
    agent: str
    phase: AgentPhase
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class GroundTruth(BaseModel):
    root_cause: str
    category: Category
    key_evidence: list[str] = Field(default_factory=list)
    acceptable_next_steps: list[str] = Field(default_factory=list)


class BenchScenario(BaseModel):
    id: str
    title: str
    severity: Severity
    incident: Incident
    ground_truth: GroundTruth | None = None  # redacted in list view


class Score(BaseModel):
    scenario_id: str
    root_cause_match: float = Field(ge=0.0, le=1.0)
    category_correct: bool
    evidence_recall: float = Field(ge=0.0, le=1.0)
    next_step_usefulness: float = Field(ge=0.0, le=1.0)
    hallucination: bool
    overall: float = Field(ge=0.0, le=1.0)
    rationale: str


class BenchResult(BaseModel):
    run_id: str
    model: str
    scores: list[Score] = Field(default_factory=list)
    mean_overall: float = 0.0
    hallucination_rate: float = 0.0
    mean_latency_ms: int = 0


# ---- request bodies ----

class InvestigateRequest(BaseModel):
    scenario_id: str | None = None
    incident: Incident | None = None


class BenchRunRequest(BaseModel):
    scenario_ids: list[str] | None = None
    model: str | None = None
