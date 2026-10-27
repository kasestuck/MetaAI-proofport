"""Bounded Docker execution of read-only working copies, never host Python."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import threading
from time import monotonic
from uuid import uuid4


class SandboxError(RuntimeError):
    pass


def find_docker() -> str | None:
    executable = shutil.which("docker")
    if executable:
        return executable
    for root in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DockerDesktop",
                 Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Docker/Docker"):
        candidate = root / "resources/bin/docker.exe"
        if candidate.is_file():
            return str(candidate)
    return None


@dataclass(frozen=True)
class Result:
    image: str
    exit_code: int
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool = False
    output_exceeded: bool = False

    def summary(self) -> dict:
        return {key: value for key, value in asdict(self).items() if key not in {"stdout", "stderr"}}


class DockerRunner:
    def __init__(self, timeout: float = 30, max_output: int = 1_048_576):
        if not math.isfinite(timeout) or not 0 < timeout <= 300 or not 0 < max_output <= 8_388_608:
            raise SandboxError("Sandbox timeout/output limits must be finite, positive and bounded.")
        self.executable = find_docker()
        self.timeout = timeout
        self.max_output = max_output
        self.tools = Path(__file__).resolve().parent
        self._images: dict[str, str] = {}
        self._active: set[str] = set()
        self._lock = threading.Lock()
        self.cancelled = threading.Event()

    def _metadata(self, args: list[str], timeout: float = 5) -> subprocess.CompletedProcess:
        if not self.executable:
            raise SandboxError("Docker CLI was not found; host execution is forbidden.")
        try:
            return subprocess.run(
                [self.executable, *args], capture_output=True, timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            raise SandboxError("Docker metadata request failed or timed out.") from None

    def available(self) -> bool:
        try:
            result = self._metadata(["info", "--format", "{{.OSType}}"])
            return result.returncode == 0 and result.stdout.strip() == b"linux"
        except SandboxError:
            return False

    def image_id(self, tag: str) -> str:
        if tag not in self._images:
            result = self._metadata(["image", "inspect", "--format", "{{.Id}}", tag])
            image = result.stdout.decode().strip()
            if result.returncode or not image.startswith("sha256:"):
                raise SandboxError(f"Required local Docker image is unavailable: {tag}. Pull/build it first.")
            self._images[tag] = image
        return self._images[tag]

    def cancel(self):
        self.cancelled.set()
        with self._lock:
            names = list(self._active)
        for name in names:
            self._metadata(["rm", "--force", name])

    def run(self, image: str, source: Path, command: list[str], payload: dict | None = None,
            timeout: float | None = None) -> Result:
        if timeout is not None and (not math.isfinite(timeout) or not 0 < timeout <= 300):
            raise SandboxError("Sandbox timeout must be finite and between zero and 300 seconds.")
        if self.cancelled.is_set():
            raise SandboxError("Sandbox execution was cancelled.")
        source = source.resolve(strict=True)
        if not source.is_dir() or "," in str(source) or "," in str(self.tools):
            raise SandboxError("Sandbox source must be a directory without commas in its path.")
        image_id = self.image_id(image)
        name = "proofport-" + uuid4().hex
        self.last_container = name
        args = [
            self.executable, "run", "--name", name, "--rm", "--pull", "never", "--init", "-i",
            "--network", "none", "--read-only", "--user", "65534:65534", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--cpus", "1", "--memory", "256m",
            "--memory-swap", "256m", "--pids-limit", "32", "--shm-size", "8m",
            "--ulimit", "nofile=64:64", "--log-driver", "none", "--stop-timeout", "1",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
            "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONHASHSEED=0",
            "--env", "HOME=/tmp", "--env", "LANG=C.UTF-8",
            "--mount", f"type=bind,source={source},target=/src,readonly",
            "--mount", f"type=bind,source={self.tools},target=/tools,readonly",
            "--workdir", "/tmp", image_id, *command,
        ]
        body = json.dumps(payload or {}, ensure_ascii=True).encode()
        if len(body) > self.max_output:
            raise SandboxError("Sandbox input is too large.")
        started = monotonic()
        output = [bytearray(), bytearray()]
        overflow = threading.Event()
        output_lock = threading.Lock()
        with self._lock:
            self._active.add(name)
        proc = None
        threads = []
        timed_out = False
        try:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

            def read(pipe, index):
                while chunk := pipe.read(4096):
                    with output_lock:
                        remaining = self.max_output - sum(len(part) for part in output)
                        output[index].extend(chunk[:max(0, remaining)])
                        if len(chunk) > remaining:
                            overflow.set()

            def write():
                try:
                    proc.stdin.write(body)
                    proc.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

            for pipe, index in ((proc.stdout, 0), (proc.stderr, 1)):
                thread = threading.Thread(target=read, args=(pipe, index), daemon=True)
                thread.start()
                threads.append(thread)
            writer = threading.Thread(target=write, daemon=True)
            writer.start()
            while proc.poll() is None:
                timed_out = monotonic() - started > (timeout if timeout is not None else self.timeout)
                if timed_out or overflow.is_set() or self.cancelled.is_set():
                    self._metadata(["rm", "--force", name])
                    proc.kill()
                    break
                try:
                    proc.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    pass
            proc.wait(timeout=5)
            writer.join(timeout=2)
            for thread in threads:
                thread.join(timeout=2)
            return Result(image_id, proc.returncode, *(part.decode("utf-8", errors="replace") for part in output),
                          round(monotonic() - started, 3), timed_out, overflow.is_set())
        except OSError:
            raise SandboxError("The Docker process could not be started.") from None
        finally:
            try:
                self._metadata(["rm", "--force", name])
            finally:
                with self._lock:
                    self._active.discard(name)
                if proc is not None:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=5)
                    for pipe in (proc.stdin, proc.stdout, proc.stderr):
                        if pipe and not pipe.closed:
                            pipe.close()
