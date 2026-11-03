"""Additive, fixed-scope live demo endpoints. Never accept keys or project paths."""
import asyncio
from typing import Annotated, Literal
from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, StrictBool


class Consent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: Literal["python_mathutils","php_legacy"]
    consent: StrictBool


class StartDemo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: Literal["python_mathutils","php_legacy"]
    approval_id: str = Field(min_length=20,max_length=128)


def router(demo):
    api = APIRouter(prefix="/api/v1/live-demo",tags=["live-demo"])

    @api.get("")
    async def metadata():
        return await asyncio.to_thread(demo.snapshot)

    @api.post("/model-check")
    async def model_check():
        return await asyncio.to_thread(demo.check_model)

    @api.post("/confirm")
    async def confirm(body: Consent):
        return await asyncio.to_thread(demo.confirm,body.profile,body.consent)

    @api.post("/runs",status_code=202)
    async def start(body: StartDemo, idempotency_key: Annotated[str,Header(min_length=8,max_length=128,pattern=r"^[a-zA-Z0-9_-]+$")]):
        return {"run_id":await demo.start(body.profile,body.approval_id,idempotency_key)}

    return api
