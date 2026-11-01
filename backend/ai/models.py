"""Strict source-bound model patch schema; transport owns provenance."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ModelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    task: Literal["translate", "security"]
    language: Literal["python", "php"]
    file: str = Field(min_length=1, max_length=256)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    finding_id: str | None
    explanation: str = Field(min_length=1, max_length=2000)
    proposed_code: str = Field(min_length=1, max_length=262144)
    behavior_impact: Literal["preserves", "changes", "unknown"]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    review_areas: list[Literal["api", "configuration", "crypto", "data_format"]] = Field(max_length=4)
