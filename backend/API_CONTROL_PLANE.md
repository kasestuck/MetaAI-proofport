# P4.1: API Control Plane

P6.1 additive discovery update on integration/p4: GET capabilities now includes
optional `languages` metadata; GET projects and project resolution add language
inventory, nullable source/target versions and readiness. GET projects also adds
per-project `available_profiles`. All original fields/endpoints, Python operation
matrices, request DTOs, frozen RunSpec/public parameters and report shapes remain.
PHP images are only configured candidates, never verified operation support.
PHP-only runs fail preflight/creation with `language_not_enabled`; the legacy
error envelope is preserved. Existing Python requests on mixed projects retain
their Python-only scope and make no PHP verification claims. See
[PHP_FOUNDATION.md](PHP_FOUNDATION.md) for exact semantics and future stages.

Implemented on `backend/codex`, 2026-11-01. Frontend is unchanged. This is an
additive, local, single-process control API; it does not enable live Meta AI.
The five legacy routes, StartRun/RunState schemas and report envelope remain.

## Routes

| Method and path | Success | Meaning |
| --- | --- | --- |
| GET /api/v1/capabilities | 200 | Docker/image metadata, configured/available/verified runtimes, allowed operation combinations |
| GET /api/v1/projects | 200 | Registered projects and server-bound cases/fixture profiles |
| POST /api/v1/projects/resolve | 200 | Register a safe workspace-relative project |
| POST /api/v1/runs/preflight | 200 | `can_start`, normalized parameters or blocking errors; does not create a job |
| POST /api/v1/runs | 202 | `{"run_id": "..."}`; one shared worker slot with legacy POST |
| GET /api/v1/runs/{id} | 200 | Immutable parameters, lifecycle/finalized, provenance, partial results and legacy state |

Every new route is registered before the static frontend mount. Existing
`/api/health`, POST `/api/runs`, GET `/api/runs/{id}`, events and report routes
keep their contracts. New run IDs work with the old state/events/report routes.
No upload, clone, runtime installation, config-writing, cancellation or remote
multi-user/authentication feature is added.

## Capabilities and readiness

The response includes `api_version: "1"`, `instance_id`, `checked_at`,
`cache_ttl_seconds: 5`, `docker.available`, `runtimes[]`, `scanner`,
`operations`, `live`, `ai_security_fix` and a verification-scope explanation.

Each runtime has configured/available/verified, version, image/image_id,
source/target role flags and (when verified) the actual `python` version tuple
from its image-bound receipt. A metadata timeout may give `available: null`,
`verified: false`, `reason: "metadata_unavailable"`. It must stay disabled.
Version 2.7 is source-only. Configured 3.8/3.10/3.14 are not enabled merely
because someone has installed their images.

Allowed adapter combinations are deliberately limited:

| Operation | Versions | Execution modes |
| --- | --- | --- |
| migration | 2.7 -> 3.12 only | offline_fixtures; separate simulation demo |
| audit | source 2.7, 3.12, 3.13; no target | offline |
| compatibility | 3.12 -> 3.12, 3.12 -> 3.13, 3.13 -> 3.12 | offline |

Real operations also require current local verified images. Supporting a
compatibility check means the backend can test the pair, including reporting
incompatibility; it does not promise that the supplied project will pass.
Audit coverage can be partial with Python 2/new grammar because Bandit uses
its separate Python 3.12 image.

Metadata probes do not have a container `run` method. They only inspect local
Docker information/images with a shared eight-second probe budget. They do
not pull, run runtime self-tests, execute the project, contact Meta or test a
paid model connection. Preflight bypasses the cached capability snapshot;
creation repeats preflight, snapshots source hashes and pins image IDs. The
worker rechecks pinned images and the copies are hash-checked before use.

Runtime receipt invalidation requires an explicit operator action, for example
`python -m backend.universal registry --verify 3.12`, using an already installed
image. This is not automatically triggered by browser reads or preflight.

## Projects and profiles

Default project IDs:

- `legacy_shop`: `samples/legacy_shop`.
- `universal_py3`: `tests/fixtures/universal_py3`.
- `security_subject`: `tests/fixtures/security_subject`.

GET projects returns availability/reasons, relative paths, `root_id: workspace`,
`cases_profiles[]` and `fixture_profiles[]`. A listed profile's available flag
checks its file presence; complete validation and source binding happen in
preflight. Example custom-project registration:

