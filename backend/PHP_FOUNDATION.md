# P6.1 — language adapters and PHP analyzer

Implemented on `integration/p4`, 2026-11-01. This milestone is a foundation,
not PHP migration, compatibility certification, security audit or remediation.
No Meta API requests, image pulls, dependency installs or frontend edits.

## Architecture and existing Python behavior

`backend/languages/` adds an internal LanguageAdapter protocol, LanguageRegistry,
AnalysisResult, tri-state Verification, SecurityResult and EvidenceSink.
Registry selection does not construct a model, pull images or execute a project.
Additional adapters can register the same analyze/compatibility/security methods.

PythonAdapter delegates to the existing analyzer, VersionRegistry, Bandit findings
and universal compatibility worker. It preserves existing RunSpec settings,
image pins, test/comparator logic and the Evidence interface. The existing Python
worker dispatch, sandbox, security fix engine and frozen RunSpec/public parameters
were not rewritten or extended. Python single-file operation preparation remains
the responsibility of the existing working-copy workflow.

PHPAdapter provides lexical analysis and opt-in Docker lint. Its compatibility
and security methods fail explicitly with not-implemented codes. They never feed
PHP into Python AST/Bandit or synthesize successful results. New PHP job dispatch,
PHP RunSpec fields, tests/golden execution, scanner and fix engine are deferred.

## PHP analyzer

The lexer recognizes PHP tags and skips HTML, comments, strings, backticks,
heredoc and nowdoc content. Structure extraction reports named classes,
interfaces/traits/enums, anonymous class markers, named functions/methods and
namespace declarations. It is not a PHP AST or full grammar implementation;
closures, arrow functions, generated declarations, string interpolation, traits,
inheritance and autoload/type resolution are not exhaustively modeled.

Include/require/once dependencies have bounded literal resolution. A literal
relative path or `__DIR__ . '/file.php'` may identify an inventoried local file.
Relative paths remain candidates because runtime include_path/cwd can differ.
Dynamic, unresolved, absolute, wrapper and outside-project includes are recorded
for review, never followed or evaluated. Dependency cycles are reported, not
silently declared safe or impossible to execute.

Limited review rules identify candidate removed built-in calls such as each and
create_function, curly string-offset syntax, and loose comparisons needing
behavior review. User-defined names and unknown types can cause false positives.
These are compatibility advisories, not confirmed security vulnerabilities.

Composer PHP constraints are reported as metadata, not solved. Composer scripts
are never executed. PHPUnit configuration presence is reported without claiming
that dependencies/configuration are compatible or that tests ran. Non-UTF-8,
oversized or lexically incomplete files produce diagnostics/manual-review entries.

Limits: shared 2000 visible files/16 MiB total, at most 1 MiB per lexed PHP file,
and at most 32 files per explicit lint. Secret/service exclusions and visible
link/junction/hard-link rejection reuse the filesystem policy. All visible
inventoried bytes are SHA-256 hashed before and after analysis. No source contents,
string literals or raw lint errors are exported as finding snippets.

## Versions, images and syntax

Configured candidates:

| Version | Official image tag | Role | Operation verified |
| --- | --- | --- | --- |
| PHP 7.4 | php:7.4.33-cli | Legacy source | No |
| PHP 8.3 | php:8.3.36-cli | Source/target candidate | No |

These fixed patch tags are operator configuration, not proof of local presence
or universal PHP support. PHP 8.4 is an extension point, not enabled support.
Runtime descriptions are frozen; a future version requires explicit configuration
and real checks rather than an automatically accepted version/image string.

Metadata reads inspect local Docker image IDs only, sharing the existing bounded
capabilities probe budget. Configured, available (including null/unknown), and
verified are independent. Even an installed PHP image remains verified=false;
P6.1 has no PHP operation receipts and no PHP operation becomes available.

Explicit lint first prepares a retained sanitized working copy, checks its hashes,
pins an inspected sha256 image ID and checks actual PHP_VERSION against the patch
tag using a trusted in-container snippet. It then invokes php -n -l on each file,
with prepend/append and CLI opcache disabled, inside the existing network-off,
read-only, non-root Docker sandbox with resource/output/time limits. It rechecks
source and copy hashes. Composer auth.json requires a separately sanitized input
and is rejected before mounting. No original code is run on the host or patched.

Syntax success is only syntax_passed. tests_passed and behavior_verified remain
null. Lint failure is distinct from unavailable/timed-out/wrong-version execution;
those cases yield no success verdict. Workspaces under backend/.work/php-lint-*
are retained and never deleted by this adapter.

