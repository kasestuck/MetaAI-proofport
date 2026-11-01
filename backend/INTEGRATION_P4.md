# P4.3 integration verification — 2026-11-01

## Git provenance

The initial working tree was clean on `frontend/claude`. A new local branch
`integration/p4` was created from that branch and merged with `backend/codex`
using `git merge --no-ff`. No conflicts, history rewriting or remote writes.

Merge commit: `c42e8df410b0bb92fd43c999b4a1ae7431cd6237`.
Its parents, also the preserved source branch tips:

- Frontend: `5b5814f0009c68da94e7b3d46d917e2e90718342`.
- Backend: `e2817d03c8e0037dfd7a94fb161a0a763b483062`.

Immediately after merge, `frontend/` matched the frontend source branch exactly;
`backend/` and `tests/` matched the backend source branch exactly. All six requested
files/directories were present, including the control-plane documentation,
backend adapters, frontend control module and frontend tests.

P4.3 adds only this document and reproducible opt-in test harnesses:
`../tests/integration_probe.py` and `../frontend/tests/browser.integration.cjs`.
Production backend/frontend implementation and the public API contract required
no fixes. Samples and prior work artifacts are unchanged.

## Fast checks

```text
python -m pytest tests -q -m "not docker" -p no:cacheprovider
179 passed, 41 deselected in 6.78s

node --test frontend/tests/*.test.cjs
tests 40
pass 40
fail 0
```

All frontend JavaScript files passed `node --check`. The 41 deselected Docker
cases were deliberately not mass-rerun. The three operations below are the only
real project/Docker workloads executed for P4.3; HTTP/browser assertions exercised
them instead of redundantly running the old TestClient smoke matrix.

The first restricted-process pytest invocation could not progress through local
TestClient I/O. Only its specifically identified child process was stopped;
the unrestricted invocation above passed. Docker's named pipe likewise required
the normal desktop process context. Splunk and other services were untouched.

## Real HTTP + browser outcomes

Server: `http://127.0.0.1:8765`, real FastAPI application, installed local images,
installed headless Chrome through the bundled Playwright. No screenshots, video
or traces were created. No browser third-party requests were observed.

| Operation | Actual result | Run ID |
| --- | --- | --- |
| 2.7 → 3.12 fixture migration, legacy_shop | 90/90 golden comparisons; 10/10 original tests on 2.7 and 10/10 target tests on 3.12; done | `5603673a8ae54cc484d791722c1017c1` |
| Security audit, legacy_shop, source 2.7 | 8 potential warnings; partial coverage, 4 parse errors; no project execution or fixes; done | `6faa4cd492884db0a6d8ebf80b981268` |
| Compatibility, universal_py3, 3.12 → 3.13, behavior | 2/2 existing tests and 2/2 golden comparisons; behavior_verified; done | `b59e16479d3c4eb684c98eec62d7a947` |

Each run used Docker isolation, finalized successfully, produced HTML/JSON,
passed independent browser SHA-256 chain verification, reported unchanged source
hashes and zero model calls/tokens/cost. A separate byte-hash snapshot of both
source projects matched after every operation. These are offline fixture/check
results, not AI migration or AI remediation.

Existing image-bound receipts were valid for Python 2.7.18, 3.12.16 and 3.13.18.
The local Bandit 1.8.6 image was available. No images were downloaded, and no
additional runtime self-test matrix was needed. 3.8/3.10/3.14 were not enabled.

Actual requests covered all six `/api/v1` routes and legacy health/state/events/
JSON/HTML report access. Browser operations submitted v1 requests without editing
`.env`. Additional assertions confirmed:

- Project resolution and traversal rejection (403).
- Runtime selectors constrained by current verified capability pairs.
- Missing project-bound profiles unavailable for selection and Start blocked.
- A real incompatible-source preflight returned HTTP 200, can_start=false;
  its actual server message was visible and Start remained disabled.
