# 06_python_secrets_crypto

## Goal

Detect an explicitly fake credential literal and MD5; independently reject configuration and digest-format changes rather than silently accepting them.

## Owned project / required fixture

See [scenario.json](scenario.json) for all explicit inputs. Source: `judge_tests/06_python_secrets_crypto/project`.
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
judge_tests\run.bat --scenario 06
# Equivalent with the installed environment:
.venv/Scripts/python.exe judge_tests/runner.py --scenario 06
```

Initial setup: `py -3.12 -m venv .venv`, then
`.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`.
Prepare only required images explicitly; see [suite setup](../README.md).
Never run this project's tests directly on Windows; the runner executes them in Docker.

## Expected result and pass/fail checks

NEEDS_REVIEW: B105 and B324 detected; both proposed changes are checked separately and rejected; no credential or crypto migration is automatically accepted.

Every mandatory assertion must be true: actual checks completed, expected decision,
original byte hashes unchanged, and evidence intact. Unexpected findings, mismatches,
missing tests, scan errors or broken integrity are FAIL. Missing mandatory Docker/images
are SKIP and produce a nonzero suite exit, never PASS.
An expected NEEDS_REVIEW can satisfy the test's rejection assertions and return exit 0;
it means **no approval for that proposed fix**, not a successful remediation.

## Evidence and output

The console prints the unique ignored `backend/.work/judge-*/summary.json` path.
Its `06/` subfolder contains `result.json`, `report.html`, `evidence.log`,
SHA-256 receipt and retained verification/candidate artifacts. Model calls are zero.
Recheck a saved result with `runner.py --verify-summary <printed-summary-path>`.
No original Meta live evidence is modified or required for this offline scenario.

## UI versus CLI

UI: resolve judge_tests/06_python_secrets_crypto/project and audit on Python 3.12. CLI only: the two negative patch verifications. Never supply real secrets to this fixture.
The server's capabilities, project catalog and preflight determine actual availability;
these instructions never override a blocked preflight or enable live generation.

## Known limitations

DEMO_NOT_A_REAL_CREDENTIAL is controlled test data, not an actual password/token. SHA-256 is a negative format-change example, not a recommended password KDF. No real account or secret service is contacted.
Local evidence hashes detect inconsistencies, not an administrator rewriting every
file/receipt. Passing finite tests is not universal equivalence or full security.
