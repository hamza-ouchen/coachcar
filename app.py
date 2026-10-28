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
import operations
import release_registry
import access
import database

ROOT = Path(__file__).resolve().parent
TASKS = set()
RUN_TASKS = {}


@asynccontextmanager
async def lifespan(app):
    access.validate_configuration()
    storage.init_db()
    operations.record_render_deployment()
    yield
    for task in list(TASKS):
        task.cancel()
    if TASKS:
        await asyncio.gather(*TASKS, return_exceptions=True)


app = FastAPI(title="Cap Avenir", description="Orientation professionnelle multi-agents et observabilité", lifespan=lifespan)
app.middleware("http")(access.protect)


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
            "slow_seconds": workflow.SLOW_SECONDS, "budget_usd": workflow.BUDGET_USD,
            "version": operations.version(), "paused": bool(operations.get_state()["paused"]),
            "demo_fault": operations.image_fault()}


@app.post("/api/runs", status_code=202)
async def create_run(body: RunRequest):
    control = operations.get_state()
    if control["paused"]:
        raise HTTPException(503, "Arrêt d'urgence actif : les nouvelles analyses sont suspendues.")
    if body.mode == "live" and not os.getenv("OPENROUTER_API_KEY"):
        raise HTTPException(503, "Clé OpenRouter absente. Configurez .env ou utilisez le mode démonstration.")
    active = [r for r in storage.list_runs() if r["status"] == "running"]
    if len(active) >= 3:
        raise HTTPException(409, "Trois missions sont déjà actives. Attendez leur fin.")
    run_id = str(uuid4())
    profile = body.profile.model_dump()
    storage.create_run(run_id, profile, body.mode, "demo-local" if body.mode == "demo" else provider.MODEL)
    scenario = body.scenario
    if body.mode == "demo":
        if operations.image_fault() or control["incident"] == "provider_error":
            scenario = "incident_error"
        elif control["incident"] == "slow":
            scenario = "incident_slow"
    task = asyncio.create_task(workflow.execute(run_id, profile, body.mode == "demo", scenario))
    TASKS.add(task)
    RUN_TASKS[run_id] = task
    task.add_done_callback(TASKS.discard)
    task.add_done_callback(lambda completed: RUN_TASKS.pop(run_id, None))
    return {"id": run_id, "correlation_id": run_id}


class Operator(BaseModel):
    actor: str = Field(min_length=2, max_length=80)
    reason: str = Field(default="Intervention pédagogique", max_length=300)

    @field_validator("actor", mode="before")
    @classmethod
    def strip_actor(cls, value):
        return value.strip() if isinstance(value, str) else value


class PauseRequest(Operator):
    paused: bool


class IncidentRequest(Operator):
    incident: Literal["normal", "provider_error", "slow"]


class ReviewRequest(Operator):
    decision: Literal["approved", "rejected"]
    agent_card_reviewed: bool = False


@app.get("/api/ops")
async def operation_status():
    return operations.snapshot()


@app.post("/api/ops/pause")
async def pause(body: PauseRequest):
    # Persist the gate BEFORE yielding the event loop or cancelling a task.
    operations.change_pause(body.paused, body.actor, body.reason)
    cancelled = []
    if body.paused:
        tasks = list(RUN_TASKS.items())
        for run_id, task in tasks:
            if not task.done():
                task.cancel()
                cancelled.append(run_id)
        if tasks:
            await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        # A task cancelled before its first instruction cannot write its own trace.
        for run_id in cancelled:
            run = storage.get_run(run_id)
            if run and run["status"] == "running":
                storage.finish_run(run_id, "cancelled", 0, error="Arrêt d'urgence avant démarrage.")
                storage.emit(run_id, "run_cancelled", 0, {"status": "cancelled", "message": "Arrêt d'urgence avant démarrage"})
        operations.audit("tasks_cancelled", body.actor, {"run_ids": cancelled})
    return {"paused": body.paused, "cancelled": cancelled}


@app.post("/api/ops/incident")
async def incident(body: IncidentRequest):
    operations.change_incident(body.incident, body.actor)
    return {"incident": body.incident, "scope": "demo_only"}


@app.post("/api/ops/releases/{version}/review")
async def review_release(version: str, body: ReviewRequest):
    try:
        result = release_registry.review(version, body.decision, body.actor, body.reason, body.agent_card_reviewed)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    operations.audit("release_" + body.decision, body.actor, {"version": version, "image_id": result["image_id"], "reason": body.reason, "agent_card_reviewed": body.agent_card_reviewed})
    return result


@app.get("/api/ops/export")
async def export_operations():
    return JSONResponse(operations.snapshot(), headers={"Content-Disposition": 'attachment; filename="cap-avenir-exploitation.json"'})


@app.post("/api/ops/backup")
async def backup_database(body: Operator):
    import sqlite3
    from datetime import datetime, timezone
    if any(r["status"] == "running" for r in storage.list_runs()):
        raise HTTPException(409, "Terminez ou interrompez les missions avant la sauvegarde.")
    if database.postgres_url():
        backup_id = str(uuid4())
        payload = {"format": "cap-avenir-application-json", "version": operations.version(),
                   "created_at": storage.now(), "runs": storage.list_runs(),
                   "operations": operations.snapshot()}
        for run in payload["runs"]:
            run["events"] = storage.events(run["id"])
        with storage.connect() as conn:
            conn.execute("INSERT INTO application_backups(id,created_at,payload) VALUES(?,?,?)",
                         (backup_id, storage.now(), json.dumps(payload, ensure_ascii=False)))
            conn.execute("DELETE FROM application_backups WHERE id NOT IN (SELECT id FROM application_backups ORDER BY created_at DESC LIMIT 3)")
        operations.audit("database_backup", body.actor, {"id": backup_id, "format": "application-json"})
        return {"id": backup_id, "format": "application-json", "download": "/api/ops/backups/" + backup_id}
    folder = storage.DB_PATH.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    filename = "cap-avenir-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + ".db"
    with storage.connect() as source:
        target = sqlite3.connect(folder / filename)
        try:
            source.backup(target)
        finally:
            target.close()
    operations.audit("database_backup", body.actor, {"filename": filename})
    return {"filename": filename}


@app.get("/api/ops/backups/{backup_id}")
async def download_backup(backup_id: str):
    with storage.connect() as conn:
        row = conn.execute("SELECT payload FROM application_backups WHERE id=?", (backup_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Sauvegarde introuvable.")
    return Response(row["payload"], media_type="application/json", headers={"Content-Disposition": 'attachment; filename="cap-avenir-backup.json"'})


@app.get("/api/ops/agent-card")
async def agent_card():
    return FileResponse(ROOT / "livrables" / "AGENT_CARD.md", media_type="text/markdown", filename="AGENT_CARD.md")


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
