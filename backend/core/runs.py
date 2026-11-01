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
from backend.core.control_models import ControlError, RunSpec
from backend.core.projects import source_files
from backend.sandbox.runner import DockerRunner, SandboxError


class RunError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


IGNORED = {".git", ".venv", "__pycache__", ".pytest_cache"}


def hashes_for(source: Path) -> dict[str, str]:
    if source.is_file():
        return {path.name: sha256(path.read_bytes()).hexdigest() for path in source_files(source)}
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
    spec: RunSpec | None = None
    use_real: bool = False
    pending_status: str | None = None
    finalizing: bool = False
    finalized: bool = False


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

    def start(self, source_path: str, max_iterations: int, *, spec: RunSpec | None = None) -> str:
        # No await between the busy check and reserving the run slot.
        if self.active is not None:
            raise RunError(409, "run_busy", "Another run is already in progress.")
        source = Path(source_path).expanduser()
        if not source.is_absolute():
            source = self.root / source
        source = source.resolve()
        pipeline = spec.pipeline if spec else self.pipeline
        php = bool(spec and spec.language == "php")
        universal = pipeline in {"analyze", "audit", "compatibility"}
        if not source.is_dir() and not ((universal or php) and source.is_file() and source.suffix == (".php" if php else ".py")):
            raise RunError(400, "source_not_found", "The source folder does not exist.")
        try:
            originals = hashes_for(source)
            modules = {}
            states = []
            for path in source_files(source):
                if path.suffix != (".php" if php else ".py"):
                    continue
                relative = Path(path.name) if source.is_file() else path.relative_to(source)
                name = ".".join(relative.with_suffix("").parts)
                text = path.read_text(encoding="utf-8", errors="replace")
                modules[name] = (f"{source.name}/{relative.as_posix()}", text)
                functions = len(re.findall(r"^\s*def [a-zA-Z]\w*\(", text, re.MULTILINE))
                cases = max(8, min(15, functions * 3)) if pipeline == "simulation" else 0
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
        controlled = spec is not None
        if spec and tuple(sorted(originals.items())) != spec.source_hashes:
            raise RunError(409, "source_changed", "Project changed after preflight; create a new request.")
        simulation = pipeline == "simulation"
        if spec is None:
            operation = "migration" if pipeline in {"verify", "fixtures", "simulation"} else pipeline
            execution = {"simulation": "simulation", "fixtures": "offline_fixtures", "verify": "live"}.get(pipeline, "offline")
            spec = RunSpec(operation, "legacy", str(source), self.settings.get("PROOFPORT_SOURCE_VERSION"),
                           self.settings.get("PROOFPORT_TARGET_VERSION"), execution, pipeline, max_iterations,
                           settings=tuple(sorted((key, str(value)) for key, value in self.settings.items()
                                                 if value is not None and key in {
                                                     "SANDBOX_TIMEOUT_SECONDS", "PROOFPORT_CASES_FILE", "PROOFPORT_FIXTURE_FILE",
                                                     "PROOFPORT_SECURITY_FIXTURES", "PROOFPORT_SOURCE_VERSION", "PROOFPORT_TARGET_VERSION",
                                                     "PROOFPORT_VERIFY_RUNTIME", "PROOFPORT_VERIFICATION_LEVEL", "PROOFPORT_REQUIRED_TESTS"})),
                           source_hashes=tuple(sorted(originals.items())))
        run = Run(state, source, originals, modules, max_iterations, simulation=simulation)
        run.spec = spec
        run.use_real = (not simulation) if controlled else self.real_enabled
        if controlled:
            run.verification["control"] = {"parameters": spec.public(), "live_enabled": False}
        notice = (
            "SIMULATED run: no code execution, migration, model calls, or security fixes."
            if simulation else "Static source inventory only; no code execution, migration, tests, or security scan."
        )
        run.evidence.append("run_started", notice)
        run.evidence.append("hashes_recorded", f"SHA-256 recorded from {len(originals)} actual source files.")
        run_id = uuid4().hex
        self.runs[run_id] = run
        self.active = run_id
        task = asyncio.create_task(self._dispatch(run_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return run_id

    def get(self, run_id: str) -> Run:
        if run_id not in self.runs:
            raise RunError(404, "run_not_found", "The requested run does not exist.")
        run = self.runs[run_id]
        if run.state.status in {"queued", "running"} and not run.finalizing:
            run.state.metrics.seconds = round(monotonic() - run.started, 3)
        run.state.chain_intact = run.evidence.verify()
        if not run.state.chain_intact and run.state.status == "done":
            run.state.status = "failed"
            run.state.error = Error(code="evidence_corrupted", message="Persisted evidence was modified; verification can no longer be trusted.")
        return run

    async def _pause(self):
        await asyncio.sleep(self.step_seconds)

    async def _dispatch(self, run_id):
        run = self.runs[run_id]
        pipeline = run.spec.pipeline
        worker = self._universal_pipeline if pipeline in {"analyze", "audit", "compatibility"} else (self._simulate if run.simulation else (self._real_pipeline if run.use_real else self._verification_unavailable))
        if run.spec.language == "php": worker = self._php_pipeline
        try:
            await worker(run_id)
        except asyncio.CancelledError:
            run.pending_status = "failed"
            run.state.error = Error(code="run_interrupted", message="Run interrupted by application shutdown.")
            raise
        except ControlError as exc:
            self._fail(run, exc.code, exc.message)
        except Exception:
            self._fail(run, "verification_unavailable", "Worker could not complete; no success is claimed.")
        finally:
            run.finalizing = True
            try:
                if run.workspace:
                    await asyncio.to_thread(self._finish, run)
                else:
                    self._finish(run)
            finally:
                self.active = None

    @staticmethod
    def _finish(run):
        terminal = run.pending_status or "failed"
        try:
            run.state.phase = "reporting"
            run.state.metrics.seconds = round(monotonic() - run.started, 3)
            run.state.hashes["unchanged"] = hashes_for(run.source) == run.originals
            if not run.state.hashes["unchanged"]:
                terminal = "failed"
                run.state.error = Error(code="source_changed", message="Original sources changed during the run.")
            run.state.chain_intact = run.evidence.verify()
            if not run.state.chain_intact:
                terminal = "failed"
                run.state.error = Error(code="evidence_corrupted", message="Evidence integrity failed.")
            if terminal == "failed":
                for module in run.state.modules:
                    module.status = "failed"
            if run.workspace:
                import json
                from backend.core.report import report_data, render_html
                data = report_data(run, status=terminal)
                for name, content in (("report.json", json.dumps(data, indent=2, ensure_ascii=True)), ("report.html", render_html(data))):
                    temporary = run.workspace / (name + ".tmp")
                    temporary.write_text(content, encoding="utf-8")
                    temporary.replace(run.workspace / name)
        except Exception:
            terminal = "failed"
            run.state.error = Error(code="report_unavailable", message="Finalization failed; report or hash verification could not complete.")
            for module in run.state.modules:
                module.status = "failed"
        finally:
            run.state.status = terminal
            run.finalized = True
            run.finalizing = False

    def _runner(self, run):
        settings = dict(run.spec.settings)
        runner = DockerRunner(timeout=float(settings.get("SANDBOX_TIMEOUT_SECONDS", "30")))
        for tag, expected in run.spec.images:
            if runner.image_id(tag) != expected:
                raise ControlError("runtime_changed", "Runtime image changed after preflight; request a new preflight.", 503)
        return runner

    async def _real_pipeline(self, run_id: str):
        from backend.core.pipeline import execute
        run = self.runs[run_id]
        try:
            run.runner = self._runner(run)
        except (ValueError, SandboxError):
            self._fail(run, "invalid_settings", "SANDBOX_TIMEOUT_SECONDS must be finite, positive and at most 300 seconds.")
            return
        mode = "fixtures" if run.spec.pipeline == "fixtures" else "live"
        worker = asyncio.create_task(asyncio.to_thread(execute, run, run_id, self.root, dict(run.spec.settings), mode))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            await asyncio.to_thread(run.runner.cancel)
            await worker
            raise

    async def _universal_pipeline(self, run_id: str):
        from backend.core.universal import execute
        run = self.runs[run_id]
        try:
            run.runner = self._runner(run)
        except (ValueError, SandboxError):
            self._fail(run, "invalid_settings", "Invalid Docker timeout; select 0 < seconds <= 300.")
            return
        worker = asyncio.create_task(asyncio.to_thread(execute, run, run_id, self.root, dict(run.spec.settings), run.spec.pipeline))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            await asyncio.to_thread(run.runner.cancel)
            await worker
            raise

    async def _php_pipeline(self, run_id):
        from backend.php.worker import execute_run
        run = self.runs[run_id]
        run.runner = self._runner(run) if run.spec.operation != "audit" else None
        worker = asyncio.create_task(asyncio.to_thread(execute_run, run, run_id, self.root, dict(run.spec.settings)))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            if run.runner: await asyncio.to_thread(run.runner.cancel)
            await worker
            raise

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
            run.pending_status = "done"
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

    @staticmethod
    def _fail(run: Run, code: str, message: str):
        run.state.status = "running"
        run.pending_status = "failed"
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
