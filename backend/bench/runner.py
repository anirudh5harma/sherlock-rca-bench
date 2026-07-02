"""Runs the agent pipeline over benchmark scenarios and aggregates judge scores."""
from __future__ import annotations

import uuid

from backend.bench.judge import judge
from backend.bench.loader import all_scenarios, get_scenario
from backend.llm import agent_model, llm_mode
from backend.models import BenchResult, Score
from backend.pipeline import run_pipeline


def run_bench(scenario_ids: list[str] | None = None, model: str | None = None) -> BenchResult:
    if scenario_ids:
        scenarios = [s for s in (get_scenario(i) for i in scenario_ids) if s is not None]
    else:
        scenarios = all_scenarios()

    scores: list[Score] = []
    latencies: list[int] = []
    for sc in scenarios:
        assert sc.ground_truth is not None, f"scenario {sc.id} missing ground_truth"
        report, _events = run_pipeline(sc.incident)
        latencies.append(report.latency_ms)
        scores.append(judge(report, sc.ground_truth, sc.incident))

    n = len(scores) or 1
    mean_overall = round(sum(s.overall for s in scores) / n, 3)
    halluc_rate = round(sum(1 for s in scores if s.hallucination) / n, 3)
    mean_latency = int(sum(latencies) / n) if latencies else 0

    label = model or (agent_model() if llm_mode() == "openai" else "mock")
    return BenchResult(
        run_id=uuid.uuid4().hex[:8],
        model=label,
        scores=scores,
        mean_overall=mean_overall,
        hallucination_rate=halluc_rate,
        mean_latency_ms=mean_latency,
    )
