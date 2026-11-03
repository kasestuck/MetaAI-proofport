# 05_python_unsafe_eval

## Goal

Detect unsafe eval; verify that a literal-only parser changes an arithmetic contract and remains needs_review.

## Owned project / required fixture

See [scenario.json](scenario.json) for all explicit inputs. Source: `judge_tests/05_python_unsafe_eval/project`.
The project is either the small owned `project/` here or a necessary reference to
an existing owned repository fixture. Do not copy this folder without the rest
of the repository when it references shared fixtures. Originals are read-only.
Authored candidate files are intentional offline test inputs, not saved Meta output.

## Required versions and dependencies

Host runner: Python 3.12 with `backend/requirements.txt` installed. Dynamic source
runtime: **3.12**; target/check runtime: **3.12**.
Language: **python**. Docker Desktop must use Linux containers.
Required existing local images: `python:3.12-slim`, `proofport-bandit:1.8.6`.
Project code uses only interpreter-provided facilities; no network packages,
external server, database credentials or API key are needed. No image is pulled.

## Run from repository root

```powershell
judge_tests\run.bat --scenario 05
# Equivalent with the installed environment:
.venv/Scripts/python.exe judge_tests/runner.py --scenario 05
```

Initial setup: `py -3.12 -m venv .venv`, then
`.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`.
Prepare only required images explicitly; see [suite setup](../README.md).
Never run this project's tests directly on Windows; the runner executes them in Docker.

## Expected result and pass/fail checks

NEEDS_REVIEW: B307 detected; baseline tests pass; literal-only candidate changes arithmetic behavior; rollback and manual policy are confirmed.

Every mandatory assertion must be true: actual checks completed, expected decision,
original byte hashes unchanged, and evidence intact. Unexpected findings, mismatches,
missing tests, scan errors or broken integrity are FAIL. Missing mandatory Docker/images
are SKIP and produce a nonzero suite exit, never PASS.
An expected NEEDS_REVIEW can satisfy the test's rejection assertions and return exit 0;
it means **no approval for that proposed fix**, not a successful remediation.

## Evidence and output

The console prints the unique ignored `backend/.work/judge-*/summary.json` path.
Its `05/` subfolder contains `result.json`, `report.html`, `evidence.log`,
SHA-256 receipt and retained verification/candidate artifacts. Model calls are zero.
Recheck a saved result with `runner.py --verify-summary <printed-summary-path>`.
No original Meta live evidence is modified or required for this offline scenario.

## UI versus CLI

UI: resolve judge_tests/05_python_unsafe_eval/project and run Python 3.12 audit. CLI only: the literal-parser proposal and review/rollback checks.
The server's capabilities, project catalog and preflight determine actual availability;
these instructions never override a blocked preflight or enable live generation.

## Known limitations

Only safe literals/arithmetic/string inputs are used. No system calls/import payloads or attacks are executed. literal_eval is not a general resource-safe replacement for unrestricted eval.
Local evidence hashes detect inconsistencies, not an administrator rewriting every
file/receipt. Passing finite tests is not universal equivalence or full security.
