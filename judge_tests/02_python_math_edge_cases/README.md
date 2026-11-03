# 02_python_math_edge_cases

## Goal

Exercise integer versus float division, negative integer floor, ties-away-from-zero examples, long integers and factorial errors on a small owned module.

## Owned project / required fixture

See [scenario.json](scenario.json) for all explicit inputs. Source: `judge_tests/02_python_math_edge_cases/project`.
The project is either the small owned `project/` here or a necessary reference to
an existing owned repository fixture. Do not copy this folder without the rest
of the repository when it references shared fixtures. Originals are read-only.
Authored candidate files are intentional offline test inputs, not saved Meta output.

## Required versions and dependencies

Host runner: Python 3.12 with `backend/requirements.txt` installed. Dynamic source
runtime: **2.7**; target/check runtime: **3.12**.
Language: **python**. Docker Desktop must use Linux containers.
Required existing local images: `python:2.7`, `python:3.12-slim`.
Project code uses only interpreter-provided facilities; no network packages,
external server, database credentials or API key are needed. No image is pulled.

## Run from repository root

```powershell
judge_tests\run.bat --scenario 02
# Equivalent with the installed environment:
.venv/Scripts/python.exe judge_tests/runner.py --scenario 02
```

Initial setup: `py -3.12 -m venv .venv`, then
`.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`.
Prepare only required images explicitly; see [suite setup](../README.md).
Never run this project's tests directly on Windows; the runner executes them in Docker.

## Expected result and pass/fail checks

PASS: 14/14 recorded cases and 3/3 existing tests on each runtime; integer/float types and errors are compared, not guessed.

Every mandatory assertion must be true: actual checks completed, expected decision,
original byte hashes unchanged, and evidence intact. Unexpected findings, mismatches,
missing tests, scan errors or broken integrity are FAIL. Missing mandatory Docker/images
are SKIP and produce a nonzero suite exit, never PASS.
An expected NEEDS_REVIEW can satisfy the test's rejection assertions and return exit 0;
it means **no approval for that proposed fix**, not a successful remediation.

## Evidence and output

The console prints the unique ignored `backend/.work/judge-*/summary.json` path.
Its `02/` subfolder contains `result.json`, `report.html`, `evidence.log`,
SHA-256 receipt and retained verification/candidate artifacts. Model calls are zero.
Recheck a saved result with `runner.py --verify-summary <printed-summary-path>`.
No original Meta live evidence is modified or required for this offline scenario.

## UI versus CLI

CLI: the custom migration candidate/cases are judge-only. The UI has no matching server-bound migration profile for this small project, so do not substitute the legacy_shop profile. You may resolve the project for supported static operations, subject to preflight.
The server's capabilities, project catalog and preflight determine actual availability;
these instructions never override a blocked preflight or enable live generation.

## Known limitations

The authored rounding candidate is tested only on these bounded examples, not every binary float or all Python 2 behavior. This 14-case offline module is not the separate genuine 31-case Meta mathutils result.
Local evidence hashes detect inconsistencies, not an administrator rewriting every
file/receipt. Passing finite tests is not universal equivalence or full security.
