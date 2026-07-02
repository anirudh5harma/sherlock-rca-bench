"""Runs the agent pipeline over benchmark scenarios and aggregates judge scores.

Scenarios are independent, so they run concurrently in a thread pool — the wall-clock time
is dominated by the slowest single scenario's two LLM calls, not the sum of all of them.
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

from backend.bench.judge import judge
from backend.bench.loader import all_scenarios, get_scenario
from backend.llm import agent_model, llm_mode
from backend.models import BenchResult, BenchScenario, Score
from backend.pipeline import run_pipeline

_MAX_WORKERS = 8


def _score_one(sc: BenchScenario) -> tuple[Score, int]:
    assert sc.ground_truth is not None, f"scenario {sc.id} missing ground_truth"
    report, _events = run_pipeline(sc.incident)
    return judge(report, sc.ground_truth, sc.incident), report.latency_ms


def run_bench(scenario_ids: list[str] | None = None, model: str | None = None) -> BenchResult:
    if scenario_ids:
        scenarios = [s for s in (get_scenario(i) for i in scenario_ids) if s is not None]
    else:
        scenarios = all_scenarios()

    scores: list[Score] = []
    latencies: list[int] = []
    if scenarios:
        workers = min(_MAX_WORKERS, len(scenarios))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for score, latency in pool.map(_score_one, scenarios):
                scores.append(score)
                latencies.append(latency)

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
