# P6.2 / P6.3 — verified offline PHP foundation

Implemented on `integration/p4`. This is authored fixture migration and finite
Docker verification, **not Meta AI migration, AI remediation, or universal PHP
support**. No model SDK, API key or paid request is used. Frontend and original
`samples/legacy_shop` are unchanged. See `PHP_FOUNDATION.md` for the earlier
P6.1 historical inventory and analyzer limitations.

## Architecture

`backend/php/` contains the independent protocol/comparator, fixed Docker harness
adapter, migration fixtures, transactional fix verifier, orchestrator, explicit
CLI, local proof receipts and control/worker bridges. Existing Python workers,
five legacy endpoints, RunState and report envelope remain intact. `PHPAdapter`
delegates compatibility to the PHP worker and security to the PHP scanner;
PHP is never parsed with Python AST or scanned with Bandit.

Flow: Analyze → Record → authored Translate candidate → Verify → next authored
candidate if necessary → Security scan → optional verified fix attempts → Report.
Each iteration has a retained copy and actual checks. Candidate exhaustion fails;
there is no fixture/model fallback. Per-run PHP parameters and image pins live
in frozen RunSpec, never server defaults, `.env` or `os.environ`.

Only copied projects execute, inside the existing DockerRunner: no network,
read-only root/source/tools mounts, non-root UID 65534, all capabilities dropped,
no-new-privileges, 1 CPU, 256 MiB memory/swap, 32 PIDs, 64 MiB temporary filesystem,
bounded input/output and default 30-second command timeout. No Docker socket,
model environment or arbitrary host directory is mounted. Containers are
ephemeral; **all working copies and reports are retained** in `backend/.work/`.

The sandbox test reads interfaces/routes (only loopback, no IPv4 routes), checks
denied source/root writes, allowed temporary writes, UID and absent key/socket.
It makes no external network connection. Docker isolation is not a guarantee
against kernel/container-runtime vulnerabilities or dishonest project tests.

## Real runtime proof and readiness

Only these two user-authorized official images were downloaded:

| Requested version | Actual interpreter | Inspected image ID |
| --- | --- | --- |
| PHP 7.4 | 7.4.33 | `sha256:620a6b9f4d4feef2210026172570465e9d0c1de79766418d3affd09190a7fda5` |
| PHP 8.3 | 8.3.36 | `sha256:600bce7c7acf524756e5aac989f4a763aed709960d7326970bb670f46efee53a` |

Tags: `php:7.4.33-cli`, `php:8.3.36-cli`. Actual PHP_VERSION is checked on every
harness invocation; image IDs are pinned. No automatic pulls, Composer installs
or dependency downloads. PHP 8.4 and other pairs are not enabled.

Configured image, local image availability, and verified operation are separate
facts. The explicit `verify-demo` command runs actual E2E and writes the local,
untracked `backend/.work/php_registry.json` only when all fourteen checks pass.
The receipt binds implementation/profile bytes, demo hashes, image IDs and
golden/report/evidence artifact hashes. Modified code/profiles/demo/artifacts,
missing proof or changed images disable dynamic PHP operation readiness.
GET/preflight only read metadata; they never create proof or run projects.
This local integrity record is not a cryptographic signature or external trust
authority. A fresh checkout requires its own explicit verification.

## Golden inputs, execution and comparison

The owned `tests/fixtures/php_shop` has four source modules, 17 named functions,
safe sample data and nine native named tests in `tests/proofport.php`.
`tests/fixtures/php_profiles/cases.json` supplies **22 inputs, not canned expected
values**. Results are recorded on the source interpreter and stored in golden.json.
The native tests use throwing checks rather than PHP assertions, so `-n` cannot
silently disable them.

The harness captures function calls, arguments, return values, stdout, warnings,
exceptions and runtime Errors. Typed JSON distinguishes null/bool/int, IEEE-754
float bits, binary strings (base64), and ordered arrays with typed keys. Error
class/message/code and output are compared. Unsupported objects/resources,
malformed/missing results, empty suites, timeouts or incomplete case coverage
cannot produce behavior_verified. No model receives expected answers.

The one explicit normalization allowance is a recorded difference in deprecation
notices (e.g. removal of each()). Other warnings, ordering, values, types, output
and errors remain strict. Results use three independent nullable flags:
`syntax_passed`, `tests_passed`, `behavior_verified`. Null means not run, never
passed. Function-input coverage is finite, not branch coverage or proof of all
behavior. Cases share one process per batch; global-state isolation, class/method
cases, generators, web requests, database/extension behavior and side effects
are not generally modeled. Inputs exclude ambiguous floats/numeric map keys;
results can represent floats exactly. Limits: 64 cases, 64 lint files, 128 tests,
2000 visible project entries / 16 MiB inventory, 1 MiB per lexed PHP file.