```json
{"root_id": "workspace", "relative_path": "samples/my_project"}
```

Resolve returns project_id, relative_path and kind (file/directory). Use the
returned project ID in subsequent requests. IDs/registrations are local to
this server instance; the three defaults are recreated at startup.

Cases profiles: `legacy_shop_golden`, `universal_py3_golden`,
`security_subject_golden`. Migration fixture profile:
`legacy_shop_py27_py312`. Profiles are bound to their registered project;
the migration manifest additionally must match source hashes. Clients cannot
pass arbitrary profile paths, Docker images, commands, mounts or API keys.
An arbitrary custom project does not acquire offline migration patches or
golden inputs automatically. It can use supported audit/syntax/tests checks;
behavior verification requires an available project-bound cases profile.

## Request contract

ControlRequest rejects extra fields and is frozen. Common fields:

| Field | Rule |
| --- | --- |
| operation | migration / audit / compatibility |
| project_id | Required registered ID, 1..128 characters |
| source_version / target_version | Configured minor-version strings, subject to role/pair and verified-image policy |
| execution_mode | offline_fixtures / offline / simulation / live; default offline |
| fixture_profile_id / cases_profile_id | Optional IDs; operation-specific requirements |
| verification_level | syntax / tests / behavior, or omitted |
| max_iterations | Strict integer 1..5, default 5; translation setting only |

Migration example, valid for preflight and creation:

```json
{
  "operation": "migration",
  "project_id": "legacy_shop",
  "source_version": "2.7",
  "target_version": "3.12",
  "execution_mode": "offline_fixtures",
  "fixture_profile_id": "legacy_shop_py27_py312",
  "cases_profile_id": "legacy_shop_golden",
  "max_iterations": 1
}
```

Migration always requires complete behavior verification; omit verification_level
or set behavior. Source must be a directory. There is no generic offline
translator and no silent live-to-fixture fallback.

Audit example:

```json
{"operation": "audit", "project_id": "legacy_shop", "source_version": "2.7", "execution_mode": "offline"}
```

Audit rejects target_version, cases/fixture profile and verification_level.
For audit/compatibility leave max_iterations at the default; other values
are rejected as incompatible translation settings. Audit does not execute
project modules, run their tests or apply fixes.

Compatibility example:

```json
{
  "operation": "compatibility",
  "project_id": "universal_py3",
  "source_version": "3.12",
  "target_version": "3.13",
  "execution_mode": "offline",
  "verification_level": "behavior",
  "cases_profile_id": "universal_py3_golden"
}
```

Compatibility defaults to tests. Syntax level does not execute project code.
Tests/behavior require a tests directory and an actually nonempty passing
unittest suite; behavior additionally requires the bound inputs and complete
positive application-module golden coverage. Missing coverage fails the
requested behavior operation even if a weaker check passed. Dependencies
are not installed/resolved and other test frameworks are not inferred.
Known source/target requires-python constraints are compared with actual
verified patch versions during preflight and again by the worker.

Simulation example:

```json
{"operation": "migration", "project_id": "legacy_shop", "execution_mode": "simulation"}
```

Simulation accepts no source/target versions, profiles or verification level.
It is a separate directory-based demo without Docker/runtime support claims.
Only inventory, source hashes and evidence bookkeeping are real; migration,
test/fix counters, tokens and costs are simulated and must be labeled.

`execution_mode: live` is accepted as a known enum solely to return a clear
403 live_disabled. Even configured MODEL_API_KEY/MODEL_NAME do not enable it.
The legacy verify worker also stops before constructing a translator/SDK.
LLMClient's standalone adapter remains for future authorized development,
but neither control plane nor migration worker enables paid generation here.
AI Security Fix and backend replay generation remain disabled.

## Preflight, creation, idempotency

POST preflight with a schema-valid request returns HTTP 200. On success:

```json
{
  "can_start": true,
  "errors": [],
  "parameters": {
    "operation": "audit", "project_id": "legacy_shop",
    "source_version": "2.7", "target_version": null,
    "execution_mode": "offline", "max_iterations": 5,
    "verification_level": null, "fixture_profile_id": null,
    "cases_profile_id": null
  },
  "scope": "Preconditions only; creation and worker repeat critical checks. No project code/model calls executed."
}
```

On failure: can_start=false, parameters contain the submitted/defaulted fields,
errors is an array of code/message/field objects. A busy worker blocks preflight.
Preflight does not reserve a slot; successful preflight does not guarantee that
a later creation or the actual project checks will succeed.

