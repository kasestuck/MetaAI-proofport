# 10_php_security_regression

## Goal

Exercise successful PHP hardening, rejected crypto-format change and syntax rollback through the existing full fixture pipeline.

## Owned project / required fixture

See [scenario.json](scenario.json) for all explicit inputs. Source: `tests/fixtures/php_shop`.
The project is either the small owned `project/` here or a necessary reference to
an existing owned repository fixture. Do not copy this folder without the rest
of the repository when it references shared fixtures. Originals are read-only.
Authored candidate files are intentional offline test inputs, not saved Meta output.

## Required versions and dependencies

Host runner: Python 3.12 with `backend/requirements.txt` installed. Dynamic source
runtime: **7.4**; target/check runtime: **8.3**.
Language: **php**. Docker Desktop must use Linux containers.
Required existing local images: `php:7.4.33-cli`, `php:8.3.36-cli`.
Project code uses only interpreter-provided facilities; no network packages,
external server, database credentials or API key are needed. No image is pulled.

## Run from repository root

```powershell
judge_tests\run.bat --scenario 10
# Equivalent with the installed environment:
.venv/Scripts/python.exe judge_tests/runner.py --scenario 10
```

Initial setup: `py -3.12 -m venv .venv`, then
`.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`.
Prepare only required images explicitly; see [suite setup](../README.md).
Never run this project's tests directly on Windows; the runner executes them in Docker.

## Expected result and pass/fail checks

NEEDS_REVIEW: 22 cases and 9 tests; attempts are fixed / needs_review / fix_reverted. Only the verified constant-command patch is retained on a copy; originals stay unchanged.

Every mandatory assertion must be true: actual checks completed, expected decision,
original byte hashes unchanged, and evidence intact. Unexpected findings, mismatches,
missing tests, scan errors or broken integrity are FAIL. Missing mandatory Docker/images
are SKIP and produce a nonzero suite exit, never PASS.
An expected NEEDS_REVIEW can satisfy the test's rejection assertions and return exit 0;
it means **no approval for that proposed fix**, not a successful remediation.

## Evidence and output

The console prints the unique ignored `backend/.work/judge-*/summary.json` path.
Its `10/` subfolder contains `result.json`, `report.html`, `evidence.log`,
SHA-256 receipt and retained verification/candidate artifacts. Model calls are zero.
Recheck a saved result with `runner.py --verify-summary <printed-summary-path>`.
No original Meta live evidence is modified or required for this offline scenario.

## UI versus CLI

UI: PHP Migration → php_shop with the existing cases/migration profiles and optional php_shop_security profile. The CLI asserts all three expected decisions and rollback. No Live AI or Apply button is added.
The server's capabilities, project catalog and preflight determine actual availability;
these instructions never override a blocked preflight or enable live generation.

## Known limitations

Fixture proposals are not Meta answers. Existing tests are finite. The crypto proposal is intentionally not an accepted password-hashing recommendation; warnings remain after the one narrow hardening.
Local evidence hashes detect inconsistencies, not an administrator rewriting every
file/receipt. Passing finite tests is not universal equivalence or full security.
