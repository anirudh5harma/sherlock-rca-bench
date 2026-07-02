"""Logs agent: scans log/trace signals for error clusters and known failure signatures."""
from __future__ import annotations

from backend.agents.base import Agent, AgentResult, signals_of, text_of
from backend.models import Hypothesis, Incident

_SIGNATURES = [
    (("nullpointer", "null pointer", "npe", "undefined is not", "cannot read propert", "nonetype"), "Null dereference / unhandled nil in code path", "code"),
    (("outofmemory", "oom", "java heap", "killed process", "memoryerror"), "Out-of-memory kill", "resource"),
    (("connection refused", "connection reset", "econnrefused", "no route to host"), "Downstream dependency unreachable", "dependency"),
    (("timeout", "timed out", "deadline exceeded", "context deadline"), "Downstream timeout", "dependency"),
    (("schema", "column", "no such column", "unknown field", "deserializ", "unmarshal", "parse error"), "Schema / data-shape mismatch", "data"),
    (("permission denied", "unauthorized", "403", "invalid credential", "auth"), "Auth / permission failure", "config"),
    (("disk", "enospc", "no space left"), "Disk full", "resource"),
    (("panic", "segfault", "fatal", "stack trace", "traceback"), "Unhandled crash / panic", "code"),
]


class LogsAgent(Agent):
    name = "logs-agent"

    def run(self, incident: Incident) -> AgentResult:
        res = AgentResult(agent=self.name)
        res.events.append(self._ev("start", "scanning logs + traces for error signatures"))
        sigs = signals_of(incident, "log", "trace")

        hits: dict[str, list[str]] = {}
        cats: dict[str, str] = {}
        for sig in sigs:
            t = text_of(sig)
            for keys, cause, category in _SIGNATURES:
                if any(k in t for k in keys):
                    hits.setdefault(cause, []).append(sig.id)
                    cats[cause] = category
                    res.events.append(self._ev("finding", f"{sig.id} matches signature: {cause}"))
                    break

        for cause, ev_ids in hits.items():
            # a concrete error signature in logs is candidate root-cause evidence (stronger than a
            # metric symptom); more matching lines => higher confidence.
            conf = min(0.5 + 0.12 * len(ev_ids), 0.88)
            res.hypotheses.append(Hypothesis(cause=cause, confidence=round(conf, 2), evidence=ev_ids, category=cats[cause]))
            res.findings.append(f"{cause} ({len(ev_ids)} line(s))")

        if not res.hypotheses:
            res.events.append(self._ev("finding", "no known error signature in logs"))
        res.events.append(self._ev("done", f"{len(res.hypotheses)} log signature cluster(s)"))
        return res
