"""Loads benchmark scenarios from backend/bench/scenarios/*.json."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.models import BenchScenario

SCENARIO_DIR = Path(__file__).parent / "scenarios"


@lru_cache(maxsize=1)
def _load_all() -> dict[str, BenchScenario]:
    out: dict[str, BenchScenario] = {}
    for p in sorted(SCENARIO_DIR.glob("*.json")):
        data = json.loads(p.read_text())
        sc = BenchScenario.model_validate(data)
        out[sc.id] = sc
    return out


def all_scenarios() -> list[BenchScenario]:
    return list(_load_all().values())


def get_scenario(scenario_id: str) -> BenchScenario | None:
    return _load_all().get(scenario_id)


def redacted_list() -> list[BenchScenario]:
    """Scenarios with ground_truth stripped (safe for the public list view)."""
    out = []
    for sc in all_scenarios():
        out.append(sc.model_copy(update={"ground_truth": None}))
    return out
