# Sherlock RCA-Bench — Shared Contract

This file is the source of truth for the interface between the **backend** (FastAPI, built by Codex)
and the **frontend** (web dashboard, built by orchestrator). Do not diverge without updating this file.

## Product in one line

An **eval benchmark** for AI-SRE root-cause-analysis + a **slim multi-agent RCA engine** that scores on it,
with a **Slack-style web dashboard** that shows agents fanning out live and returns a ranked RCA card + a bench grade.

Positioning for Sherlocks.ai: the hard problem in AI-SRE is **trust** — proving the RCA is right. This ships the ruler
(the benchmark + LLM judge) *and* the agent, so quality is measurable, not asserted.

## Core data schemas (Pydantic v2, `backend/models.py`)

```
Signal
  id: str
  kind: Literal["metric","log","deploy","trace","alert"]
  source: str                 # e.g. "prometheus", "github-actions", "loki"
  ts: datetime
  title: str
  body: str                   # raw text / value payload
  meta: dict[str, Any] = {}

Incident
  id: str
  title: str
  severity: Literal["sev1","sev2","sev3"]
  alert: Signal               # the firing alert
  signals: list[Signal]       # correlated evidence bundle
  started_at: datetime

Hypothesis
  cause: str                  # concise root-cause statement
  confidence: float           # 0..1
  evidence: list[str]         # signal ids or short quotes supporting it
  category: Literal["deploy","config","resource","dependency","code","data","unknown"]

RCAReport
  incident_id: str
  summary: str                # human-readable RCA summary
  hypotheses: list[Hypothesis]        # ranked, best first
  blast_radius: str
  next_steps: list[str]
  agents_used: list[str]
  latency_ms: int

AgentEvent                    # streamed over SSE during investigation
  ts: datetime
  agent: str                  # "metrics-agent" | "deploy-agent" | "logs-agent" | "correlator" | "judge"
  phase: Literal["start","thinking","finding","done","error"]
  message: str
  data: dict[str, Any] = {}

# Benchmark
BenchScenario
  id: str
  title: str
  severity: str
  incident: Incident          # full signal bundle
  ground_truth: GroundTruth

GroundTruth
  root_cause: str
  category: str
  key_evidence: list[str]     # signal ids that must be cited
  acceptable_next_steps: list[str]

Score                         # judge output for one scenario
  scenario_id: str
  root_cause_match: float     # 0..1  (semantic match to ground truth)
  category_correct: bool
  evidence_recall: float      # 0..1  fraction of key_evidence cited
  next_step_usefulness: float # 0..1
  hallucination: bool         # cited evidence not present in bundle
  overall: float              # weighted 0..1
  rationale: str

BenchResult
  run_id: str
  model: str
  scores: list[Score]
  mean_overall: float
  hallucination_rate: float
  mean_latency_ms: int
```

## HTTP + SSE API (FastAPI, `backend/app.py`)

- `GET  /api/health` -> `{status:"ok", llm_mode:"openai"|"mock"}`
- `GET  /api/scenarios` -> `list[BenchScenario]` (ground_truth omitted / redacted in this view)
- `GET  /api/scenarios/{id}` -> `BenchScenario` (ground_truth included; demo only)
- `POST /api/investigate` body `{scenario_id}` OR `{incident: Incident}` -> `RCAReport` (blocking, full run)
- `GET  /api/investigate/stream?scenario_id=...` -> **SSE** stream of `AgentEvent`, final event `phase:"done"` carries `{report: RCAReport}` in `data`
- `POST /api/bench/run` body `{scenario_ids?: [...], model?: str}` -> `BenchResult` (runs agent + judge over scenarios)
- Static: serve `frontend/` at `/`

SSE format: each event line `data: <json AgentEvent>\n\n`.

## LLM layer (`backend/llm.py`)

- Reads `OPENAI_API_KEY`. If present -> real OpenAI client (model default `gpt-4o-mini` for agents, `gpt-4o` for judge; override via env `RCA_AGENT_MODEL`, `RCA_JUDGE_MODEL`).
- If absent -> **deterministic mock** that returns plausible canned reasoning per scenario so the whole demo runs offline.
- `/api/health` reports which mode is active. UI shows a badge.

## Agents (`backend/agents/`)

Role agents, each takes an Incident, returns partial findings + emits AgentEvents:
- `metrics_agent` — reads metric/alert signals, spots anomalies (latency, error rate, saturation).
- `deploy_agent` — diffs recent deploy signals against incident start (correlation-in-time).
- `logs_agent` — scans log signals for error clusters / stack traces.
- `correlator` — fuses agent findings into ranked `Hypothesis` list + `RCAReport`.

Mirrors an AI-SRE "Rep composed of role agents" + a correlation step. Judge gates quality (bench).

## Bench (`backend/bench/`)

- `scenarios/*.json` — 6+ synthetic incidents with ground truth. Cover categories: deploy (bad rollout), config (bad env var), resource (OOM / disk full), dependency (downstream 5xx), code (null deref), data (schema drift). Each is realistic: multiple signals, some red herrings.
- `judge.py` — LLM-judge scores an RCAReport vs GroundTruth -> `Score`.
- `runner.py` — runs agent over scenarios, judges, aggregates -> `BenchResult`.

## Non-negotiables (from Sherlocks positioning)

- Confidence on every hypothesis. Hallucination flag in judge. Latency tracked. These are the trust signals founders care about.
