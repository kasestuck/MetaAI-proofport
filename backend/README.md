# Proofport backend

## Current release entry point (P10)

Use the [root README](../README.md) and [release report](../docs/RELEASE_READINESS.md)
for the current integrated Python/PHP application. Genuine scoped Meta migrations
and a rejected real security proposal are documented in P82/P83/P84 result files.
Explicit response replay is implemented internally; public live generation stays
disabled. `python -m backend.release prepare-demo` exports checked saved evidence,
not a new model run. API operation selection uses per-run UI controls.

**The P0–P5 notes below are historical**, including their earlier unverified-model
and unimplemented-replay statements. They are not current readiness claims.

Python 3.12, FastAPI, Docker-only Python 2.7 to Python 3.12 verification.
Endpoint paths and state fields follow the existing shared contract. Frontend
is untouched. See `ARCHITECTURE.md` for the staged plan and historical audit.

## Per-run API control plane (P4.1)

The additive `/api/v1` API selects migration, audit or compatibility per run,
with immutable parameters, project path policy, preflight and image readiness.
Legacy endpoints remain. Live Meta stays disabled; no environment edits are
needed for choosing offline operations. See [API_CONTROL_PLANE.md](API_CONTROL_PLANE.md)
for requests, supported combinations, legacy path restrictions and Claude Code
integration instructions. Frontend changes are a separate task.

## Offline universal Python workflows (P3)

See [UNIVERSAL.md](UNIVERSAL.md) for the runtime registry, conservative version
detection, Python 3 analysis, security audit without migration, and actual
Docker compatibility checks. These modes do not call Meta or change source.
Configured versions are candidates until explicit runtime checks pass; project
compatibility requires its own test/behavior evidence. The existing HTTP
contract and Python 2.7 -> 3.12 migration mode are preserved.

## Project and trusted images

The unpacked root is `samples/legacy_shop`, containing `tests/`, `sample_data/`,
and the inner package `legacy_shop/`. Pass that outer directory as `source_path`;
the inner package alone omits its tests and data. The original 15 files remain
unchanged. This project has 10 tests, not the 11 in the earlier specification.

```powershell
docker pull python:2.7
docker pull python:3.12-slim
docker build -t proofport-bandit:1.8.6 -f backend/sandbox/Dockerfile.bandit backend/sandbox
```

Networking is used only during trusted image/dependency setup. Project
execution and scanning are offline. The runner resolves local tags to immutable
image IDs, records them, and never pulls during execution. CLI discovery also
checks the per-user Docker Desktop installation under
`%LOCALAPPDATA%/Programs/DockerDesktop/resources/bin` if it is not in PATH.
For manual setup commands, add that directory to terminal PATH when needed.

## Explicit fixtures: real verification, no AI

From a PowerShell terminal at the repo root:

```powershell
$env:LLM_MODE = 'mock'
$env:PROOFPORT_PIPELINE = 'fixtures'
$env:PROOFPORT_CASES_FILE = 'tests/fixtures/legacy_shop/cases.json'
$env:PROOFPORT_FIXTURE_FILE = 'tests/fixtures/legacy_shop/patches.json'
.\start.bat
```

POST `{"source_path":"samples/legacy_shop","max_iterations":2}` to `/api/runs`.
Fixtures are authored inputs and source-hash-bound compatibility patches,
**not expected outputs or Meta responses**. Expected results are recorded by
executing originals in Docker Python 2.7. Candidates, all golden comparisons,
and the same existing test IDs run in Docker Python 3.12. Fixture runs consume
zero model tokens and are never presented as AI migration.

For P2 security verification, also set
`PROOFPORT_SECURITY_FIXTURES=tests/fixtures/security/legacy_shop_fixes.json`
before starting the app. See [SECURITY.md](SECURITY.md) for actual outcomes,
rollback/status semantics and the disabled future Meta interface. This stage
is offline only; selecting security fixtures with live/replay migration is
rejected before any SDK call. Four incompatible legacy proposals require
review rather than being silently applied.

`start.bat` creates `.venv`, installs `backend/requirements.txt`, starts uvicorn
at `http://127.0.0.1:8000`, and opens the browser after readiness. Ctrl+C stops
it. Set `PROOFPORT_PORT=8001` if needed. API docs: `/docs`.

