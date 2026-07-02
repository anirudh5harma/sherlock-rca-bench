# 🔎 Sherlock RCA-Bench

**Multi-agent root-cause analysis for AI-SRE — with a ruler.**

The hard part of an AI SRE isn't calling an LLM on logs. It's *trust*: proving the root-cause
analysis is right before an enterprise lets it touch production. Most demos ship the agent.
This ships the **agent + the benchmark that grades it**.

## What's inside

1. **Multi-agent RCA engine** — an alert fires; specialist agents fan out
   (`metrics-agent`, `deploy-agent`, `logs-agent`), a `correlator` fuses their findings into a
   ranked list of hypotheses with confidence + cited evidence, and returns a Slack-style RCA card.
2. **RCA-Bench** — synthetic incidents across 6 failure classes (deploy, config, resource,
   dependency, code, data), each with **ground truth**. An LLM **judge** scores every run on
   root-cause match, evidence recall, category, next-step usefulness, and a **hallucination flag**.
3. **Live dashboard** — watch agents work in real time (SSE), read the RCA card, run the whole
   benchmark and see the grade.

## Why it maps to Sherlocks

| Sherlocks concept | Here |
|---|---|
| Specialized agents investigate + correlate signals | role agents + correlator |
| Root cause + next steps into Slack | Slack-style RCA card |
| 90% less alert noise / faster MTTR | latency + confidence surfaced per run |
| Enterprise trust | the benchmark + hallucination detection — the missing ruler |

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app:app --reload
# open http://localhost:8000
```

No API key? It runs in **mock mode** — deterministic, offline, full demo. To use real reasoning,
put a `.env` in the repo root (auto-loaded, cwd-independent):

```
OPENAI_API_KEY=sk-...
RCA_AGENT_MODEL=gpt-4o-mini
RCA_JUDGE_MODEL=gpt-4o
```

## Deploy

`render.yaml` is a one-click Render blueprint. Set `OPENAI_API_KEY` in the Render dashboard.

## Layout

```
backend/
  models.py        # shared schemas (contract)
  llm.py           # OpenAI + deterministic mock
  agents/          # metrics / deploy / logs / correlator
  bench/           # judge, runner, scenarios/*.json
  app.py           # FastAPI + SSE, serves frontend/
frontend/          # vanilla dashboard (index.html, styles.css, app.js)
CONTRACT.md        # interface source of truth
```
