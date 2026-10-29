# P3: offline Python analysis, audit and compatibility

No Meta requests, automatic migration or security fixes occur in these modes.
They reuse the hardened Docker runner: no network, non-root, read-only source,
read-only container root, bounded temporary storage, CPU/memory/PID/time/output
limits. Docker shares a kernel and is not a VM or a complete hostile-code
security boundary. Original files are hashed and copied; execution uses copies.

## Configured, available, verified

`core/versions.py` configures 2.7 as a legacy source, and 3.8, 3.10, 3.12, 3.13,
3.14 as potential sources/targets. This list is not a support claim.

- **configured**: descriptor exists in the allowlist.
- **available**: Linux Docker and the local image exist; no container or pull
  occurs when inspecting the registry.
- **verified**: the exact local image ID passed the shipped static analyzer,
  syntax checks, two unittest tests and two deterministic behavior harness
  checks. Receipt hashes bind the image and verifier source revision. Editing
  verifier code or retagging an image invalidates the receipt. Local receipts
  are reproducibility records, not signed external certification.

Selection requires all three. Verification is explicit and never downloads an
image. These self-tests do not prove arbitrary project compatibility, establish
a migration pair, or establish security. Project checks produce separate
evidence. Only the existing Python 2.7 -> 3.12 migration loop is implemented.
Other pairs use analysis/check modes; these modes do not rewrite code.

Run from the repository root with the Python 3.12 virtual environment:

```powershell
./.venv/Scripts/python.exe -m backend.universal registry
./.venv/Scripts/python.exe -m backend.universal registry --verify 3.12
./.venv/Scripts/python.exe -m backend.universal registry --verify 3.13
./.venv/Scripts/python.exe -m backend.universal detect path/to/project
./.venv/Scripts/python.exe -m backend.universal analyze path/to/project --source-version 3.12
./.venv/Scripts/python.exe -m backend.universal audit path/to/module.py --source-version 3.12
./.venv/Scripts/python.exe -m backend.universal check tests/fixtures/universal_py3 --source-version 3.12 --target-version 3.13 --cases tests/fixtures/universal_py3/cases.json
```

`--verify-runtime` on analyze/audit/check explicitly performs missing runtime
self-tests for the required locally installed images. It never pulls. Missing
images, unsupported versions, unverified images and mismatching project
metadata fail explicitly. Installing every configured image is unnecessary.
The CLI returns JSON, an artifact directory, and nonzero exit on failure.

## Detection and analysis

Detection is static: token/AST syntax evidence, pyproject.toml requires-python,
setup.cfg, literal setup.py metadata, dependency declarations and an optional
user declaration. setup.py is never executed. `.python-version` is a hint.
Conditional dependency markers are not treated as global Python requirements.
No package index is contacted and transitive requirements are not resolved.
Minor series are candidates if some patches can meet the metadata constraints;
the selected source's actual patch version is checked during a workflow. Target
requirements are checked before project execution; excluded targets require
metadata/dependency review even when their syntax check succeeds.

Common syntax returns unknown; newer syntax returns a possible range, never an
exact compatibility verdict. Host Python 3.12 cannot parse every new grammar.
PEP 696 type-parameter defaults provide a specific Python >=3.13 hint; more
unrecognized grammar stays uncertain. Python classifiers and complex dynamic
metadata are not exhaustive detection inputs. Explicit user versions are
validated against known evidence, then actual Docker grammar checks apply.

The Python 2.7 analyzer is preserved. The Python 3 analyzer runs in the chosen
interpreter, without importing project modules. It inventories top-level
functions/async functions, classes/methods, signatures and imports; resolves
relative internal imports; produces a dependency graph, ordering, cycles or
blocked modules, obsolete-construct advisories and a staged migration plan.
Dynamic imports, receiver types and dependency behavior need manual review.
Planning is not translation. Single .py files and directories are supported.

## Audit only

Audit parses using a verified source interpreter and runs Bandit 1.8.6 in its
separate Python 3.12 scanner image (`proofport-bandit:1.8.6`). Bandit reports
potential issues, CWE/severity/confidence, recommendations and open/review
status. No target module is imported, no tests or fixes run, no API key is
required. Scanner parse errors are reported as partial coverage, especially
for Python 2 and new Python 3.13+ grammar. A completed audit or zero warnings
does not mean the project is secure or compatible. Source snippets and literal
secrets are removed from scanner exports by the existing adapter.

## Compatibility evidence

Reports distinguish independent checks, including null (not run):

- `syntax_compatible`: all copied Python files compile in the selected target.
- `tests_passed`: a nonempty `tests/` unittest suite actually ran and every test
  passed. Missing dependencies fail tests; no dependency installation occurs.
