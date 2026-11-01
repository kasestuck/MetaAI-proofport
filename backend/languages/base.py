"""Internal adapter contracts. Legacy HTTP RunState/RunSpec stay unchanged."""

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Protocol, runtime_checkable

from backend.core.control_models import ControlError
from backend.core.projects import excluded, linked, source_files


class AdapterError(ControlError):
    pass


@runtime_checkable
class EvidenceSink(Protocol):
    def append(self, event_type: str, detail: str, module: str | None = None) -> None: ...
    def verify(self) -> bool: ...


@dataclass(frozen=True)
class Verification:
    syntax_passed: bool | None = None
    tests_passed: bool | None = None
    behavior_verified: bool | None = None


@dataclass(frozen=True)
class AnalysisResult:
    language: str
    source_version: str | None
    target_version: str | None
    analysis: dict
    verification: Verification = field(default_factory=Verification)
    limitations: tuple[str, ...] = ()

    def public(self):
        return asdict(self)


@dataclass(frozen=True)
class SecurityResult:
    language: str
    # Existing Python detail dictionaries already include CWE, confidence,
    # severity, file/line/status and potential-risk provenance. No reclassification.
    findings: tuple[dict, ...]
    coverage: str
    limitations: tuple[str, ...] = ()


@runtime_checkable
class LanguageAdapter(Protocol):
    language: str
    def analyze(self, source: Path, *, source_version=None, target_version=None, runner=None, evidence=None) -> AnalysisResult: ...
    def compatibility(self, run, run_id, root, settings) -> None: ...
    def security_findings(self, runner, source: Path, evidence: EvidenceSink) -> SecurityResult: ...
    def migrate_ai(self, job, client, **options): ...


def inventory(source):
    """Bounded read-only inventory; reject link ancestors before resolving."""
    source = Path(source).absolute()
    if any(linked(part) for part in (source, *source.parents)):
        raise AdapterError("unsafe_project_path", "Analysis cannot follow links/junctions.", 403)
    if excluded(source.name) or not source.exists():
        raise AdapterError("source_not_found", "Choose an existing, non-secret project or source file.", 404)
    files = source_files(source, max_files=2000, max_bytes=16 * 1024 * 1024)
    if len(files) > 2000 or sum(p.stat().st_size for p in files) > 16 * 1024 * 1024:
        raise AdapterError("project_limit_exceeded", "Analysis exceeds file/byte limits.", 413)
    return source, files


def hashes(source, files):
    return {p.name if source.is_file() else p.relative_to(source).as_posix(): sha256(p.read_bytes()).hexdigest() for p in files}
