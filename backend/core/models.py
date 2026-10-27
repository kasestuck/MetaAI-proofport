"""Section 8 of the shared contract. Do not add simulation-only state fields."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartRun(ContractModel):
    source_path: str = Field(min_length=1)
    max_iterations: int = Field(default=5, ge=1, strict=True)


class Error(ContractModel):
    code: str
    message: str


class Module(ContractModel):
    name: str
    status: Literal["pending", "translating", "testing", "fixing", "green", "failed"] = "pending"
    iterations: int = 0
    tests_passed: int = 0
    tests_total: int


class Finding(ContractModel):
    id: str
    file: str
    line: int
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    status: Literal["open", "fixed", "false_positive", "needs_review", "fix_reverted"]
    note: str


class Security(ContractModel):
    before: int = 0
    after: int = 0
    findings: list[Finding] = Field(default_factory=list)


class Metrics(ContractModel):
    tests_passed: int = 0
    tests_total: int = 0
    lines_migrated: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0


class RunState(ContractModel):
    status: Literal["queued", "running", "done", "failed"] = "queued"
    phase: str = "analyzing"
    isolation: Literal["docker", "reduced"] = "reduced"
    modules: list[Module]
    security: Security = Field(default_factory=Security)
    hashes: dict[str, str | bool | None]
    metrics: Metrics
    chain_intact: bool = True
    error: Error | None = None

    def snapshot(self) -> dict:
        return self.model_dump(exclude={"error"} if self.error is None else set())
