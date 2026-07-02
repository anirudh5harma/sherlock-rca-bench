"""Correlator: fuses role-agent hypotheses into a ranked RCAReport.

Cross-agent agreement boosts confidence. Deploy-time correlation is weighted highest because
"what changed just before it broke" is the strongest real-world signal. LLM (when available)
polishes the summary + next steps; deterministic templates are used in mock mode.
"""
from __future__ import annotations

from backend.agents.base import AgentResult
from backend.llm import complete_json
from backend.models import Hypothesis, Incident, RCAReport

_NEXT_STEPS = {
    "deploy": ["Roll back the suspect deploy and confirm error rate recovers", "Diff the release for the offending change"],
    "config": ["Revert the config/env change", "Add a validation gate for this config key"],
    "resource": ["Scale the saturated resource / raise limits", "Add an autoscaling or backpressure guard"],
    "dependency": ["Check the downstream service health + add a circuit breaker", "Verify timeouts and retry budgets"],
    "code": ["Ship a hotfix for the failing code path + add a regression test", "Add a guard/null-check where it faulted"],
    "data": ["Reconcile the schema/data-shape mismatch", "Add a contract test on the producer"],
    "unknown": ["Gather more signal around the incident window", "Page the owning team for context"],
}


def _merge(hyps: list[Hypothesis]) -> list[Hypothesis]:
    """Merge hypotheses with the same category, unioning evidence and boosting on agreement."""
    by_cat: dict[str, Hypothesis] = {}
    counts: dict[str, int] = {}
    for h in hyps:
        counts[h.category] = counts.get(h.category, 0) + 1
        cur = by_cat.get(h.category)
        if cur is None:
            by_cat[h.category] = Hypothesis(
                cause=h.cause, confidence=h.confidence, evidence=list(h.evidence), category=h.category
            )
            continue
        # keep the highest-confidence cause as the representative, but always union evidence
        # from every hypothesis in this category (recall must not depend on ordering).
        if h.confidence > cur.confidence:
            cur.cause = h.cause
            cur.confidence = h.confidence
        for e in h.evidence:
            if e not in cur.evidence:
                cur.evidence.append(e)

    merged: list[Hypothesis] = []
    for cat, h in by_cat.items():
        boost = 0.08 * (counts[cat] - 1)  # multiple agents implicated this category
        # deploy/config that time-correlate are the strongest real-world signal
        if cat in ("deploy", "config"):
            boost += 0.05
        h.confidence = round(min(h.confidence + boost, 0.98), 2)
        merged.append(h)

    merged.sort(key=lambda x: x.confidence, reverse=True)
    return merged


def _blast_radius(incident: Incident) -> str:
    svc = incident.alert.meta.get("service") or incident.alert.source
    return f"Affects {svc}; {incident.severity.upper()} — {len(incident.signals)} correlated signals in window."


def correlate(incident: Incident, results: list[AgentResult]) -> RCAReport:
    all_hyps = [h for r in results for h in r.hypotheses]
    ranked = _merge(all_hyps)
    agents_used = [r.agent for r in results] + ["correlator"]

    if not ranked:
        ranked = [Hypothesis(cause="Root cause undetermined from available signals", confidence=0.2, category="unknown")]

    top = ranked[0]
    next_steps = list(_NEXT_STEPS.get(top.category, _NEXT_STEPS["unknown"]))
    summary = (
        f"Most likely: {top.cause} (confidence {int(top.confidence * 100)}%). "
        f"Ranked {len(ranked)} hypothesis(es) from {len(results)} agents."
    )

    # optional LLM polish
    findings_txt = "\n".join(f"- {r.agent}: " + "; ".join(r.findings) for r in results if r.findings)
    polished = complete_json(
        system="You are an SRE correlator. Given agent findings, write a crisp 2-sentence RCA summary and 3 concrete next steps.",
        user=f"Incident: {incident.title}\nTop hypothesis: {top.cause} ({top.category})\nFindings:\n{findings_txt}",
        schema_hint='{"summary": str, "next_steps": [str]}',
        mock={},
    )
    if isinstance(polished.get("summary"), str) and polished["summary"].strip():
        summary = polished["summary"].strip()
    if isinstance(polished.get("next_steps"), list) and polished["next_steps"]:
        next_steps = [str(s) for s in polished["next_steps"]][:4]

    return RCAReport(
        incident_id=incident.id,
        summary=summary,
        hypotheses=ranked,
        blast_radius=_blast_radius(incident),
        next_steps=next_steps,
        agents_used=agents_used,
        latency_ms=0,  # set by the runner/app
    )
