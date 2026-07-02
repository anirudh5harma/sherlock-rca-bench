"""Offline smoke test: runs the pipeline + bench in mock mode and asserts valid output.

Run: python -m backend.smoke_test   (exits 0 on success)
"""
from __future__ import annotations

import sys

from backend.bench.loader import all_scenarios
from backend.bench.runner import run_bench
from backend.models import BenchResult, RCAReport
from backend.pipeline import run_pipeline


def main() -> int:
    scenarios = all_scenarios()
    assert len(scenarios) >= 6, f"expected >=6 scenarios, got {len(scenarios)}"

    # single investigate
    sc = scenarios[0]
    report, events = run_pipeline(sc.incident)
    assert isinstance(report, RCAReport)
    assert report.hypotheses, "no hypotheses produced"
    assert any(e.phase == "done" and e.data.get("report") for e in events), "no done event with report"
    print(f"investigate[{sc.id}]: top='{report.hypotheses[0].cause}' "
          f"conf={report.hypotheses[0].confidence} cat={report.hypotheses[0].category}")

    # full bench
    result = run_bench()
    assert isinstance(result, BenchResult)
    assert len(result.scores) == len(scenarios)
    print(f"bench: mean_overall={result.mean_overall} halluc_rate={result.hallucination_rate} "
          f"latency={result.mean_latency_ms}ms model={result.model}")
    for s in result.scores:
        print(f"  {s.scenario_id:<24} overall={s.overall:<5} cat_ok={str(s.category_correct):<5} "
              f"root={s.root_cause_match} evid={s.evidence_recall} halluc={s.hallucination}")

    # sanity: no hallucinations expected on curated scenarios
    assert result.hallucination_rate == 0.0, "unexpected hallucination on curated scenarios"
    # single-scenario bench
    one = run_bench(scenario_ids=[sc.id])
    assert len(one.scores) == 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
