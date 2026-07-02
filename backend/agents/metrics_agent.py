"""Metrics agent: scans metric + alert signals for anomaly patterns."""
from __future__ import annotations

from backend.agents.base import Agent, AgentResult, signals_of, text_of
from backend.models import Hypothesis, Incident

# pattern -> (human cause template, category)
_PATTERNS = [
    (("error rate", "5xx", "500", "error_rate", "errors spiking"), "Elevated error rate / 5xx responses", "code"),
    (("latency", "p99", "p95", "slow", "response time"), "Latency / p99 spike", "resource"),
    (("cpu", "saturation", "throttl"), "CPU saturation / throttling", "resource"),
    (("memory", "oom", "out of memory", "heap"), "Memory pressure / OOM", "resource"),
    (("disk", "no space", "enospc"), "Disk exhaustion", "resource"),
    (("connection", "pool", "timeout", "refused"), "Connection pool exhaustion / downstream timeout", "dependency"),
    (("health check", "unresponsive", "unavailable", "status page", "not responding", "availability"), "Downstream service availability drop", "dependency"),
    (("queue", "lag", "backlog", "consumer"), "Queue backlog / consumer lag", "resource"),
]


class MetricsAgent(Agent):
    name = "metrics-agent"

    def run(self, incident: Incident) -> AgentResult:
        res = AgentResult(agent=self.name)
        res.events.append(self._ev("start", "scanning metric + alert signals"))
        sigs = signals_of(incident, "metric", "alert")

        for sig in sigs:
            t = text_of(sig)
            for keys, cause, category in _PATTERNS:
                if any(k in t for k in keys):
                    # metric anomalies are *symptoms*, so they carry lower confidence than a concrete
                    # log signature or a time-correlated deploy (which are candidate *causes*).
                    conf = 0.4 + (0.1 if sig.kind == "alert" else 0.0)
                    res.hypotheses.append(
                        Hypothesis(cause=cause, confidence=round(conf, 2), evidence=[sig.id], category=category)
                    )
                    res.findings.append(f"{sig.id}: {cause}")
                    res.events.append(self._ev("finding", f"anomaly in {sig.id}: {cause}"))
                    break

        if not res.hypotheses:
            res.events.append(self._ev("finding", "no clear metric anomaly"))
        res.events.append(self._ev("done", f"{len(res.hypotheses)} metric signal(s) implicated"))
        return res
