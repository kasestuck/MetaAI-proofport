# Proofport backend

Python 3.12, FastAPI, Docker-only Python 2.7 to Python 3.12 verification.
Endpoint paths and state fields follow the existing shared contract. Frontend
is untouched. See `ARCHITECTURE.md` for the staged plan and historical audit.

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

`start.bat` creates `.venv`, installs `backend/requirements.txt`, starts uvicorn
at `http://127.0.0.1:8000`, and opens the browser after readiness. Ctrl+C stops
it. Set `PROOFPORT_PORT=8001` if needed. API docs: `/docs`.

## Live Meta migration

Create an untracked `.env` in the repo root with genuine provider settings:

```dotenv
PROOFPORT_PIPELINE=verify
PROOFPORT_CASES_FILE=tests/fixtures/legacy_shop/cases.json
LLM_MODE=live
MODEL_API_KEY=your-private-key
MODEL_NAME=your-provisioned-model
MODEL_BASE_URL=https://api.meta.ai/v1
PRICE_IN_PER_MTOK=1.25
PRICE_OUT_PER_MTOK=4.25
SANDBOX_TIMEOUT_SECONDS=30
```

Environment variables override `.env`; clear fixture-mode terminal settings
before switching to live mode. Missing credentials produce `model_unavailable`,
even after successful golden recording. There is no automatic fixture fallback.
The SDK uses a 30-second request timeout and at most two retries. The live
translate/fix path is connected but no actual Meta request has been validated
here: the key/model are not configured. Health reports configuration, not
provider access. Replay is still unimplemented and cannot count as model use.

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
remain `open` or `needs_review`. No automatic fix or security certification is
claimed. Source snippets and hard-coded secret values are omitted from stored
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

Enabled integration tests require the real sample and all three local images;
missing prerequisites fail rather than producing synthetic passing results.
Readiness exit 2 means configuration is incomplete. Exit 0 permits an attempt,
not a claim that a provider request or migration has succeeded.
