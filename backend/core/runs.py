"""Run state, explicit simulation, and Docker-backed verification workers."""

import asyncio
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import re
from time import monotonic
from uuid import uuid4

from backend.core.evidence import Evidence
from backend.core.models import Error, Finding, Metrics, Module, RunState
from backend.sandbox.runner import DockerRunner, SandboxError


class RunError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


IGNORED = {".git", ".venv", "__pycache__", ".pytest_cache"}


def source_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if not source.is_symlink() else []
    return sorted(
        path for path in source.rglob("*")
        if path.is_file() and not path.is_symlink()
        and not any(part.startswith(".") or part in IGNORED for part in path.relative_to(source).parts)
        and not any(parent.is_symlink() for parent in path.parents if parent != source.parent)
    )


def hashes_for(source: Path) -> dict[str, str]:
    if source.is_file():
        return {source.name: sha256(source.read_bytes()).hexdigest()}
    return {
        f"{source.name}/{path.relative_to(source).as_posix()}": sha256(path.read_bytes()).hexdigest()
        for path in source_files(source)
    }


@dataclass
class Run:
    state: RunState
    source: Path
    originals: dict[str, str]
    modules: dict[str, tuple[str, str]]
    max_iterations: int
    simulation: bool = False
    execution_mode: str = "static_only"
    workspace: Path | None = None
    verification: dict = field(default_factory=dict)
    runner: DockerRunner | None = None
    evidence: Evidence = field(default_factory=Evidence)
    started: float = field(default_factory=monotonic)