References used to check PHP-specific assumptions:
[PHP CLI options](https://www.php.net/manual/en/features.commandline.options.php),
[PHP 8 migration changes](https://www.php.net/manual/en/migration80.incompatible.php),
[PHP 8.3.36 release](https://www.php.net/releases/8_3_36.php),
[official PHP Docker images](https://hub.docker.com/_/php).
No provider/analyzer code was copied from these references.

## Additive discovery contract

Existing capabilities operations/runtimes remain Python. Optional `languages`
is added to GET /api/v1/capabilities. Its PHP entry has configured candidates,
planned_pairs, lexical_analysis_available=true, supported_operations=[],
source_versions=[], target_versions=[], available_profiles with empty lists,
and readiness.can_start=false/reason=php_operations_not_implemented.
Configured source/target lists are explicitly named configured_*_versions.

Python language metadata derives from the existing operation matrix, verified
runtime/role flags and scanner availability. Profile availability comes from
GET /api/v1/projects, not an invented global empty Python profile list.

Project catalog/resolve results add language, languages, nullable source_version
and target_version, supported_operations and readiness. GET projects also adds
project-bound available_profiles (cases/fixture IDs) while retaining the original
root cases_profiles/fixture_profiles arrays and all prior fields.

Language inference is extension-based inventory, not a runtime-version verdict.
Missing inputs stay unknown; mixed PHP/Python inputs are marked mixed/review.
Pure PHP files/directories can be registered safely for inventory, with no
available run operations. Preflight returns can_start=false; creation and legacy
POST reject them before reserving a worker or executing anything.

For backward compatibility, mixed projects still retain the old Python-only
execution scope through existing endpoints. PHP assets are not translated,
executed, scanned or behavior-verified by those Python requests; whole mixed
projects are not advertised as supported in the new metadata. A regression test
checks this using explicitly labeled simulation, not a fabricated PHP run.

No language parameter is accepted on POST runs yet. Existing requests/defaults,
legacy state/events/report envelopes and immutable per-run settings are retained.
The unchanged frontend ignores additive metadata. P6.5 must use per-language
readiness rather than treating configured images/versions as executable support.

## Local usage

```powershell
# Static lexical inventory: no Docker, PHP process, network or model required.
.venv/Scripts/python.exe -m backend.languages tests/fixtures/php_analysis --source-version 7.4 --target-version 8.3

# Optional syntax-only check, only with an already installed local image.
.venv/Scripts/python.exe -m backend.languages tests/fixtures/php_analysis --source-version 7.4 --target-version 8.3 --lint-version 8.3
```

Output includes real source hashes and an evidence chain. The small authored
tests/fixtures/php_analysis input has two modules and deliberate obsolete syntax;
it is analyzer test data, not the runnable legacy demo or an AI migration fixture.

## Verification and limits of this session

Recorded fast checks and frontend regressions:

```text
pytest tests -q -m "not docker" -p no:cacheprovider
287 passed, 43 deselected

node --test frontend/tests/*.test.cjs
40 passed, 0 failed

PROOFPORT_DOCKER_TESTS=1 pytest tests/test_php_analyzer_integration.py -q -rs -p no:cacheprovider
2 skipped: Docker is unavailable; no PHP runtime has been verified.
```

The Docker Desktop Linux named pipe was absent during the metadata check. No
Docker service was started/stopped, and no image was pulled. Consequently no real
PHP syntax/compatibility support is claimed. Lint command/decision tests use
explicit doubles, not execution evidence. The opt-in tests are ready to check
valid/invalid syntax, actual image version, non-execution and unchanged originals
once Docker and the exact local images are available with user authorization.

Static CLI on the authored fixture produced two inventoried files/modules,
originals_unchanged=true and a valid evidence chain, with all three verification
statuses null. Its local report is retained under backend/.tmp/.

## Remaining milestones — plan only

1. **P6.2:** obtain permission for only the necessary official images; verify
   actual patch IDs and add image/analyzer-bound receipts. Add an owned legacy
   PHP demo, constrained JSON function harness, supported local PHPUnit runner
   and dependency/config validation. No Composer install or scripts from network.
   Record source results on 7.4, run target tests/cases on 8.3, compare typed
   values/exceptions/output, and distinguish syntax/tests/behavior. Add immutable
   language selection/dispatch without sharing environment state; enable only
   exercised operation/pair/profile combinations through preflight.
2. **P6.3:** implement PHP-specific limited security rules/analyzer for SQLi,
   XSS, command injection, unsafe deserialization, upload/path traversal, secrets
   and weak password hashing. Preserve CWE/severity/confidence/location/status,
   report coverage/false positives and never use Bandit for PHP.
3. **P6.4:** implement offline source-hash-bound proposals on copies, syntax,
   nonempty existing tests, golden comparison, rescan and conservative decisions.
   Reject/rollback failed or behavior/API/config changes, retain diffs/evidence,
   and test rollback/original integrity. No automatic acceptance from warning loss.
4. **P6.5:** Claude Code frontend language/operation/version/profile integration
   after the verified backend contract exists; tri-state results and honest
   provenance/coverage, no PHP migration success or AI fix claims from fixtures.

## Changed files

```text
backend/languages/__init__.py
backend/languages/__main__.py
backend/languages/base.py
backend/languages/registry.py
backend/languages/runtimes.py
backend/languages/python.py
backend/languages/php_lexer.py
backend/languages/php.py
backend/core/capabilities.py
backend/core/control.py
backend/core/projects.py
tests/test_languages.py
tests/test_php_analyzer.py
tests/test_php_analyzer_integration.py
tests/fixtures/php_analysis/bootstrap.php
tests/fixtures/php_analysis/lib/prices.php
tests/fixtures/php_analysis/composer.json
tests/fixtures/php_analysis/README.md
backend/API_CONTROL_PLANE.md
backend/ARCHITECTURE.md
backend/PHP_FOUNDATION.md
```
