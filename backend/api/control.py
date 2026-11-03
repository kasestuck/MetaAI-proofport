"""Additive /api/v1 routes; legacy response DTOs are unchanged."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Header

from backend.core.control_models import ControlRequest, ResolveProject


def router(control):
    api = APIRouter(prefix="/api/v1", tags=["control"])

    @api.get("/capabilities")
    async def capabilities():
        data = await asyncio.to_thread(control.capabilities.snapshot)
        if getattr(control,"live_demo",None):
            data["live_demo"] = await asyncio.to_thread(control.live_demo.snapshot)
        return {**data, "instance_id": control.instance_id}

    @api.get("/projects")
    async def projects():
        return await asyncio.to_thread(control.catalog)

    @api.post("/projects/resolve")
    async def resolve(body: ResolveProject):
        return await asyncio.to_thread(control.projects.register, body.relative_path)

    @api.post("/runs/preflight")
    async def preflight(body: ControlRequest):
        return await asyncio.to_thread(control.preflight, body)

    @api.post("/runs", status_code=202)
    async def start(body: ControlRequest, idempotency_key: Annotated[str | None, Header(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")] = None):
        return {"run_id": await control.start(body, idempotency_key)}

    @api.get("/runs/{run_id}")
    async def details(run_id: str):
        return control.details(run_id)

    return api