- `behavior_verified`: supplied inputs were actually recorded on a declared or
  unambiguous source and compared on the target. Every analyzed application
  module needs at least one positive direct operation, parser coverage must be
  complete, and every case must match. This is limited finite evidence, not
  exhaustive function/path coverage or universal equivalence.
- `not_verified`: no sufficient compatibility evidence has completed.

The `level` identifies the strongest completed check; individual failures and
run status must also be read. Existing-test failure or behavior mismatch fails
the run. Matching partial golden coverage is exported but does not grant full
project behavior status. Syntax-only/test-only modules remain pending because
the unchanged API has no partial-verification module state. An audit/analyze
run may finish successfully with compatibility `not_verified`.

Artifacts: `backend/.work/<id>/copy/`, original SHA-256 map, optional golden
captures, chained evidence.log, HTML and JSON reports. Generated data is ignored
and must not be committed. Evidence is hash-chained locally, not externally
anchored or a cryptographic proof against an administrator rewriting it.

## Existing HTTP contract

No endpoint, request body or RunState field was added. To select the backend
mode, restart with server environment settings (not frontend request fields):

```powershell
$env:PROOFPORT_PIPELINE = 'audit' # analyze | audit | compatibility
$env:PROOFPORT_SOURCE_VERSION = '3.12'
$env:PROOFPORT_TARGET_VERSION = '3.13' # compatibility only
$env:PROOFPORT_VERIFY_RUNTIME = '1' # explicit optional self-tests; no pulls
$env:LLM_MODE = 'mock'
./.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Use the existing POST /api/runs source_path, poll status, then export the
existing report endpoints. Rich detection/registry/analysis/audit/compatibility
details live in reports and evidence, outside the frozen state schema.
PROOFPORT_CASES_FILE optionally selects inputs for compatibility mode. Clear
PROOFPORT_SECURITY_FIXTURES when switching from security-fix fixture mode.
The default verify/fixtures migration paths continue using 2.7 -> 3.12; they
reject source/target overrides for other pairs rather than silently ignoring
them. P3 paths do not construct LLMClient even if live credentials exist.

## Tests

```powershell
$env:PROOFPORT_DOCKER_TESTS = '1'
./.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider
```

Enabled integrations require existing local python:2.7, python:3.12-slim,
python:3.13-slim and the previously built Bandit image. Missing prerequisites
fail; without the flag Docker tests explicitly skip. Offline fixtures are
original project inputs, not AI migrations or canned passing execution results.

Grammar reference: [Python 3.13: PEP 696](https://docs.python.org/3.13/whatsnew/3.13.html#pep-696-type-defaults-for-type-parameters).
Dependency marker semantics: [PyPA dependency specifiers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/).

## Observed local verification: 2026-10-29

| Configured version | Actual local interpreter | Available | Runtime verified |
| --- | --- | --- | --- |
| 2.7 | 2.7.18 | yes | yes, source only |
| 3.8 | not installed | no | no |
| 3.10 | not installed | no | no |
| 3.12 | 3.12.16 | yes | yes |
| 3.13 | 3.13.18 | yes | yes |
| 3.14 | not installed | no | no |

Only python:3.13-slim was downloaded for this milestone. The prior 2.7, 3.12
and Bandit images were reused. Runtime self-tests execute the shipped analyzer,
compile step, two unittest tests and two golden-harness operations for each
verified image. Receipts contain complete immutable image IDs and hashes of
the analyzer, harness, registry, runner and trusted fixture sources.

The CLI check of universal_py3 from 3.12 to 3.13 actually passes two existing
tests and compares two recorded input cases. It writes HTML/JSON, original
SHA-256 maps, golden captures and chained evidence with model_calls=0.
The new audit-only CLI on legacy_shop records eight Bandit warnings and four
parser errors (partial coverage); target code is not imported or executed,
source hashes remain unchanged, and no fixes are claimed. New Python 3.13
grammar is parsed with its real interpreter; the Python 3.12 scanner's inability
to parse that grammar is reported rather than hidden.

Final full-suite output with PROOFPORT_DOCKER_TESTS=1:

```text
154 passed in 440.98s (0:07:20)
```

This includes 117 unit/API tests and 37 real Docker integration tests, with
no skips or failures. P3 adds 43 tests. Regression checks preserve the old
legacy_shop fixture migration: 90/90 golden comparisons and 10/10 unchanged
existing tests pass in Python 3.12, with the original Python 2.7 baseline also
executed in Docker. No Meta generation is implied by fixture verification.
All 15 original legacy_shop files retain their recorded SHA-256 values.

The first resumed test attempt found Docker Desktop stopped (117 passed,
two failures and 35 setup errors). After starting the installed Docker Desktop
and confirming the existing local images, the final full run above passed.
Generated pytest logs/XML and run artifacts remain ignored under backend/.
