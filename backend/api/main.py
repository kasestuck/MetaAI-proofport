"""Proofport API. Run with: python -m uvicorn backend.api.main:app."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from backend.core.models import Error, RunState, StartRun
from backend.core.report import render_html, report_data
from backend.core.runs import RunError, RunStore
from backend.sandbox.runner import DockerRunner


ROOT = Path(__file__).resolve().parents[2]


def docker_available() -> bool:
    return DockerRunner().available()


def create_app(root: Path = ROOT, step_seconds: float = 0.2) -> FastAPI:
    settings = {**dotenv_values(root / ".env"), **os.environ}
    mode = settings.get("LLM_MODE", "mock").lower()
    if mode not in {"live", "mock", "replay"}:
        raise ValueError("LLM_MODE must be live, mock, or replay.")
    pipeline = settings.get("PROOFPORT_PIPELINE", "verify")
    if pipeline not in {"verify", "simulation", "fixtures", "analyze", "audit", "compatibility"}:
        raise ValueError("Invalid PROOFPORT_PIPELINE mode.")
    store = RunStore(root, step_seconds, pipeline=pipeline, settings=settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.docker = docker_available()
        store.real_enabled = app.state.docker and bool(settings.get("PROOFPORT_CASES_FILE"))
        if not app.state.docker:
            store.verification_error = Error(
                code="docker_unavailable",
                message="Docker is unavailable. Only static source inventory and hashing ran; dynamic verification is unavailable. Host execution is forbidden.",
            )
        try:
            yield
        finally:
            await store.close()

    app = FastAPI(title="Proofport", version="0.1.0", lifespan=lifespan)
    app.state.runs = store

    @app.exception_handler(RunError)
    async def run_error(_: Request, exc: RunError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Do not echo request bodies, which may contain secrets.
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Invalid request body or query parameters."}})

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail)}})

    @app.get("/api/health")
    async def health():
        return {"ok": True, "docker": app.state.docker, "llm_mode": mode}

    @app.post("/api/runs")
    async def start_run(body: StartRun):
        if pipeline in {"verify", "fixtures"} and (settings.get("PROOFPORT_SOURCE_VERSION", "2.7") != "2.7" or settings.get("PROOFPORT_TARGET_VERSION", "3.12") != "3.12"):
            raise RunError(400, "unsupported_migration_pair", "Migration currently supports only Python 2.7 to 3.12. Use compatibility mode to verify other configured versions.")
        if settings.get("PROOFPORT_SECURITY_FIXTURES") and (pipeline != "fixtures" or mode != "mock"):
            raise RunError(503, "offline_only", "Security fixture verification requires PROOFPORT_PIPELINE=fixtures and LLM_MODE=mock. No paid API request is permitted in this stage.")
        if pipeline in {"simulation", "fixtures"} and mode != "mock":
            raise RunError(503, "pipeline_unavailable", "Simulation/fixtures require LLM_MODE=mock and cannot stand in for live or replay model calls.")
        return {"run_id": store.start(body.source_path, body.max_iterations)}

    @app.get("/api/runs/{run_id}", response_model=RunState, response_model_exclude_unset=True)
    async def get_run(run_id: str):
        return store.get(run_id).state.snapshot()

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, since: int = Query(default=0, ge=0)):
        return store.get(run_id).evidence.since(since)

    @app.get("/api/runs/{run_id}/report")
    async def report(run_id: str, format: Literal["html", "json"] = "html"):
        run = store.get(run_id)
        if run.state.status not in {"done", "failed"}:
            raise RunError(409, "run_not_finished", "The report is available after the run finishes.")
        data = report_data(run)
        headers = {"Content-Disposition": f'attachment; filename="proofport-{run_id}.{format}"'}
        if format == "json":
            return JSONResponse(data, headers=headers)
        return HTMLResponse(render_html(data), headers=headers)

    # API routes must precede the catch-all static mount.
    frontend = root / "frontend"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    else:
        @app.get("/", response_class=HTMLResponse)
        async def index():
            return '<h1>Proofport backend is running</h1><p>Docker-only Python 2.7 to 3.12 verification. Configure golden inputs and a live model or explicitly select fixture candidates. Frontend files have not been added yet.</p><a href="/docs">API documentation</a>'

    return app


app = create_app()
