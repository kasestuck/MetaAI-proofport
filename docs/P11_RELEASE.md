# P11: repository consolidation and judge verification

Local verification date: **3 November 2026**. The mandatory judge assertions
passed. Publication and submission still require the owner actions below.
No Meta request, credit use, image download, push or main update occurred.

## Branch audit and preservation

The starting checkout was clean on `integration/p4`. Every other local branch
was already an ancestor of that branch. No useful unique commit was missing:
therefore no new merge, repeated merge or empty consolidation commit was made.
`release/hackathon` was created from the audited integration HEAD.

| Original branch | HEAD before and after P11 | Unique commits outside starting integration |
| --- | --- | --- |
| integration/p4 | `b907f6dd41e44f606b6b04c00bbd07ed3ba35fd6` | Base |
| backend/codex | `e2817d03c8e0037dfd7a94fb161a0a763b483062` | 0 |
| frontend/claude | `5b5814f0009c68da94e7b3d46d917e2e90718342` | 0 |
| main | `b1a2f5b018a2c63f857029ec0224ce1e1b1ce4d1` | 0 |
| Front | `b1a2f5b018a2c63f857029ec0224ce1e1b1ce4d1` | 0 |
| Back | `b1a2f5b018a2c63f857029ec0224ce1e1b1ce4d1` | 0 |

Condensed graph (the omitted intermediate commits remain in history):

```text
* Documentation and release checks                    release/hackathon
* 4256b64 Add ten Docker-verified offline judge scenarios and runner
* d476e04 Audit retired credentials across all local Git objects
* b907f6d Prepare English hackathon release docs         integration/p4
* ... P5-P10, including retained Python/PHP live evidence ...
*   c42e8df Existing P4 integration merge
|\
| * e2817d0 Backend control plane                        backend/codex
* | 5b5814f Frontend control plane                       frontend/claude
* | ... frontend design commits ...
|/
* 2e330c7 Shared earlier work
* ... existing Python pipeline commits ...
* b1a2f5b Initial commit                                 main, Front, Back
```

The first graph node describes this document's commit; obtain its exact SHA with
`git rev-parse release/hackathon`. `git log --graph --decorate --oneline --all`
shows the complete graph. No original branch was deleted or moved. Frontend,
existing sample sources and existing fixture content have no diff against the
starting integration commit. PHP fixture checkout attributes now preserve LF
bytes on Windows; the fixture files themselves were not rewritten.

## Ten actual judge results

All scenarios use authored offline inputs, **not Meta responses**. Golden
observations were recorded from originals inside Docker during this run.
Each scenario has an English README and a bounded source/profile selection.
The full demo projects are referenced where appropriate instead of duplicated.

| ID and scenario directory | Result | Actual scope |
| --- | --- | --- |
| 01_python_legacy_migration | PASS | Python 2.7 → 3.12: 90/90 golden comparisons; 10/10 source and 10/10 target tests. |
| 02_python_math_edge_cases | PASS | Python 2.7 → 3.12: 14/14 cases; 3/3 tests on each runtime. Authored math fixture, separate from historical Meta mathutils. |
| 03_python_compatibility | PASS | Python 3.12 → 3.13: 5/5 cases; 3/3 tests on each runtime; unchanged source. |
| 04_python_sql_injection | NEEDS_REVIEW | B608 detection; 3 baseline cases and 2 baseline tests. Parameterized-query proposal changes returned API, fails checks and is rolled back. No database contacted. |
| 05_python_unsafe_eval | NEEDS_REVIEW | B307 detection; 4 baseline cases and 2 baseline tests. Literal-only replacement matches 3/4 cases and 1/2 tests; arithmetic behavior changes, so rollback/review. |
| 06_python_secrets_crypto | NEEDS_REVIEW | Fake-secret/MD5 detection; 3 baseline cases and 2 tests. Configuration and hash-format changes are rejected in separate checked attempts. |
| 07_php_legacy_migration | PASS | PHP 7.4.33 → 8.3.36: 22/22 cases; 9/9 source and 9/9 target tests. |
| 08_php_xss | NEEDS_REVIEW | Both PHP runtimes: escaping changes output; 2/3 cases and 0/1 test for the proposed patch. Rejected with source preserved. |
| 09_php_command_injection | PASS | Both PHP runtimes: one exact constant-command hardening; 1/1 case and 1/1 test on each. No claim of confirmed exploitable user-input injection. |
| 10_php_security_regression | NEEDS_REVIEW | 22 baseline cases, 9 source and 9 target tests; constant hardening accepted, changed crypto contract reviewed/rejected, invalid syntax reverted. |

Full run: **5 PASS, 5 NEEDS_REVIEW, 0 FAIL, 0 SKIP; exit 0**.
Every required scenario assertion passed, including the expected review/rollback
decisions. This is not a claim that five rejected patches fixed vulnerabilities.
Failed candidate stage checks remain visibly failed in their attempt reports.

Local artifacts, intentionally ignored and not included in a public clone:

```text
backend/.work/judge-98a4d73d/summary.json
SHA-256: 45795576ba8f7e195f83488489d257076fbefd873a651eb8f9f0789df79ff02f
```

Each numeric scenario directory contains `result.json`, `report.html`,
`evidence.log`, `receipt.json` and retained engine artifacts. Source/input hashes,
actual runtime versions/image IDs, comparisons, tests, diffs and decisions are
recorded. Summary equality, receipt hashes and ordered evidence chains passed
the separate saved-summary verifier. Hashes prove local consistency, not an
external signature against rewriting every artifact.

## Reproduction and regression checks

