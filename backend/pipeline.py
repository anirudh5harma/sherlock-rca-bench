"""Orchestrates the role agents + correlator into a single investigation.

Exposes a sync `run_pipeline` (used by /api/investigate and the bench runner) and an async
`stream_pipeline` generator (used by the SSE endpoint) that adds small delays so the UI can
show agents fanning out in real time.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from backend.agents.base import AgentResult
from backend.agents.correlator import correlate
from backend.agents.deploy_agent import DeployAgent
from backend.agents.logs_agent import LogsAgent
from backend.agents.metrics_agent import MetricsAgent
from backend.models import AgentEvent, Incident, RCAReport

ROLE_AGENTS = [MetricsAgent(), DeployAgent(), LogsAgent()]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_pipeline(incident: Incident) -> tuple[RCAReport, list[AgentEvent]]:
    t0 = time.perf_counter()
    events: list[AgentEvent] = []
    results: list[AgentResult] = []
    for agent in ROLE_AGENTS:
        r = agent.run(incident)
        events.extend(r.events)
        results.append(r)
    events.append(AgentEvent(ts=_now(), agent="correlator", phase="start", message="fusing agent findings"))
    report = correlate(incident, results)
    report.latency_ms = int((time.perf_counter() - t0) * 1000)
    events.append(
        AgentEvent(
            ts=_now(),
            agent="correlator",
            phase="done",
            message=f"ranked {len(report.hypotheses)} hypothesis(es)",
            data={"report": report.model_dump(mode="json")},
        )
    )
    return report, events


async def stream_pipeline(incident: Incident, delay: float = 0.18) -> AsyncIterator[AgentEvent]:
    t0 = time.perf_counter()
    results: list[AgentResult] = []
    for agent in ROLE_AGENTS:
        r = agent.run(incident)
        for ev in r.events:
            yield ev
            await asyncio.sleep(delay)
        results.append(r)

    yield AgentEvent(ts=_now(), agent="correlator", phase="start", message="fusing agent findings")
    await asyncio.sleep(delay)
    report = correlate(incident, results)
    report.latency_ms = int((time.perf_counter() - t0) * 1000)
    yield AgentEvent(
        ts=_now(),
        agent="correlator",
        phase="done",
        message=f"ranked {len(report.hypotheses)} hypothesis(es)",
        data={"report": report.model_dump(mode="json")},
    )
