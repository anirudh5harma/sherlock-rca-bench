"""Deploy agent: time-correlates recent deploys/config changes with incident start."""
from __future__ import annotations

from datetime import timedelta

from backend.agents.base import Agent, AgentResult, signals_of, text_of
from backend.models import Hypothesis, Incident

WINDOW = timedelta(minutes=15)


def _incident_service(incident: Incident) -> str:
    return str(incident.alert.meta.get("service") or incident.alert.source or "").lower()


class DeployAgent(Agent):
    name = "deploy-agent"

    def run(self, incident: Incident) -> AgentResult:
        res = AgentResult(agent=self.name)
        res.events.append(self._ev("start", "correlating deploys/config changes with incident start"))
        start = incident.started_at
        inc_svc = _incident_service(incident)

        for sig in signals_of(incident, "deploy"):
            delta = start - sig.ts
            if timedelta(0) <= delta <= WINDOW:
                mins = round(delta.total_seconds() / 60, 1)
                # config changes vs code deploys get different categories
                is_config = any(k in text_of(sig) for k in ("config", "env", "flag", "toggle", "variable"))
                category = "config" if is_config else "deploy"
                cause = (
                    f"Recent {'config change' if is_config else 'deploy'} "
                    f"({sig.title}) {mins} min before incident"
                )
                # closer in time => higher confidence
                conf = 0.9 - min(delta / WINDOW, 1.0) * 0.25
                # service-awareness: a change on a *different* service than the one alerting is a
                # weaker suspect (avoids the naive "something deployed, blame it" trap).
                sig_svc = str(sig.meta.get("service") or "").lower()
                same_service = not sig_svc or not inc_svc or sig_svc == inc_svc
                if not same_service:
                    conf *= 0.6
                    res.events.append(
                        self._ev("thinking", f"{sig.id} is on {sig_svc}, not {inc_svc} — down-weighting")
                    )
                res.hypotheses.append(
                    Hypothesis(cause=cause, confidence=round(conf, 2), evidence=[sig.id], category=category)
                )
                res.findings.append(f"{sig.id}: {cause}")
                phase_msg = f"prime suspect {sig.id}: {mins} min before start" if same_service else f"nearby change {sig.id} (cross-service)"
                res.events.append(self._ev("finding", phase_msg))
            else:
                res.events.append(self._ev("thinking", f"{sig.id} outside 15-min window — likely unrelated"))

        if not res.hypotheses:
            res.events.append(self._ev("finding", "no deploy/config change within window"))
        res.events.append(self._ev("done", f"{len(res.hypotheses)} time-correlated change(s)"))
        return res
