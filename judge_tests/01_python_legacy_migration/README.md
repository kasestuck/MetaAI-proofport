# 01_python_legacy_migration

## Goal

Exercise the existing full Python 2.7 to 3.12 fixture migration pipeline, including analysis, recording, tests, scan and reports.

## Owned project / required fixture

See [scenario.json](scenario.json) for all explicit inputs. Source: `samples/legacy_shop`.
The project is either the small owned `project/` here or a necessary reference to
an existing owned repository fixture. Do not copy this folder without the rest
of the repository when it references shared fixtures. Originals are read-only.
Authored candidate files are intentional offline test inputs, not saved Meta output.

## Required versions and dependencies

Host runner: Python 3.12 with `backend/requirements.txt` installed. Dynamic source
runtime: **2.7**; target/check runtime: **3.12**.
Language: **python**. Docker Desktop must use Linux containers.
Required existing local images: `python:2.7`, `python:3.12-slim`, `proofport-bandit:1.8.6`.
Project code uses only interpreter-provided facilities; no network packages,
external server, database credentials or API key are needed. No image is pulled.

## Run from repository root

```powershell
judge_tests\run.bat --scenario 01
# Equivalent with the installed environment:
.venv/Scripts/python.exe judge_tests/runner.py --scenario 01
```

Initial setup: `py -3.12 -m venv .venv`, then
`.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`.
Prepare only required images explicitly; see [suite setup](../README.md).
Never run this project's tests directly on Windows; the runner executes them in Docker.

## Expected result and pass/fail checks

PASS: 90/90 golden comparisons; 10/10 original and 10/10 target tests; original hashes and pipeline evidence intact; zero model calls.

Every mandatory assertion must be true: actual checks completed, expected decision,
original byte hashes unchanged, and evidence intact. Unexpected findings, mismatches,
missing tests, scan errors or broken integrity are FAIL. Missing mandatory Docker/images
are SKIP and produce a nonzero suite exit, never PASS.
An expected NEEDS_REVIEW can satisfy the test's rejection assertions and return exit 0;
it means **no approval for that proposed fix**, not a successful remediation.

## Evidence and output

The console prints the unique ignored `backend/.work/judge-*/summary.json` path.
Its `01/` subfolder contains `result.json`, `report.html`, `evidence.log`,
SHA-256 receipt and retained verification/candidate artifacts. Model calls are zero.
Recheck a saved result with `runner.py --verify-summary <printed-summary-path>`.
No original Meta live evidence is modified or required for this offline scenario.

## UI versus CLI

UI: Python Migration → legacy_shop → 2.7 to 3.12 → existing legacy_shop fixture/cases profiles. Check readiness, then start. CLI here additionally asserts the exact verification outcomes.
The server's capabilities, project catalog and preflight determine actual availability;
these instructions never override a blocked preflight or enable live generation.

## Known limitations

Prewritten, source-bound repository patches are offline fixtures, not AI output. Golden inputs are finite. Original Python 2 Bandit coverage is partial; a scan is not a security certificate.
Local evidence hashes detect inconsistencies, not an administrator rewriting every
file/receipt. Passing finite tests is not universal equivalence or full security.
