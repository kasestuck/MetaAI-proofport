# Architecture audit and staged implementation plan

Audit date: 2026-10-27. Branch: `backend/codex`. Baseline: `8050c94`.
Scope: `backend/`, `tests/`, `start.bat`. No frontend or API contract changes.

## Decision for this iteration

Full P0 is blocked and is not implemented or claimed as complete. The local
Python 3.12.14 environment works, but Docker CLI, `.env` model configuration,
and `samples/legacy_shop` are absent. Therefore there are no verified runtime
images, live Meta call, or real demo run. Installing Docker or obtaining an API
key is not replaced by mocks. No host execution fallback will be introduced.

`docs/BRIEF.md` is still missing. The full project specification supplied in
the chat was reviewed, including its authoritative section 8 contract. The new
user request supersedes its earlier host subprocess fallback: untrusted code
must run only in Docker. The PDF is reference material, not independent
authorization to expand folder ownership or implement later milestones.

This iteration provides a read-only readiness command, an explicit simulation
gate, honest static-inventory failures, and regression tests. It does not
implement P1-P4 or present a command-construction mock as a real sandbox.

## What was already real at the baseline

| Component | Files | Verified capability and limit |
| --- | --- | --- |
| API | `api/main.py`, `core/models.py` | Five contract endpoints, request validation, busy handling, static frontend mount; no real pipeline integration |
| Source inspection | `core/runs.py` | Directory inventory and SHA-256 of actual non-hidden files; no Python parser, version detection, import graph, or single-file input |
| Evidence | `core/evidence.py` | In-memory hash chain, sequence cursors, tamper test; no durable append-only log or external trust anchor |
| Exports | `core/report.py` | Downloadable, escaped HTML and JSON containing state and events; baseline exports always describe simulation |
| LLM client | `llm/client.py` | OpenAI SDK adapter, `.env`, live request method, mock mode, bounded retries, token/cost accounting; live behavior tested with a fake SDK, not a real Meta call |
| Startup | `launcher.py`, `../start.bat` | Python 3.12 virtualenv, dependency installation, uvicorn, browser readiness; port configurable without API changes |
| Tests | `../tests/` | 28 baseline tests cover simulated lifecycle, API fields, hashes, chain, exports, mock calls, errors, and browser readiness |

All translation, golden recording, test pass counts, fixes, module green states,
and run token/cost figures were produced by `RunStore._simulate`. Its security
findings are string heuristics, not Bandit. `max_iterations` was accepted but did
not drive a repair loop. The pipeline never used `LLMClient`.

Replay was accepted as a health configuration value, but `LLMClient` explicitly
rejected it. There are no replay recordings or fixtures. There is nothing real
to preserve as a working replay implementation yet; later implementation must
fail on missing prompt hashes rather than inventing outputs.

## Issues and corrections in this iteration

1. Baseline API runs reached `done`/`green` even with `LLM_MODE=live` or
   `replay`, while the report was marked simulated. This could mislead a
   frontend consuming only state. Default runs now stop after actual source
   inventory and hash rechecking, with zero execution/model/security metrics.
   They fail with `docker_unavailable` or `pipeline_unavailable` and never go
   green. `reduced` denotes no container verification, not a host fallback.
2. Demo simulation now requires `PROOFPORT_PIPELINE=simulation` and
   `LLM_MODE=mock`; it is refused for live/replay. These are server settings,
   not new request fields. Existing endpoint paths and state shapes remain.
3. Static-only reports explicitly say dynamic verification and security scans
   did not run. Empty findings do not assert safety. Static inventory is only
   filenames, text-based module inventory, and hashes, not the universal
   analyzer requested for P3.
4. `core/readiness.py` probes only Docker metadata and local image presence.
   It never pulls images, imports project code, starts a container, or calls a
   model. It reports configuration booleans, never credentials. Even when all
   configuration checks succeed, `pipeline_implemented=false` prevents a
   readiness claim. Image presence does not prove a working sandbox or tests.
5. Source hashing during startup now turns read failures into a contract error
   instead of leaking an unexpected exception during the second hash pass.

## Concrete file plan and acceptance gates

### P0: Python 2.7 to Python 3.12, Docker only

Implement these in small slices only when their real integration checks can
run. Keep the runner and evidence types independent of one hard-coded version
pair; only 2.7/3.12 may be advertised after the demo case passes.

