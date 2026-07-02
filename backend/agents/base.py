"""Base types for role agents. Each agent inspects an Incident and returns candidate
hypotheses plus a list of AgentEvents describing its work (streamed to the UI)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.models import AgentEvent, Hypothesis, Incident, Signal


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AgentResult:
    agent: str
    hypotheses: list[Hypothesis] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)


class Agent:
    name: str = "agent"

    def _ev(self, phase: str, message: str, **data) -> AgentEvent:
        return AgentEvent(ts=now(), agent=self.name, phase=phase, message=message, data=data)

    def run(self, incident: Incident) -> AgentResult:  # pragma: no cover - overridden
        raise NotImplementedError


def signals_of(incident: Incident, *kinds: str) -> list[Signal]:
    wanted = set(kinds)
    out = [s for s in incident.signals if s.kind in wanted]
    if incident.alert.kind in wanted:
        out = [incident.alert, *out]
    return out


def text_of(sig: Signal) -> str:
    return f"{sig.title} {sig.body}".lower()
