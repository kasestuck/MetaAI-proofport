# Try Proofport — 10 Judge Test Scenarios

Ten owned, finite, **offline** scenarios. No API key, paid model request, image
download, external target/database or host execution of project code is involved.
The suite uses the existing Docker harnesses, comparators, security engines and
fixture pipeline; it is not a separate fake verifier. Run it from the full repo.

| ID | Scenario | Runtime(s) | Expected scenario status |
| --- | --- | --- | --- |
| [01](01_python_legacy_migration/README.md) | Full legacy Python fixture migration: 90 cases, 10 tests | 2.7 → 3.12 | PASS |
| [02](02_python_math_edge_cases/README.md) | Small math migration: 14 cases, 3 tests | 2.7 → 3.12 | PASS |
| [03](03_python_compatibility/README.md) | Unchanged project: 5 cases, 3 tests | 3.12 → 3.13 | PASS |
| [04](04_python_sql_injection/README.md) | SQL detection and changed query/API rejection | 3.12 | NEEDS_REVIEW |
| [05](05_python_unsafe_eval/README.md) | Eval detection and literal-only behavior rejection | 3.12 | NEEDS_REVIEW |
| [06](06_python_secrets_crypto/README.md) | Fake credential + MD5; config/hash-format rejection | 3.12 | NEEDS_REVIEW |
| [07](07_php_legacy_migration/README.md) | PHP fixture migration: 22 cases, 9 tests | 7.4 → 8.3 | PASS |
| [08](08_php_xss/README.md) | XSS detection; changed escaped output requires review | 7.4 and 8.3 | NEEDS_REVIEW |
| [09](09_php_command_injection/README.md) | One exact constant-command hardening verified | 7.4 and 8.3 | PASS |
| [10](10_php_security_regression/README.md) | Accepted hardening + crypto rejection + syntax rollback | 7.4 → 8.3; fixes checked on both | NEEDS_REVIEW |

Each directory contains English instructions, `scenario.json` and either a small
owned `project/` or an explicit necessary reference to an existing owned fixture.
01/07/10 avoid duplicating the full demo projects. Candidates are clearly authored
offline inputs, **not** recorded or new Meta answers. Input JSON contains calls,
not precomputed golden answers. Expected observations come from running originals
in Docker. Existing demo sources and historical Meta evidence stay read-only.

## Install and start

Windows, from repository root, with Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

If `.venv` already uses Python 3.12, keep it and install the pinned requirements.
The entry-point selection/summary code is standard-library Python; invoking the
actual backend engines requires the existing pinned backend dependencies. No new
runner dependency is added. Node is needed only for frontend regression tests.

Start Docker Desktop in **Linux container** mode. For all ten scenarios the local
images below are required. Install images explicitly if missing; these setup
commands use the network, but the suite itself never pulls or installs anything:

```powershell
docker info --format '{{.OSType}}'
docker pull python:2.7
docker pull python:3.12-slim
docker pull python:3.13-slim
docker pull php:7.4.33-cli
docker pull php:8.3.36-cli
docker build -t proofport-bandit:1.8.6 -f backend/sandbox/Dockerfile.bandit backend/sandbox
```

For one scenario, install only its listed images. Runtime tags are resolved to
local SHA-256 image IDs; project commands use the bounded non-root, no-network,
read-only Docker runner. There is no host fallback or automatic image download.
PHP source fixtures have LF checkout attributes because their manifests bind raw
bytes. No original fixture was rewritten to achieve that.

The CLI needs no running server or readiness receipt. To inspect the UI, run
`start.bat` and follow root README receipt setup/capabilities/preflight. The judge
runner does not silently enable new server capabilities. Never run project tests
directly on Windows, including the tests under these scenario directories.

## Run all / one / list

```powershell
judge_tests\run.bat
judge_tests\run.bat --scenario 05
judge_tests\run.bat --scenario 09_php_command_injection
judge_tests\run.bat --list
# Equivalent direct Python entry point:
.venv/Scripts/python.exe judge_tests/runner.py
```

Run sequentially. Each invocation creates a new ignored
`backend/.work/judge-<id>/` and prints its `summary.json` path. Completed per-case
results are retained even when another case fails. Nothing is deleted or published.
Do not run the full unrelated Docker matrix just to try these ten scenarios.

## Read results and exit codes

- **PASS:** required assertions passed for this finite scenario. Not universal
  compatibility, confirmed exploitability or a security certificate.
- **NEEDS_REVIEW:** an intentionally policy/behavior-changing proposal remains
  unaccepted. The scenario asserts actual detection, checks, rescan and rollback;
  those assertions can all pass. Scenario 10 also retains one separately verified
  narrow hardening; its rejected crypto proposal is still not approved.
- **FAIL:** a required assertion or execution/integrity check failed unexpectedly.
- **SKIP:** a mandatory Docker/image prerequisite was missing. No execution or
  success is invented; missing checks make the suite exit nonzero.

**Exit 0** means every selected scenario's required assertions completed/passed,
including an expected review/rollback decision. It never means all fixes were
accepted. **Exit 1** means required FAIL/SKIP; **exit 2** means invalid selection,
dependency/setup or saved-integrity error. Listing is metadata-only, not a test run.

Actual first full local result on the P11 workstation: **5 PASS, 5 NEEDS_REVIEW,
0 FAIL, 0 SKIP**, exit **0**. Do not copy that status onto a skipped run elsewhere.
Interpreter patch versions and image IDs are recorded in each run, not assumed.

## JSON, SHA-256 and evidence

Top-level summary: `counts`, `mandatory_checks_passed`, `model_calls: 0` and each
selected scenario. Per-case numeric folders (`01/`…`10/`) contain:

- `result.json`, `report.html`, `evidence.log`, `receipt.json`.
- Actual source-byte hashes, input/profile/candidate hashes, checks and reasons.
- Golden observations, existing test results and retained candidate artifacts.
- Full engine/pipeline reports where used, linked by relative artifact path.

Stage checks inside rejected attempts may correctly be false or not run. Those
are never relabelled passing just because the overall rejection scenario worked.
Recheck saved receipts, exact summary/result equality and the ordered chain with:

```powershell
.venv/Scripts/python.exe judge_tests/runner.py --verify-summary backend/.work/<judge-id>/summary.json
```

This makes no Docker/model request. Its exit is nonzero if integrity fails or the
saved suite's mandatory assertions did not pass. Hashes establish local consistency,
not external signatures against someone rewriting all artifacts.

## UI versus CLI and genuine Meta evidence

01/07 use the registered demo migration profiles. 10 uses PHP's optional existing
security fixture profile. Custom project audits can be resolved in the UI when
capabilities permit. 03 can use UI syntax/test compatibility; its custom golden
profile and all standalone custom patch verifications are CLI-only. Individual
READMEs give exact boundaries; do not invent profiles or AI Fix endpoints.

All ten scenarios are **offline**. The separate genuine historical Meta results
are Python mathutils **31/31 + 3/3**, PHP legacy.php **22/22 + 9/9**, and the rejected
eval proposal **5/9 + 0/1**. See the root README, P8 result documents and reviewed
saved-demo pack procedure. Private `.work` evidence is not bundled into a clone,
and replay never becomes a new live call. No API key is needed for this suite.

## Limits

Controlled fixtures only: no external attacks, live DB/server, personal data,
real credentials or network dependencies. PHP rules are lexical; original Python
2 Bandit coverage is partial. Source/test/golden behavior and security policy are
separate decisions. These checks do not promise all Python/PHP projects, all
frameworks, untested input behavior or complete vulnerability coverage.
