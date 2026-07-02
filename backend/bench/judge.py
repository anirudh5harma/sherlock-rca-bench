"""LLM judge (with deterministic mock fallback) that grades an RCAReport vs ground truth."""
from __future__ import annotations

import re

from backend.llm import complete_json, judge_model
from backend.models import GroundTruth, Incident, RCAReport, Score

_WEIGHTS = {"root": 0.45, "evidence": 0.2, "category": 0.15, "next": 0.1, "halluc": 0.1}
_STOP = {"the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "/", "-", "for", "with"}


def _tokens(s: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", s.lower()) if w and w not in _STOP}


def _semantic_overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _cited_ids(report: RCAReport) -> set[str]:
    return {e for h in report.hypotheses for e in h.evidence}


def _valid_ids(incident: Incident) -> set[str]:
    return {incident.alert.id} | {s.id for s in incident.signals}


def _heuristic_score(report: RCAReport, gt: GroundTruth, incident: Incident) -> Score:
    top_cause = report.hypotheses[0].cause if report.hypotheses else ""
    top_cat = report.hypotheses[0].category if report.hypotheses else "unknown"

    root = round(min(_semantic_overlap(top_cause, gt.root_cause) * 1.6, 1.0), 2)
    category_correct = top_cat == gt.category

    cited = _cited_ids(report)
    key = set(gt.key_evidence)
    evidence_recall = round(len(cited & key) / len(key), 2) if key else 1.0

    valid = _valid_ids(incident)
    hallucination = any(c not in valid for c in cited)

    ns_text = " ".join(report.next_steps).lower()
    next_usefulness = 1.0 if any(_semantic_overlap(ns_text, a) > 0.12 for a in gt.acceptable_next_steps) else 0.4

    overall = (
        _WEIGHTS["root"] * root
        + _WEIGHTS["evidence"] * evidence_recall
        + _WEIGHTS["category"] * (1.0 if category_correct else 0.0)
        + _WEIGHTS["next"] * next_usefulness
        + _WEIGHTS["halluc"] * (0.0 if hallucination else 1.0)
    )
    return Score(
        scenario_id="",
        root_cause_match=root,
        category_correct=category_correct,
        evidence_recall=evidence_recall,
        next_step_usefulness=round(next_usefulness, 2),
        hallucination=hallucination,
        overall=round(overall, 2),
        rationale=(
            f"root≈{root} vs '{gt.root_cause}'; category {'hit' if category_correct else 'miss'} "
            f"({top_cat} vs {gt.category}); evidence {evidence_recall}; halluc={hallucination}"
        ),
    )


def judge(report: RCAReport, gt: GroundTruth, incident: Incident) -> Score:
    base = _heuristic_score(report, gt, incident)
    base.scenario_id = incident.id

    # LLM refinement of the fuzzy dimensions (root cause match, next-step usefulness) when available.
    polished = complete_json(
        system=(
            "You grade an SRE root-cause analysis against ground truth. Score 0..1 how well the "
            "reported root cause semantically matches, and how useful the next steps are."
        ),
        user=(
            f"Ground-truth root cause: {gt.root_cause}\n"
            f"Reported top cause: {report.hypotheses[0].cause if report.hypotheses else '(none)'}\n"
            f"Reported next steps: {report.next_steps}\n"
            f"Acceptable next steps: {gt.acceptable_next_steps}"
        ),
        model=judge_model(),
        schema_hint='{"root_cause_match": number, "next_step_usefulness": number, "rationale": str}',
        mock={},
    )
    if isinstance(polished.get("root_cause_match"), (int, float)):
        base.root_cause_match = round(max(0.0, min(float(polished["root_cause_match"]), 1.0)), 2)
    if isinstance(polished.get("next_step_usefulness"), (int, float)):
        base.next_step_usefulness = round(max(0.0, min(float(polished["next_step_usefulness"]), 1.0)), 2)
    if isinstance(polished.get("rationale"), str) and polished["rationale"].strip():
        base.rationale = polished["rationale"].strip()

    # recompute overall with any refined values
    base.overall = round(
        _WEIGHTS["root"] * base.root_cause_match
        + _WEIGHTS["evidence"] * base.evidence_recall
        + _WEIGHTS["category"] * (1.0 if base.category_correct else 0.0)
        + _WEIGHTS["next"] * base.next_step_usefulness
        + _WEIGHTS["halluc"] * (0.0 if base.hallucination else 1.0),
        2,
    )
    return base