See [judge instructions](../judge_tests/README.md) for requirements, images,
Windows setup, commands and UI/CLI boundaries. The runner never downloads images
or installs project dependencies. Missing mandatory Docker/images means SKIP
and nonzero exit. Project/model code has no Windows execution fallback.
Tests run sequentially with the existing restricted, non-root, no-network Docker
runner, read-only input mounts and bounded CPU/memory/process/time limits.

Actual output from the final fast backend run:

```text
554 passed, 58 deselected in 27.72s
```

The fast selection is `pytest -m "not docker"`; Docker tests were deliberately
deselected, not claimed as passed. Frontend Node tests: **73 passed, 0 failed**.
No frontend source changes were necessary.

Selected real Docker regression tests:

```text
3 passed, 3 deselected in 22.20s
```

These selected `tests/test_release_docker.py` and
`tests/test_control_integration.py` cases rechecked both genuine saved model
candidates and v1 audit/preflight/run polling plus legacy events/HTML/JSON reports.
Fast tests also cover idempotency, blocked preflight, finalization, capabilities,
Python/PHP control selection, replay and corrupted evidence handling. This is not
a new exhaustive browser or stress test.

Additional checks:

- `run.bat --scenario 02`: PASS, exit 0; independent retained summary under
  `backend/.work/judge-0704ca43/`.
- A fresh `git archive` of suite commit `4256b64`, extracted under ignored
  `backend/.tmp/p11-src-13b5167e/`, ran scenarios 01 and 07: both PASS, exit 0.
  This checks canonical Git checkout bytes and relative fixture paths. It reused
  the workstation's installed dependencies/images; it is not a clean-machine
  installation claim. No private `.env`, `.venv` or original runtime data was in
  that archive.
- Genuine historical Python candidate: **31/31 + 3/3** reverified in Docker.
- Genuine historical PHP candidate: **22/22 + 9/9** reverified in Docker.
- Saved real-run demo pack passed `backend.release verify-demo`. Original
  reports/provenance/receipts remain unchanged. Replay is not a fresh live run.
- Dependency consistency: `pip check` reported **No broken requirements found**.
  The existing 29 pinned requirements, MIT project license, sample license and
  third-party notices are preserved. This is not a comprehensive CVE/license audit
  of Docker transitive dependencies.

## Credential and generated-file audit

The strengthened release auditor checks current tracked bytes and **all local Git
objects, including unreachable blobs, commits, tags and trees**. It compares
available local credential copies in raw/JSON/base64 forms, common credential
prefixes and suspicious long `MODEL_API_KEY` assignments. It emits counts only.
Unit tests verify detection in unreachable objects and prevent key disclosure.

The pre-documentation-commit snapshot scanned **765 blobs / 1,202 objects**:
zero known/common credential matches, zero suspicious long key assignments,
zero tracked private env files and zero tracked generated files. Object counts
increase with commits; rerun the audit for the exact final count:

```powershell
.venv/Scripts/python.exe -m backend.release audit
```

**Coverage limitation:** only the available current local credential copies were
available for exact matching. No retired-key list was supplied. Unknown previously
disclosed/revoked values cannot be exact-matched, and heuristic checks are not
exhaustive secret discovery. This audit cannot certify that every historical
credential is absent. The owner must confirm revocation of previously disclosed
keys before publication. Never paste keys into chat, command arguments or reports.

If the owner retains old values, they may enter them privately in an ignored,
untracked file under `backend/.tmp/` with named `MODEL_API_KEY_RETIRED_1` entries,
then use `backend.release audit --retired-keys-file backend/.tmp/retired-keys.env`.
Missing/empty/non-private files are rejected. If any hit is found, withhold
publication and arrange separately authorized remediation; this task does not
rewrite history or rotate credentials.

Shared ignore rules cover `.work`, `.tmp`, virtual environments and caches.
Generated reports, extracted archives and the demo pack remain on disk but are
not tracked. Newly tracked judge projects/cases/candidates are intentionally
authored inputs, not output reports. No secrets, new dependencies or confidential
runtime artifacts are intentionally included in these commits.

## Local commits and remaining publication gates

- `d476e04`: credential audit across all local Git objects and regression tests.
- `4256b64`: ten judge scenarios, Docker runner, evidence verification, checkout
  attributes, scoped rules and runner regressions.
- Following documentation commit: root README and this report. Use
  `git log integration/p4..release/hackathon --oneline` for its actual SHA.

The checked local release branch is suitable for further owner review. Public
GitHub/submission readiness remains gated by old-key revocation confirmation,
review of any evidence pack chosen for sharing, repository access/branch settings,
the demo video, public name/profile TODOs and organizer/submission requirements in
the [existing checklist](SUBMISSION_CHECKLIST.md). No claim of universal Python/
PHP compatibility, complete vulnerability removal or guaranteed sandbox isolation
against all hostile code is made. Lexical PHP rules and finite golden coverage
retain their documented limits.

Safe publication sequence, **only after separate owner authorization**:

1. Confirm prior key revocation privately and resolve any credential audit hit.
2. Run the release audit, inspect `git status`, and inspect
   `git diff integration/p4..release/hackathon`. Confirm no private/generated
   material is staged; retain all original branches and artifacts.
3. Reproduce judge checks with required local images. A mandatory SKIP/FAIL is a
   blocker. Review the five NEEDS_REVIEW decisions rather than changing labels.
4. Review any intended evidence pack separately; ordinary source publication
   does not include ignored historical proof files. Do not bulk-add `.work`.
5. If the owner then authorizes publication, push only `release/hackathon` using
   a normal non-force push. Do not update/merge main or rewrite existing refs.
   Verify public visibility and the intended branch/README while signed out.
6. Complete the remaining video/team/portal items. No push or submission was
   performed during P11.
