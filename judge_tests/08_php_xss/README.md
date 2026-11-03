# 08_php_xss

## Goal

Detect dynamic HTML output, then verify in PHP 7.4 and 8.3 that escaping changes the recorded output and requires review.

## Owned project / required fixture

See [scenario.json](scenario.json) for all explicit inputs. Source: `judge_tests/08_php_xss/project`.
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
judge_tests\run.bat --scenario 08
# Equivalent with the installed environment:
.venv/Scripts/python.exe judge_tests/runner.py --scenario 08
```

Initial setup: `py -3.12 -m venv .venv`, then
`.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`.
Prepare only required images explicitly; see [suite setup](../README.md).
Never run this project's tests directly on Windows; the runner executes them in Docker.

## Expected result and pass/fail checks

NEEDS_REVIEW: PHP-XSS detected; 3 source cases and one existing test; both runtime checks run; escaping changes output, so no patch is promoted.

Every mandatory assertion must be true: actual checks completed, expected decision,
original byte hashes unchanged, and evidence intact. Unexpected findings, mismatches,
missing tests, scan errors or broken integrity are FAIL. Missing mandatory Docker/images
are SKIP and produce a nonzero suite exit, never PASS.
An expected NEEDS_REVIEW can satisfy the test's rejection assertions and return exit 0;
it means **no approval for that proposed fix**, not a successful remediation.

## Evidence and output

The console prints the unique ignored `backend/.work/judge-*/summary.json` path.
Its `08/` subfolder contains `result.json`, `report.html`, `evidence.log`,
SHA-256 receipt and retained verification/candidate artifacts. Model calls are zero.
Recheck a saved result with `runner.py --verify-summary <printed-summary-path>`.
No original Meta live evidence is modified or required for this offline scenario.

## UI versus CLI

UI: resolve judge_tests/08_php_xss/project and perform a supported PHP static audit. CLI only: context-changing escaping proposal checked in both runtimes; no standalone fix API exists.
The server's capabilities, project catalog and preflight determine actual availability;
these instructions never override a blocked preflight or enable live generation.

## Known limitations

Harmless markup is input data, not JavaScript or an external attack. Correct escaping depends on output context; lexical detection is not full taint analysis. Changed output needs review.
Local evidence hashes detect inconsistencies, not an administrator rewriting every
file/receipt. Passing finite tests is not universal equivalence or full security.