POST runs repeats preparation and atomically reserves the common slot. Success
is HTTP 202 with only run_id. Optional `Idempotency-Key` header is 8..128
alphanumeric/underscore/hyphen characters (UUIDs fit). Reusing a key for the
same normalized request returns the same run ID, including while busy or after
completion; changed parameters return 409 idempotency_conflict. Concurrent
same-key requests also create only one run. Failed creation does not reserve
the key. Guarantees are within instance_id; no durable history/restart resume
or multi-process scheduling is promised. Do not auto-repeat an unknown-result
POST without its original key.

## State, reports and provenance

GET v1 run returns:

- run_id and instance_id.
- parameters: the immutable public RunSpec; no settings, secrets or absolute
  source paths are serialized.
- lifecycle: queued/running/finalizing/done/failed.
- finalized: true only when the worker and finalization have finished and
  the shared slot is released.
- execution: effective mode, simulated, ai_generated=false, live_enabled=false.
- result: compatibility, security_audit, target_tests, security_fix and
  limitations; not-yet-produced sections are null/empty.
- state: the unchanged legacy RunState.

Every run, including legacy, gets its own frozen RunSpec. Execution settings,
source hash snapshot and pinned images are immutable tuples, not shared mutable
request dictionaries. Dispatch reads the run's spec, not current global mode.
V1 run settings never inherit global PROOFPORT_SECURITY_FIXTURES or model keys.
Neither request path changes os.environ, .env or RunStore defaults.

While reporting is finalizing, legacy state remains running with phase reporting;
legacy report endpoint returns 409. Terminal status is published after source
hash/evidence checks and atomic report replacement. Storage/finalization failure
produces failed/report_unavailable and releases the slot. Later evidence tampering
can still revoke a previously done state. Unknown phase/error values need a
frontend fallback. No percentage-of-time or ETA is invented.

Continue polling the old state/events endpoints if desired. Events use seq >
since and the old envelope. HTML/JSON report URLs are unchanged; reports for
new v1 runs add verification.control.parameters/live_enabled without changing
their root envelope. Simulation report notices remain explicitly SIMULATED.
Compatibility exposes independent syntax/tests/behavior checks; null is not
success. Audit completion is not a security certificate. Fixed findings from
existing offline security fixtures are not Meta AI fixes.

Frontend saved-report replay is read-only local viewing, not backend execution
or LLM_MODE=replay. A server-origin run is not necessarily live AI. The new
capabilities/live policy overrides any inference from legacy health.llm_mode.

## Path policy: intentional legacy access tightening

Both HTTP APIs use ProjectCatalog before recursive reads/hashing. The approved
root is this repository workspace; custom projects can live under an ordinary
subdirectory such as samples/my_project. Legacy paths may be relative or an
absolute path inside that root. V1 resolve accepts relative paths only.

Denied: traversal components, outside-root paths, drive-relative/UNC/device
paths, alternate-stream colons, root itself, backend/frontend/docs service
sources, tests outside tests/fixtures, hidden/service paths, and direct secret
files. Symlinks, Windows junction/reparse points and hard-linked visible files
require operator review. Selected files must be regular .py files. Directories
may contain at most 2000 visible files, 4000 entries and 16 MiB of content.

Hidden files, .git/.venv/work/caches/node_modules, known credential/secret files
and private-key extensions are excluded from copied/hashed project content.
Code, ordinary documentation, tests, JSON/CSV/config fixtures remain. Original
files are not edited or deleted. Excluded secret configuration is not injected
into Docker; projects depending on it may fail tests and require operator review.
This policy is not a general secret-content detector or protection against an
administrator concurrently rewriting local filesystem/registry state.

Legacy request/response shapes remain, but unsafe paths previously accepted by
POST /api/runs now get the existing error envelope (typically 403). This is an
explicitly approved security behavior change. Missing/empty normal projects
retain source_not_found/source_empty semantics. Trusted internal CLI callers
can select operator-supplied projects outside the HTTP workspace allowlist;
copied content still uses the shared link/secret/service policy.

This remains a loopback/local dashboard API without user authentication. Do not
expose it as a public multi-user service without authorization, origin/host
controls, project isolation, retention and durable job storage. Existing Docker
resource/network/filesystem restrictions remain; host execution fallback is absent.

## Errors