## Meta live readiness (P5.1)

Live migration and AI Security Fix remain disabled. The standalone
client now needs explicit authorization/limits, sends no automatic retries, and
has a separate one-request smoke with an offline default. Follow
[META_LIVE_READINESS.md](META_LIVE_READINESS.md) for current credential, budget,
error-handling and first-call instructions. No actual Meta request has been
verified. No `.env` setting alone enables the control-plane/worker live gates.

An offline preview, safe even when credentials are configured:

```powershell
.venv/Scripts/python.exe -m backend.llm.smoke
```

The separate executed smoke requires explicit paid-call acknowledgment, a
dollar cap and verified model pricing. It sends only synthetic connectivity
input, not project sources. Health reports configuration, not provider access.
Replay remains unimplemented and cannot count as model use.

Without explicit golden inputs or working Docker, requests only inventory/hash
sources and fail without fictional successes. `PROOFPORT_PIPELINE=simulation`
and `LLM_MODE=mock` retain the old labelled frontend demo with fictional
metrics. The separate `fixtures` mode performs real container verification.

## Verification, safety and artifacts

The source-interpreter AST analyzer does not import target modules. The worker
orders dependencies, records behavior and existing tests, translates candidates,
compiles under the target interpreter, compares cases and test IDs, and supplies
failure evidence to subsequent iterations. Missing coverage, an empty/failing
baseline suite, changed test IDs, compile errors, or exhausted mismatches cannot
produce success. Test sources are not rewritten to make candidates pass;
Python 2-only test syntax requires a separately reviewed port.

The harness captures tagged values, exceptions, stdout/stderr, object scenarios
and selected file/SQL operations. Only documented text/bytes and errno-backed
I/O-name differences are allowed and reported. Dict/set order is ignored;
sequence order, value types, floats and output text remain exact. This proves
recorded cases, not every input or side effect. Fixture patches for eval and
CSV diagnostics cover selected expressions and this dataset; arbitrary eval
namespaces, Python 2 hash ordering and pickle-format interoperability are not
exhaustively verified.

Every project execution uses Docker with a non-root UID, disabled networking,
read-only source/tool/root mounts, dropped capabilities, no-new-privileges,
CPU/memory/swap/PID/descriptor limits, bounded temp/output, timeout and container
cleanup. No model key, Docker socket or writable host volume is exposed to the
project. There is no host Python fallback. These controls are integration-tested;
Docker is not a universal guarantee against hostile native/kernel exploits.

Bandit 1.8.6 scans read-only copies offline. It cannot parse four original
Python 2 files, so the initial scan is explicitly partial. The Python 3 scan
covers all files. Findings include CWE, severity, confidence and location and
default to `open` or `needs_review`. Optional P2 can verify narrow fixture
hardening and contextual triage, or reject/review proposals after real checks;
it is not a security certification or validated AI remediation. Source snippets and hard-coded secret values are omitted from stored
scanner results. A clean scan would not prove complete security.

Real runs persist `backend/.work/<run_id>/` (git-ignored): `copy/`, `migrated/`,
original hashes, analysis, `golden.json`, legacy/target test outcomes,
comparisons per iteration, before/after scans, append-only hash-chained
`evidence.log`, `report.json` and `report.html`. Original hashes and the persisted
chain are rechecked. API state is in memory; artifacts survive restart but API
resume/history loading is not implemented.

## Tests and diagnostics

```powershell
# Unit/API tests; Docker tests are visibly skipped by default.
.venv/Scripts/python.exe -m pytest tests -q

# Real integration, isolation limits, original/candidate behavior and failures.
$env:PROOFPORT_DOCKER_TESTS = '1'
.venv/Scripts/python.exe -m pytest tests -q

# Read-only configuration preflight; no model call or project execution.
.venv/Scripts/python.exe -m backend.core.readiness
```

Enabled integration tests require the real sample and the four local images
(including python:3.13-slim for P3);
missing prerequisites fail rather than producing synthetic passing results.
Readiness exit 2 means configuration is incomplete. Exit 0 permits an attempt,
not a claim that a provider request or migration has succeeded.
