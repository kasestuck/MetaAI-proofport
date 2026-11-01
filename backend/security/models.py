"""Internal proposal schema; the shared API Finding shape is unchanged."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FixProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: str = Field(min_length=1, max_length=128)
    explanation: str = Field(min_length=1, max_length=4000)
    proposed_code: str | None = Field(default=None, max_length=262144)
    behavior_impact: Literal["preserves", "changes", "unknown"]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    mode: Literal["fixture", "live", "replay", "mock"] = "fixture"
    disposition: Literal["patch", "false_positive"] = "patch"
    review_areas: list[Literal["api", "configuration", "crypto", "data_format"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_disposition(self):
        if self.disposition == "patch" and self.proposed_code is None:
            raise ValueError("A patch proposal must supply candidate code.")
        if self.disposition == "false_positive" and self.proposed_code is not None:
            raise ValueError("A classification must not silently change code.")
        return self


class FixGenerator(Protocol):
    def generate(self, finding: dict, source: str) -> FixProposal | None: ...