V1 policy errors have error.code/message/field (field can be null). Shared
validation, run lookup and legacy guards retain error.code/message. Clients
must tolerate the optional field. No input bodies, keys or source snippets
are echoed by validation errors.

| HTTP | Examples |
| --- | --- |
| 400/404 | source_not_found, source_empty, source_unreadable, project_not_found, run_not_found |
| 403 | unsafe_project_path, project_outside_root, live_disabled |
| 409 | run_busy, idempotency_conflict, source_changed |
| 413 | project_limit_exceeded |
| 422 | invalid_request, incompatible_parameters, unsupported_python_version, unsupported_migration_pair, unsupported_compatibility_pair, profile_unavailable, fixture_source_mismatch, tests_unavailable, source_version_conflict, source_metadata_conflict, target_metadata_conflict, project_metadata_invalid |
| 503 | docker_unavailable, runtime_unavailable, unverified_version, scanner_unavailable, runtime_metadata_unavailable, preflight_unavailable |

Worker failures are HTTP 200 state/status=failed, including runtime_changed after
preflight, insufficient_cases, verification errors and report_unavailable. Do not
turn a passed weaker check into a success verdict when the run failed.

## Instructions for Claude Code

1. Keep work in frontend/claude; do not overwrite backend. Fetch/integration/merge
   require the user's separate approval. Current preserved frontend tip is 968c5b8.
2. Add capability/project/preflight/start/detail methods in js/api.js; keep the
   five legacy methods for fallback. A v1 404 means old backend: preserve the
   current informational operation cards, do not send extra fields to legacy POST.
3. Replace config.deployment.pipeline inference with per-run parameters/effective
   mode when v1 is available. Health is liveness/config echo, not readiness.
4. Make Migration/Audit/Compatibility real controls. Filter choices by both the
   operation matrix and runtime available===true && verified===true/role flags.
   An image's presence alone never enables migration pairs.
5. Load server projects/profiles. Resolve a custom relative project path before
   constructing RunRequest. Do not send browser-local absolute paths or secrets.
6. Simulation disables version/profile controls; audit disables target/iterations;
   compatibility exposes syntax/tests/behavior; migration needs its bound offline
   profiles. Live and AI Fix stay visibly disabled with server reasons.
7. Preflight shows errors but does not lock the slot. Generate crypto.randomUUID()
   once per user submission and reuse it only for same-request retries. Preserve
   run_id; use instance_id to distinguish server restarts and missing jobs.
8. Keep cursor-based events/report downloads. Wait for finalized, preserve partial
   results/errors and display syntax/tests/behavior separately. Never label saved
   report viewing, simulation or offline fixtures as live Meta AI.

After separate approval, integration should start from the latest frontend tip
and merge the updated backend branch into an integration branch. Preserve all
Claude commits, including 349df64 and 968c5b8. Do not replace frontend wholesale,
force-update branches or cherry-pick only one frontend commit.

## Validation

Fast tests and the minimal P4.1 real Docker smoke are reported separately.
The older Docker stress/security-loop suites are deliberately not rerun here.
Enabled smoke uses only existing local 2.7/3.12/3.13/Bandit images and forbids
SDK construction/completion. Runtime receipts were explicitly reverified using
the shipped trusted self-tests; GET/preflight never does this automatically.
Generated logs/XML/reports remain ignored under backend/.tmp and backend/.work.

Final recorded results:

```text
pytest tests -q -m "not docker" -p no:cacheprovider
179 passed, 41 deselected in 6.64s

PROOFPORT_DOCKER_TESTS=1 pytest tests/test_control_integration.py -q -p no:cacheprovider
4 passed in 47.83s
```

The 41 deselected Docker cases include these four targeted smoke cases plus
37 older integration/stress cases. This stage verifies 183 selected tests;
it does not claim the full 220-case collection was run. Three installed runtime
images additionally passed their explicit trusted self-tests (two unittest
tests and two harness inputs per version), with no image downloads.

Actual HTTP/Docker outcomes: fixture migration 90/90 golden comparisons plus
10/10 target tests (the same ten original tests also passed on 2.7); audit
produced potential warnings without running the project or applying fixes;
3.12 -> 3.13 behavior check passed two cases and two tests; 3.12 -> 3.12
syntax-only check ran no project tests and claimed no behavior verification.
Source hashes, persisted JSON/HTML, legacy event/report access and zero model
usage were asserted. A finalization race affecting elapsed seconds was found
by the real smoke checks, fixed, regression-tested and rechecked successfully.
