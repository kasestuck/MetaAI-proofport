# 07_php_legacy_migration

## Goal

Run the existing PHP 7.4 to 8.3 offline migration fixture through real source/target syntax, golden recording, native tests and reports.

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
judge_tests\run.bat --scenario 07
# Equivalent with the installed environment:
.venv/Scripts/python.exe judge_tests/runner.py --scenario 07
```

Initial setup: `py -3.12 -m venv .venv`, then
`.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`.
Prepare only required images explicitly; see [suite setup](../README.md).
Never run this project's tests directly on Windows; the runner executes them in Docker.

## Expected result and pass/fail checks

PASS: 22/22 golden cases and 9/9 native tests on source/target. The recorded profile permits deprecation-notice differences only.

Every mandatory assertion must be true: actual checks completed, expected decision,
original byte hashes unchanged, and evidence intact. Unexpected findings, mismatches,
missing tests, scan errors or broken integrity are FAIL. Missing mandatory Docker/images
are SKIP and produce a nonzero suite exit, never PASS.
An expected NEEDS_REVIEW can satisfy the test's rejection assertions and return exit 0;
it means **no approval for that proposed fix**, not a successful remediation.

## Evidence and output

The console prints the unique ignored `backend/.work/judge-*/summary.json` path.
Its `07/` subfolder contains `result.json`, `report.html`, `evidence.log`,
SHA-256 receipt and retained verification/candidate artifacts. Model calls are zero.
Recheck a saved result with `runner.py --verify-summary <printed-summary-path>`.
No original Meta live evidence is modified or required for this offline scenario.

## UI versus CLI

UI: PHP Migration → php_shop → 7.4 to 8.3 → php_shop_74_83 and php_shop_golden profiles, after explicit local PHP proof. CLI verifies the same finite migration without requiring browser readiness receipts.
The server's capabilities, project catalog and preflight determine actual availability;
these instructions never override a blocked preflight or enable live generation.

## Known limitations

One recorded PHP demo, not arbitrary Composer/framework apps. No network dependency installation or real Meta generation. Removed each()/curly-offset syntax is exercised via authored fixtures.
Local evidence hashes detect inconsistencies, not an administrator rewriting every
file/receipt. Passing finite tests is not universal equivalence or full security.