| Files | Change | Required evidence |
| --- | --- | --- |
| `sandbox/runtime.py`, `sandbox/runner.py` | Runtime descriptors and Docker-only adapter. Pin tested image identities. Network off, CPU/memory/PID limits, non-root UID, read-only root/source mount, drop capabilities, no-new-privileges, bounded writable temp, output limit, timeout and forced cleanup. Never mount Docker socket, credentials, or arbitrary host roots. | Real container tests for runtime versions, blocked network and writes, non-root UID, timeout/cleanup, resource exhaustion, and output overflow. No fallback if daemon/image is missing. |
| `core/workspace.py`, `core/evidence.py` | Copy sources into per-run workspaces, preserve relative structure, reject escaping links, hash before/after, persist chain as append-only JSONL. Keep runtime artifacts under `backend/` until root `work/` ownership is approved. | Original bytes unchanged, traversal/link rejection, interrupted-run persistence, chain tamper detection. |
| `sandbox/analyze_py2.py`, `core/analyzer.py` | Parse Python 2 syntax inside its interpreter; extract imports, public signatures, classes and dependency order without importing target modules. Use explicit 2.7/3.12 runtime descriptors. | Real Python 2 parser results, package/relative imports, cycles and script handling. No exact version guesses from compatible syntax. |
| `sandbox/harness.py`, `core/recorder.py` | Trusted 2.7/3.12-compatible harness executed in Docker. Existing tests, generated JSON inputs and scenarios, type-tagged values/exceptions; deterministic capture of stdout/stderr and controlled side effects. | Actual legacy golden captures, malformed input rejection, isolation checks, explicit missing/insufficient cases and harness failures. |
| `core/comparator.py` | Normalize only documented differences, preserve sequence order and exception evidence, record every allowed difference. | Boundary tests for division/rounding traps, bytes/text, dict/set order, types, floats and exceptions. |
| `core/translator.py`, `core/verifier.py` | Existing `LLMClient`, strict single-file parsing, compile in target Docker runtime, retry failing golden comparisons up to `max_iterations`, save reasons/results. | Real Meta response plus Docker verification; forced mismatch, failed compile, retry exhaustion, zero-case failure. Green requires actual successful verification with stated coverage. |
| `llm/client.py`, `core/runs.py`, `core/report.py` | Connect actual model usage and sandbox evidence, safe replay lookup, truthful metrics and limitations, compatible API state projection. Remove the unavailable gate only for implemented and tested execution paths. | Real end-to-end run, timeout/cancellation, busy slot release, absent key/model, replay miss, HTML/JSON exports. Mock/replay outputs alone never establish behavior equivalence. |
| `../tests/test_sandbox_integration.py`, `../tests/test_pipeline_e2e.py` | Original integration fixtures; use real `samples/legacy_shop` when supplied. | Successful real 2.7 to 3.12 migration with unchanged original hashes. Missing Docker/model/fixtures is an explicit skip or failure, never a passing synthetic migration. |

The runner constraints above follow the available Docker controls described in
[Docker's run reference](https://docs.docker.com/engine/containers/run/).
They still require real adversarial integration tests before a sandbox claim.

P0 prerequisites to unblock: working local Docker with Linux containers; tested
2.7 and 3.12 image identities; real Meta key/model supplied privately; original
demo sources and existing tests. A model-name configuration check is not proof
that the provider supports that model. Do not install global services, stop
unrelated services, or expose an API key in a commit to satisfy these gates.

### P1: Bandit adapter, after P0

Add `security/base.py`, `security/bandit.py`, `core/security.py`, and scanner
fixtures. Preserve raw scanner evidence separately from the contract finding
projection. Store CWE, severity, confidence, file/line, description, suggested
fix and verification status internally and in exports. Report parse errors and
coverage gaps. [Bandit documents AST/plugin analysis for common Python security
issues](https://bandit.readthedocs.io/en/latest/); it is not uniform coverage of
all requested categories. Clean output never proves complete security.

### P2: AI security fixes, after verified P1 results

Extend `core/security.py`, add `security/fixer.py` and rollback tests. Persist
before/after scanner evidence, minimal patches, model explanations and real
retest results. Preserve `fixed`, `open`, `needs_review`, `false_positive`,
`fix_reverted`. API/crypto/data compatibility changes need review. A fix is
accepted only after sufficient behavior cases and a real rescan; otherwise
retain or restore the previous candidate. Keep source originals read-only.

### P3/P4: additional versions and broader analysis

Extend runtime descriptors and analyzer adapters with actual interpreter tests;
single files and directories; explicit source version when syntax/metadata are
ambiguous; target choices from tested capabilities. Do not promise every
Python version. Broader scanner adapters and UX are later stages.

## Proposed API extensions: design only

No fields below are implemented, accepted, or required by current endpoints.
Keep section 8 state fields and the frontend unchanged until human review.

- Propose optional `source_version` and `target_version` in `POST /api/runs`,
  validated against tested runtime descriptors rather than arbitrary strings.
- Propose a capabilities resource to distinguish configured runtimes from
  runtimes actually validated by integration tests.
- Propose a verification/coverage object so the UI can show unavailable,
  insufficient, and verified outcomes without overloading `failed`.
- Rich security evidence can live in report exports; discuss any new state
  fields with the frontend owner first.

Today the existing contract has no `unverified` module status: an unavailable
required verification is represented as `failed` with an error and evidence.
No new run fields, endpoint paths, or frontend changes were introduced.