Local PHPUnit support requires a recognized local XML configuration plus existing
`vendor/autoload.php` and `vendor/phpunit/phpunit/phpunit`. It runs inside Docker
and consumes nonempty bounded JUnit results; skipped/error/failure results do
not pass. No dependency installation occurs. Real PHPUnit/Composer compatibility
is **not integration-verified** in this milestone; only native demo tests ran.
Large dependency trees may exceed the bounded lint/inventory limits.

## Migration and security results

Actual demo migration: PHP 7.4.33 → 8.3.36, 22/22 golden cases matched and 9/9
native tests passed on each interpreter. `src/legacy.php` replaces each() while
preserving its mixed-key array order and replaces curly string offsets. Other
modules pass through unchanged until an explicit security fixture is checked.
The unchanged legacy project fails target syntax compatibility as expected;
the accepted migrated copy passes separate syntax/tests/behavior compatibility.

The PHP scanner uses original bounded lexical rules, not taint analysis:

| Rule | CWE | Potential issue |
| --- | --- | --- |
| PHP-SQL | 89 | Query sink / SQL construction |
| PHP-XSS | 79 | Dynamic output requiring context review |
| PHP-CMD | 78 | Shell or command sink |
| PHP-DESERIALIZE | 502 | Unserialization |
| PHP-PATH | 22 | Dynamic filesystem access |
| PHP-SECRET | 798 | Possible embedded credential |
| PHP-HASH | 328 | Weak hash requiring usage review |
| PHP-UPLOAD | 434 | Upload handling |

Every finding has a stable contextual ID, CWE, severity/confidence, file/line,
scope, description/recommendation, status and `potential_risk_not_confirmed`.
Values and source snippets are withheld. Comments/literal text and tests/vendor
are excluded. Parser diagnostics produce partial coverage; a partial rescan
cannot authorize an automatic fix. Dynamic calls, aliases, autoloading, templates,
sanitizer correctness and data flow are not comprehensively analyzed.

The demo yields **10 potential warnings across all eight rules, 0 confirmed
exploits**. It includes a console-output XSS candidate and a constant-command
warning; these require context and are not automatically called vulnerabilities
or false positives. SQL uses a fake local connection, upload uses a non-upload,
commands/data are harmless, and the secret is an explicit fake placeholder.

Each fix is source-hash-bound and staged on a fresh copy. Syntax → existing
tests and golden comparison → rescan → conservative policy → decision. Both
test stages must run/pass; disappearance of a warning alone is insufficient.
An exact allowlist currently covers only the demo constant `printf` shell call
changed to literal argv `proc_open`. Arbitrary proposals need review even if
tests pass. Originals and the previously accepted copy are rehashed each time.

Real outcomes:

* Constant command hardening: accepted after all checks; `src/commands.php`
  changes, potential warnings reduce 10 → 9. This is verified hardening within
  the finite test scope, not proof of a previously exploitable vulnerability.
* md5 → sha256 proposal: behavior and existing test failures; `needs_review`,
  rejected and rolled back. Crypto/data format changes cannot be auto-accepted.
* Broken syntax proposal: `fix_reverted`; tests/golden not run and not fabricated.

Rollback keeps the earlier accepted copy and retains rejected candidates,
checks and diffs. Possible credential-bearing file diffs are withheld from
exports. All patches are `fixture`/`not_ai`, not model responses.

## Additive /api/v1 contract

No new endpoint is needed. Existing Python requests default to `language=python`
and keep their previous successful public parameters and operation matrix.
Legacy POST remains Python-only, including its prior error envelope/path policy.
PHP must be explicit: `language: "php"`. PHP public parameters additionally
include `language` and nullable `security_fix_profile_id`.

`GET /api/v1/capabilities` keeps root `operations` and `runtimes` Python-only;
read `languages.php` for PHP `configured`, `available`, `verified`, `runtimes`,
`source_versions`, `target_versions`, `supported_operations`, `operations`,
`readiness`, configured candidate versions and verification scope.
Only supported_operations is executable; operation policy descriptions are not
proof of readiness. PHP runtime verified flags require current image-bound E2E.
PHP audit can remain ready without Docker after a valid local proof because it
is static only. Never show it as execution-based interpreter certification.

`GET /api/v1/projects` includes `php_shop`, language inventory/readiness and
server-bound `available_profiles`: cases `php_shop_golden`, fixture
`php_shop_74_83`, security_fix `php_shop_security`. Root `cases_profiles` and
`fixture_profiles` remain; `security_fix_profiles` is additive. Resolve remains
safe inventory/registration, not operation approval; refresh catalog/capabilities
and preflight afterward. Server-bound demo profiles cannot be applied to a
different resolved project or selected by an arbitrary filename.

Supported operation policies after current proof:

* migration: 7.4 → 8.3, `offline_fixtures`, directory, full behavior verification,
  matching cases/fixture profiles; optional server-bound security fixture.
