"""Versioned control DTOs. Legacy DTOs deliberately remain unchanged."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ControlError(Exception):
    def __init__(self, code, message, status=422, field=None):
        super().__init__(message)
        self.code, self.message, self.status, self.field = code, message, status, field

    def snapshot(self):
        return {"code": self.code, "message": self.message, "field": self.field}


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    language: Literal["python", "php"] = "python"
    operation: Literal["migration", "audit", "compatibility"]
    project_id: str = Field(min_length=1, max_length=128)
    source_version: str | None = Field(default=None, max_length=16)
    target_version: str | None = Field(default=None, max_length=16)
    execution_mode: Literal["offline_fixtures", "offline", "simulation", "live"] = "offline"
    fixture_profile_id: str | None = Field(default=None, max_length=128)
    cases_profile_id: str | None = Field(default=None, max_length=128)
    security_fix_profile_id: str | None = Field(default=None, max_length=128)
    verification_level: Literal["syntax", "tests", "behavior"] | None = None
    max_iterations: int = Field(default=5, ge=1, le=5, strict=True)


class ResolveProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_id: Literal["workspace"] = "workspace"
    relative_path: str = Field(min_length=1, max_length=1024)


@dataclass(frozen=True)
class RunSpec:
    operation: str
    project_id: str
    source_path: str
    source_version: str | None
    target_version: str | None
    execution_mode: str
    pipeline: str
    max_iterations: int
    verification_level: str | None = None
    settings: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    images: tuple[tuple[str, str], ...] = ()
    source_hashes: tuple[tuple[str, str], ...] = ()
    fixture_profile_id: str | None = None
    cases_profile_id: str | None = None
    language: str = "python"
    security_fix_profile_id: str | None = None

    def public(self):
        data = {key: getattr(self, key) for key in (
            "operation", "project_id", "source_version", "target_version", "execution_mode",
            "max_iterations", "verification_level", "fixture_profile_id", "cases_profile_id")}
        if self.language != "python":
            data.update(language=self.language, security_fix_profile_id=self.security_fix_profile_id)
        return data
