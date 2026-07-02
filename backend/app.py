"""FastAPI app: RCA investigation (blocking + SSE) + benchmark, serving the dashboard.

See CONTRACT.md for the full API surface.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.bench.loader import get_scenario, redacted_list
from backend.bench.runner import run_bench
from backend.llm import llm_mode
from backend.models import BenchRunRequest, InvestigateRequest
from backend.pipeline import run_pipeline, stream_pipeline

app = FastAPI(title="Sherlock RCA-Bench", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "llm_mode": llm_mode()}


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    return [s.model_dump(mode="json") for s in redacted_list()]


@app.get("/api/scenarios/{scenario_id}")
def scenario_detail(scenario_id: str) -> dict:
    sc = get_scenario(scenario_id)
    if sc is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    return sc.model_dump(mode="json")


@app.post("/api/investigate")
def investigate(req: InvestigateRequest) -> dict:
    incident = _resolve_incident(req)
    report, _events = run_pipeline(incident)
    return report.model_dump(mode="json")


@app.get("/api/investigate/stream")
async def investigate_stream(scenario_id: str) -> StreamingResponse:
    sc = get_scenario(scenario_id)
    if sc is None:
        raise HTTPException(status_code=404, detail="scenario not found")

    async def gen():
        async for ev in stream_pipeline(sc.incident):
            yield f"data: {json.dumps(ev.model_dump(mode='json'))}\n\n"
            await asyncio.sleep(0)  # flush

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/bench/run")
def bench_run(req: BenchRunRequest) -> dict:
    result = run_bench(scenario_ids=req.scenario_ids, model=req.model)
    return result.model_dump(mode="json")


def _resolve_incident(req: InvestigateRequest):
    if req.incident is not None:
        return req.incident
    if req.scenario_id:
        sc = get_scenario(req.scenario_id)
        if sc is None:
            raise HTTPException(status_code=404, detail="scenario not found")
        return sc.incident
    raise HTTPException(status_code=400, detail="provide scenario_id or incident")


# static dashboard at "/" (mounted last so /api/* wins)
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
