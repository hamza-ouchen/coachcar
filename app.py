"""Run with: python -m uvicorn app:app --host 127.0.0.1 --port 8000"""
import asyncio
import csv
import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import provider
import storage
import workflow

ROOT = Path(__file__).resolve().parent
TASKS = set()


@asynccontextmanager
async def lifespan(app):
    storage.init_db()
    yield
    for task in list(TASKS):
        task.cancel()
    if TASKS:
        await asyncio.gather(*TASKS, return_exceptions=True)


app = FastAPI(title="Cap Avenir", description="Orientation professionnelle multi-agents et observabilité", lifespan=lifespan)


class Profile(BaseModel):
    situation: str = Field(min_length=3, max_length=400)
    skills: str = Field(min_length=2, max_length=1200)
    objective: Literal["compare", "evolve", "switch"] = "compare"
    market: str = Field(default="Maroc", min_length=2, max_length=150)
    remote: bool = True
    hours: int = Field(default=8, ge=1, le=60)
    horizon: Literal[3, 6, 12] = 6
    interests: str = Field(default="", max_length=1200)

    @field_validator("situation", "skills", "market", "interests", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class RunRequest(BaseModel):
    profile: Profile
    mode: Literal["live", "demo"] = "live"
    scenario: Literal["normal", "alerts"] = "normal"


def require_run(run_id):
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(404, "Exécution introuvable.")
    return run


@app.get("/api/health")
async def health():
    return {"ok": True, "application": "cap-avenir", "configured": bool(os.getenv("OPENROUTER_API_KEY")), "model": provider.MODEL,
            "slow_seconds": workflow.SLOW_SECONDS, "budget_usd": workflow.BUDGET_USD}


@app.post("/api/runs", status_code=202)
async def create_run(body: RunRequest):
    if body.mode == "live" and not os.getenv("OPENROUTER_API_KEY"):
        raise HTTPException(503, "Clé OpenRouter absente. Configurez .env ou utilisez le mode démonstration.")
    active = [r for r in storage.list_runs() if r["status"] == "running"]
    if len(active) >= 3:
        raise HTTPException(409, "Trois missions sont déjà actives. Attendez leur fin.")
    run_id = str(uuid4())
    profile = body.profile.model_dump()
    storage.create_run(run_id, profile, body.mode, "demo-local" if body.mode == "demo" else provider.MODEL)
    task = asyncio.create_task(workflow.execute(run_id, profile, body.mode == "demo", body.scenario))
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    return {"id": run_id, "correlation_id": run_id}


@app.get("/api/runs")
async def runs(mode: Literal["live", "demo"] | None = None):
    return storage.list_runs(mode)


@app.get("/api/runs/{run_id}")
async def run_detail(run_id: str):
    run = require_run(run_id)
    run["events"] = storage.events(run_id)
    return run


@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str, request: Request, after: int = 0):
    require_run(run_id)
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        cursor = after

    async def generate():
        nonlocal cursor
        heartbeat = 0
        while not await request.is_disconnected():
            batch = storage.events(run_id, cursor)
            for event in batch:
                cursor = event["id"]
                yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            run = storage.get_run(run_id)
            if run and run["status"] != "running":
                # A terminal event may follow the status update in the same event-loop turn.
                for event in storage.events(run_id, cursor):
                    cursor = event["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                yield "event: closed\ndata: {}\n\n"
                break
            heartbeat += 1
            if heartbeat % 30 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.35)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/metrics")
async def metrics(mode: Literal["live", "demo"] = "live"):
    return storage.metrics(mode)


@app.get("/api/exports/runs.csv")
async def export_runs(mode: Literal["live", "demo"] | None = None):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["correlation_id", "date", "mode", "statut", "situation", "duree_ms", "tokens", "cout_connu_usd", "cout_complet"])
    for run in storage.list_runs(mode):
        # Spreadsheet formulas must not be interpreted when opening the classroom export.
        situation = run["profile"]["situation"]
        if situation.startswith(("=", "+", "-", "@")):
            situation = "'" + situation
        writer.writerow([run["id"], run["created_at"], run["mode"], run["status"], situation, run["duration_ms"], run["tokens"], run["cost"], run["cost_complete"]])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="cap-avenir-executions.csv"'})


@app.get("/api/runs/{run_id}/export")
async def export_run(run_id: str):
    run = require_run(run_id)
    run["events"] = storage.events(run_id)
    return JSONResponse(run, headers={"Content-Disposition": f'attachment; filename="orientation-{run_id[:8]}.json"'})


@app.get("/api/workflow/export")
async def export_workflow():
    return JSONResponse(workflow.export_workflow(), headers={"Content-Disposition": 'attachment; filename="cap-avenir-workflow.json"'})


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