- Creation returned HTTP 202; same key/payload returned the same running ID.
- Another key returned run_busy (409); busy preflight returned can_start=false.
- During finalizing, finalized=false, the UI still showed Finalizing, polling
  continued, and the report route returned 409. Report loading and browser chain
  verification were separately observed after backend completion.
- Cursor events used seq > since and matched the complete report event chain.
- No active Live Meta AI badge and no uncaught/render/unhandled JavaScript errors.
- All five dashboard tabs loaded real completed reports for each operation:
  15 additional browser checks, with zero additional pipeline runs.

The test-only server delays entry into the unchanged real finalizer by two
seconds so ordinary one-second frontend polling can reliably observe finalizing.
It does not replace Docker execution, test outcomes, evidence, reports, capability
receipts or the HTTP contract. The production entrypoint has no such delay.
The probe also raises immediately on model SDK construction/completion.

One harness issue was corrected before any project run: Playwright serializes
native Error objects without custom code/field properties. The assertion now
explicitly reads those fields in the page. It was not an API/dashboard defect.

## Retained artifacts

Real JSON/HTML reports, events, capabilities, preflight/error responses,
before-run source hashes and summaries are retained locally under:

`backend/.tmp/p43-real-2026-11-01T07-32-11-575Z/`

`summary.json` records all three operations; `browser-views.json` records the
15 report/tab checks. The initial unsuccessful harness attempt has its own
separate retained directory. Per-run workspaces and persisted evidence remain
under `backend/.work/`. Generated data is excluded locally and not committed.
In-memory IDs disappear when the test server stops; the saved reports remain
available for local read-only replay in the frontend.

After stopping only the owned probe process, the ordinary `backend.api.main:app`
entrypoint was started on the same port and checked in a fresh real browser.
Health, current capabilities, operation/version controls and successful migration
preflight passed, with zero JavaScript errors and no extra pipeline executions.
This server has no verification delay or monkeypatches and was left running for
manual inspection. `normal-entrypoint.json` records that additional check.

## Start the normal application

With the existing Python 3.12 virtualenv, run from the repository root:

```powershell
$env:LLM_MODE = 'mock'
.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. If that port already serves this verification
session's normal app, use it directly; do not stop unrelated listeners. The
standard launcher also supports `PROOFPORT_PORT=8765` with `start.bat`.
Select operation/project/versions/profiles in Run control, Check readiness, then
Start run. No per-operation `.env` editing is needed. Docker Desktop must remain
available, with the required installed images and valid receipts.

## Reproduce the opt-in real checks

These commands intentionally perform the three Docker operations again. Do not
run them as part of ordinary fast tests. Choose an unused allowed test port.

```powershell
# Terminal 1, repository root; only the verification server gets this delay/guard.
$env:LLM_MODE = 'mock'
$env:PROOFPORT_INTEGRATION_TESTS = '1'
.venv/Scripts/python.exe -m uvicorn integration_probe:create_probe --factory --app-dir tests --host 127.0.0.1 --port 8765

# Terminal 2; Playwright must already be installed (no automatic install/download).
$env:PROOFPORT_INTEGRATION_TESTS = '1'
$env:PROOFPORT_INTEGRATION_URL = 'http://127.0.0.1:8765'
# This workstation's bundled package directory; adapt for another installation.
$env:NODE_PATH = "$env:USERPROFILE/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
node frontend/tests/browser.integration.cjs
```

The harness uses installed Chrome at its standard Windows path; override
`PROOFPORT_CHROME_PATH` if needed. It creates a fresh retained artifact directory
per invocation. Its opt-in filename is excluded from the `*.test.cjs` fast glob.

## Limits

This verifies the three exercised local combinations and finite recorded inputs,
not universal Python support or equivalence. Bandit findings are potential risks;
Python 2 parse errors leave real coverage gaps. The migrated candidate also has
8 warnings, with no claimed fixes (eval, pickle/import advisories, weak MD5,
formatted SQL, shell execution and hard-coded secret).

Live Meta AI, AI Security Fix, uploads, dependency installation, durable server
history, remote authentication and multi-process scheduling remain outside this
integration. No API credit was used. No main merge, rebase or push was performed.