* compatibility: 7.4 → 8.3, `offline`, syntax/tests/behavior levels. Passing
  checks are project-specific; an operation being available does not mean the
  selected project is compatible. Tests need an existing local suite; behavior
  additionally needs a bound cases profile.
* audit: source label 7.4 or 8.3, `offline`, static only; no target/cases/level,
  migration settings or fixes. Source labels are operator input, not detection.

Example migration body for both preflight and POST runs:

```json
{
  "language": "php",
  "operation": "migration",
  "project_id": "php_shop",
  "source_version": "7.4",
  "target_version": "8.3",
  "execution_mode": "offline_fixtures",
  "fixture_profile_id": "php_shop_74_83",
  "cases_profile_id": "php_shop_golden",
  "security_fix_profile_id": "php_shop_security",
  "max_iterations": 1
}
```

```json
{"language":"php","operation":"audit","project_id":"php_shop","source_version":"7.4","execution_mode":"offline"}
```

Preflight HTTP 200 still requires `can_start: true`. `php_e2e_verification_required`,
`docker_unavailable`, `unsupported_php_version`, pair/profile/language/parameter
errors block launch. Creation repeats checks and returns HTTP 202 `{run_id}`;
existing busy gate/idempotency rules apply. Live and PHP simulation are rejected;
no automatic fallback. No browser Docker commands, mounts or manifest paths.

Poll GET `/api/v1/runs/{id}` for immutable parameters, lifecycle, finalized,
execution provenance, result.compatibility/security_audit/security_fix/target_tests
and the unchanged legacy state. Events/report exports continue on
`/api/runs/{id}/events?since=N` and `/api/runs/{id}/report?format=json|html`.
Wait for finalized; report receipt and evidence verification are separate checks.
Audit module green means audit finished, **not behavior verified or secure**.
Legacy numeric test metrics count PHP golden comparisons; the nine existing
tests are separately listed under result/report target_tests.

Reports preserve the existing envelope; verification adds language/mode, images,
source/accepted hashes, separate tri-state checks, recorded comparisons,
iterations, coverage, findings before/after, security attempts/decisions, model
calls zero, isolation and limitations. Full engine JSON/HTML and JSONL evidence
remain in the retained PHP artifact; HTTP exports live in its `api/` subdirectory.
Golden values and candidate source are local verification artifacts; treat
future real-project recordings as private application data.

## Commands and actual checks

```powershell
# Explicit E2E proof, not a startup side effect; already installed images only.
.venv/Scripts/python.exe -m backend.php verify-demo

# Static audit needs neither Docker nor a model.
.venv/Scripts/python.exe -m backend.php audit

# Start the unchanged dashboard/server. PHP UI language controls are P6.5.
.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8001
```

Fast backend tests, real PHP integration/lint, one Python migration regression
and unchanged frontend tests were run. Actual outputs:

```text
pytest tests -q -m "not docker" -p no:cacheprovider
372 passed, 47 deselected in 15.15s

PROOFPORT_DOCKER_TESTS=1 pytest tests/test_php_integration.py -q -p no:cacheprovider
4 passed in 46.27s

PROOFPORT_DOCKER_TESTS=1 pytest tests/test_php_integration.py tests/test_php_analyzer_integration.py -q -p no:cacheprovider
4 passed in 54.88s
(Earlier combined run: two initial E2E cases and both actual PHP lint cases.
The final four-case PHP E2E run above additionally covers positive compatibility
and sandbox restrictions. Six distinct PHP Docker tests passed overall.)

PROOFPORT_DOCKER_TESTS=1 pytest tests/test_control_integration.py -k migration -q -p no:cacheprovider
1 passed, 3 deselected in 15.02s

node --test frontend/tests/*.test.cjs
tests 40; pass 40; fail 0
```

Every pytest invocation used its own retained `backend/.tmp/` base directory;
none reused/deleted earlier artifacts. No unrelated Docker matrix or dependency
installation ran. Forty other Docker tests were not rerun in this milestone.
The Python regression preserves 90/90 golden cases and 10 existing tests on
both interpreters. The PHP-specific CLI lint bug found during testing (PHP 8.3
interpreting `-l -- path` as stdin lint) was corrected using validated absolute
`/src/...` file arguments; no original source changed.

## Remaining work

P6.4 broader policy/patch generators need more behavior/rollback fixtures,
application-specific contracts, data-flow/extension coverage and real PHPUnit
integration. Current allowlist is intentionally narrow. A future Meta translator
and PHP security proposal provider must bind findings/source hashes, validate
structured responses and re-use these checks; this milestone never invokes them.
AI migration/fix readiness requires separately authorized real Meta verification.

P6.5 is Claude Code frontend language selection, per-language capabilities,
project/profile filtering, tri-state checks, static coverage and offline fixture
labels. Do not reuse the root Python version matrix for PHP. There is no AI
Security Fix endpoint/button. Replay reports remain read-only saved evidence.