class RunStore:
    def __init__(self, root: Path, step_seconds: float = 0.2, pipeline: str = "verify", settings: dict | None = None):
        self.root = root
        self.step_seconds = step_seconds
        self.pipeline = pipeline
        self.settings = settings or {}
        self.real_enabled = False
        self.verification_error = Error(
            code="pipeline_unavailable", message="Configure PROOFPORT_CASES_FILE for recorded behavior verification; no invented test inputs are used.",
        )
        self.runs: dict[str, Run] = {}
        self.tasks: set[asyncio.Task] = set()
        self.active: str | None = None

    def start(self, source_path: str, max_iterations: int) -> str:
        # No await between the busy check and reserving the run slot.
        if self.active is not None:
            raise RunError(409, "run_busy", "Another run is already in progress.")
        source = Path(source_path).expanduser()
        if not source.is_absolute():
            source = self.root / source
        source = source.resolve()
        universal = self.pipeline in {"analyze", "audit", "compatibility"}
        if not source.is_dir() and not (universal and source.is_file() and source.suffix == ".py"):
            raise RunError(400, "source_not_found", "The source folder does not exist.")
        try:
            originals = hashes_for(source)
            modules = {}
            states = []
            for path in source_files(source):
                if path.suffix != ".py":
                    continue
                relative = Path(path.name) if source.is_file() else path.relative_to(source)
                name = ".".join(relative.with_suffix("").parts)
                text = path.read_text(encoding="utf-8", errors="replace")
                modules[name] = (f"{source.name}/{relative.as_posix()}", text)
                functions = len(re.findall(r"^\s*def [a-zA-Z]\w*\(", text, re.MULTILINE))
                cases = max(8, min(15, functions * 3)) if self.pipeline == "simulation" else 0
                states.append(Module(name=name, tests_total=cases))
        except OSError:
            raise RunError(400, "source_unreadable", "The source folder could not be read.") from None
        if not states:
            raise RunError(400, "source_empty", "The source folder contains no Python modules.")
        # Detect edits during inspection instead of pairing different snapshots.
        try:
            if originals != hashes_for(source):
                raise RunError(409, "source_changed", "Source files changed while being inspected. Try again.")
        except OSError:
            raise RunError(400, "source_unreadable", "The source folder could not be read.") from None
        state = RunState(
            modules=states, hashes={**originals, "unchanged": None},
            metrics=Metrics(tests_total=sum(module.tests_total for module in states)),
        )
        simulation = self.pipeline == "simulation"
        run = Run(state, source, originals, modules, max_iterations, simulation=simulation)
        notice = (
            "SIMULATED run: no code execution, migration, model calls, or security fixes."
            if simulation else "Static source inventory only; no code execution, migration, tests, or security scan."
        )
        run.evidence.append("run_started", notice)
        run.evidence.append("hashes_recorded", f"SHA-256 recorded from {len(originals)} actual source files.")
        run_id = uuid4().hex
        self.runs[run_id] = run
        self.active = run_id
        worker = self._universal_pipeline if universal else (self._simulate if simulation else (self._real_pipeline if self.real_enabled else self._verification_unavailable))
        task = asyncio.create_task(worker(run_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return run_id

    def get(self, run_id: str) -> Run:
        if run_id not in self.runs:
            raise RunError(404, "run_not_found", "The requested run does not exist.")
        run = self.runs[run_id]
        if run.state.status in {"queued", "running"}:
            run.state.metrics.seconds = round(monotonic() - run.started, 3)
        run.state.chain_intact = run.evidence.verify()
        if not run.state.chain_intact and run.state.status == "done":
            run.state.status = "failed"
            run.state.error = Error(code="evidence_corrupted", message="Persisted evidence was modified; verification can no longer be trusted.")
        return run

    async def _pause(self):
        await asyncio.sleep(self.step_seconds)

    async def _real_pipeline(self, run_id: str):
        from backend.core.pipeline import execute
        run = self.runs[run_id]
        try:
            run.runner = DockerRunner(timeout=float(self.settings.get("SANDBOX_TIMEOUT_SECONDS", "30")))
        except (ValueError, SandboxError):
            self._fail(run, "invalid_settings", "SANDBOX_TIMEOUT_SECONDS must be finite, positive and at most 300 seconds.")
            self.active = None
            return
        mode = "fixtures" if self.pipeline == "fixtures" else "live"
        worker = asyncio.create_task(asyncio.to_thread(execute, run, run_id, self.root, self.settings, mode))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            await asyncio.to_thread(run.runner.cancel)
            await worker
            raise
        finally:
            self.active = None

    async def _universal_pipeline(self, run_id: str):
        from backend.core.universal import execute
        run = self.runs[run_id]
        try:
            run.runner = DockerRunner(timeout=float(self.settings.get("SANDBOX_TIMEOUT_SECONDS", "30")))
        except (ValueError, SandboxError):
            self._fail(run, "invalid_settings", "Invalid Docker timeout; select 0 < seconds <= 300.")
            self.active = None
            return
        worker = asyncio.create_task(asyncio.to_thread(execute, run, run_id, self.root, self.settings, self.pipeline))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            await asyncio.to_thread(run.runner.cancel)
            await worker
            raise
        finally:
            self.active = None

    async def _verification_unavailable(self, run_id: str):
        run = self.runs[run_id]
        try:
            run.state.status = "running"
            await self._pause()
            run.state.hashes["unchanged"] = hashes_for(run.source) == run.originals
            if not run.state.hashes["unchanged"]:
                self._fail(run, "source_changed", "Original files changed during source inspection.")
            else:
                self._fail(run, self.verification_error.code, self.verification_error.message)
            # Contract has no 'unverified' module status. Required verification failed.
            for module in run.state.modules:
                module.status = "failed"
        except asyncio.CancelledError:
            self._fail(run, "run_interrupted", "Run interrupted by application shutdown.")
            raise
        except OSError:
            self._fail(run, "source_unreadable", "Original file hashes could not be rechecked.")
        finally:
            run.state.metrics.seconds = round(monotonic() - run.started, 3)
            run.state.chain_intact = run.evidence.verify()
            self.active = None

    async def _simulate(self, run_id: str):
        run = self.runs[run_id]
        state = run.state
        try:
            await self._pause()
            state.status = "running"
            state.phase = "analyzing"
            await self._pause()
            state.phase = "recording"
            run.evidence.append("golden_recorded", f"SIMULATED allocation of {state.metrics.tests_total} golden cases; none executed.")
            await self._pause()
            state.phase = "migrating"
            for module in state.modules:
                path, text = run.modules[module.name]
                module.status = "translating"
                module.iterations = 1
                run.evidence.append("patch_applied", "SIMULATED translation; no files written.", module.name)
                await self._pause()
                module.status = "testing"
                run.evidence.append("test_result", "SIMULATED test execution in progress.", module.name)
                await self._pause()
                module.status = "green"
                module.tests_passed = module.tests_total
                state.metrics.tests_passed += module.tests_passed
                state.metrics.lines_migrated += len(text.splitlines())
                # Demo estimates only: never accounted as actual LLMClient usage.
                state.metrics.tokens_in += max(100, len(text) // 4) + 160
                state.metrics.tokens_out += max(30, len(text) // 4)
                state.metrics.cost_usd = round(
                    (state.metrics.tokens_in * 1.25 + state.metrics.tokens_out * 4.25) / 1_000_000, 6,
                )
                run.evidence.append("test_result", f"SIMULATED: {module.tests_total}/{module.tests_total} match; no tests ran.", module.name)
                self._findings(run, path, text)
                await self._pause()
            state.phase = "security"
            state.security.before = len(state.security.findings)
            state.security.after = state.security.before
            await self._pause()
            for finding in state.security.findings:
                if "MD5" in finding.note or "pickle" in finding.note:
                    finding.status = "needs_review"
                    finding.note += " Simulated review: changing the format may change behavior."
                else:
                    finding.status = "fixed"
                    finding.note += " Simulated fix only; source has not been modified."
                    state.security.after -= 1
                    run.evidence.append("security_fix", f"SIMULATED remediation of {finding.id}; no fix applied.")
            await self._pause()
            state.phase = "reporting"
            await self._pause()
            state.hashes["unchanged"] = hashes_for(run.source) == run.originals
            if not state.hashes["unchanged"]:
                raise RunError(409, "source_changed", "Original files changed during the run.")
            state.status = "done"
            run.evidence.append("run_finished", "SIMULATED run complete. Real original file hashes are unchanged.")
        except asyncio.CancelledError:
            self._fail(run, "run_interrupted", "Run interrupted by application shutdown.")
            raise
        except Exception as exc:
            code = exc.code if isinstance(exc, RunError) else "simulation_failed"
            message = exc.message if isinstance(exc, RunError) else "The simulated worker failed."
            self._fail(run, code, message)
        finally:
            state.metrics.seconds = round(monotonic() - run.started, 3)
            state.chain_intact = run.evidence.verify()
            self.active = None

    @staticmethod
    def _fail(run: Run, code: str, message: str):
        run.state.status = "failed"
        run.state.error = Error(code=code, message=message)
        run.evidence.append("error", message)
        run.evidence.append("run_finished", "Run failed; no migration was verified.")

    @staticmethod
    def _findings(run: Run, path: str, text: str):
        # These string matches populate the demo UI, not a Bandit/security scan.
        rules = (
            (r"\beval\s*\(", "HIGH", "eval may execute input"),
            (r"\bpickle\.(load|loads)\s*\(", "HIGH", "pickle may deserialize executable objects"),
            (r"\bmd5\s*\(", "MEDIUM", "MD5 output may require a behavior-changing fix"),
            (r"shell\s*=\s*True", "HIGH", "shell=True may allow command injection"),
            (r"(?i)\bSELECT\b.*%", "MEDIUM", "formatted SQL may allow injection"),
        )
        for line, content in enumerate(text.splitlines(), 1):
            for pattern, severity, description in rules:
                if re.search(pattern, content):
                    finding = Finding(
                        id=f"SIM-{len(run.state.security.findings) + 1:03d}",
                        file=path, line=line, severity=severity, status="open",
                        note=f"SIMULATED finding (text heuristic, not Bandit): {description}.",
                    )
                    run.state.security.findings.append(finding)
                    run.evidence.append("security_finding", finding.note)

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
