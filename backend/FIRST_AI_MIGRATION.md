# P8 — first genuine Python module migration: awaiting paid approval

Update: the approved P8 run failed (26/31 cases, three tests, two API attempts,
USD 0.01367425). [P8_FAILURE_ANALYSIS.md](P8_FAILURE_ANALYSIS.md) records P8.1's
offline diagnosis, detailed opt-in repair observations and response diagnostics.
The preparation notes below are historical; no successful live repair is claimed.

The separately authorized synthetic Meta smoke succeeded in this session:
one request, 57 input / 65 output tokens, estimated USD 0.0003475. That verifies
connectivity for `muse-spark-1.3`, not a migration or security fix.

P8 preparation has made **zero model requests**. No real AI migration result is
claimed yet. Public API capabilities and both generic Python/PHP AIJob live gates
remain disabled. The only new live path is an explicitly acknowledged, local,
single-module command; it cannot generate security fixes or migrate PHP.

## Exact scope and plan

* Original: `samples/legacy_shop/legacy_shop/mathutils.py`, six functions.
* Analyze and record 31 existing golden inputs under actual Python 2.7.18.
  Inputs come from `tests/fixtures/legacy_shop/cases.json`; no translation patch
  manifest is read. Outcomes are freshly executed, never fixture expectations.
* Existing `MathTests` has three tests. Its class, assertions and method bodies
  are copied verbatim into an isolated snapshot. Only imports are narrowed to
  `unittest` and `mathutils`, avoiding unrelated unported modules. This is an
  explicitly scoped suite, **not the full ten-test legacy_shop suite**.
* Send only the module source and strict ModelPatch schema to Meta. Expected
  golden values, raw failure bodies and unrelated project files are not sent.
* Retain the returned candidate and prompt hash. Compile, execute the same
  golden cases and run the unchanged scoped tests in Python 3.12.16 Docker.
* Repair only when local verification fails, within the separately approved
  three-call batch. Feedback contains statuses and failing IDs, not answers.
  Stop on transport/authentication/rate-limit/JSON/schema/budget failures.
* Accept only if syntax passes, all 31 comparisons match and the same three
  existing test IDs pass. Check actual original byte hashes and evidence again.
  Otherwise retain rejected candidates and restore the scoped original copy.
* Export JSON/HTML, response records, usage, checks, evidence chain and artifact
  hashes. `verify_export()` independently checks retained bytes, chain ordering,
  report consistency and originals. Hashes detect inconsistency, not an attacker
  rewriting every local artifact and receipt together.

No original sample is edited or imported on the host. Existing DockerRunner
enforces read-only mounts/root, no network, non-root, dropped capabilities,
1 CPU, 256 MiB memory, 32 PIDs and time/output limits. Images are inspected and
pinned to actual local IDs; no downloads/installations are performed.

## Budget and authorization

Read the existing ignored `backend/.tmp/meta-smoke.env` without printing it.
Require the smoke-tested model, API base and Standard prices:
`muse-spark-1.3`, `https://api.meta.ai/v1`, USD 1.25/M input and 4.25/M output.
Sources: https://dev.meta.ai/docs/models and
https://dev.meta.ai/docs/pricing-rate-limits (checked 2026-11-01).

Frozen per-run LLMLimits:

* At most three requests, one client, zero SDK/HTTP retries.
* Per request: 7,936 input allowance, 1,536 completion limit, 30-second timeout.
* Total reservation: 28,416 tokens; maximum reserved estimate USD **0.049344**.
* Explicit cost cap USD **0.05**. Full reservations are never refunded/reused.

The existing byte-based input guard is conservative, not a provider tokenizer.
Local cost guards are estimates, not a provider-side spending guarantee. Unknown
timeout charges cannot be undone. A durable exclusive execution marker blocks
relaunching the same workspace, including after a crash/timeout; review the
outcome and obtain permission before preparing any replacement paid run.

`ModuleLiveApproval` binds the exact module and source SHA-256; keys/env/API
requests cannot create this approval. Mode, file, language, task and budget must
still match. The generic ModelSession without this explicit object rejects live.
Successful responses, including schema-invalid text returned by LLMClient, are
saved after credential/private-literal redaction. Transport/client-rejected
bodies are withheld; safe attempt hashes/outcomes and any reported usage remain
in evidence. Neither logs, reports nor console output contain credentials.

## Commands

Free preparation (Docker execution, no Meta client/request):

```powershell
.venv/Scripts/python.exe -m backend.ai.first_live --prepare
```

Inspect the printed retained workspace and show the user this exact plan before
requesting separate paid consent. Do not infer migration permission from the
earlier synthetic smoke approval.

Only **after separate approval for this P8 batch**, use its prepared workspace:

```powershell
.venv/Scripts/python.exe -m backend.ai.first_live --execute --acknowledge-paid-api --workspace backend/.work/p8-mathutils-<preparation-id>
```

All artifacts remain ignored under `backend/.work/`. Do not stage credentials,
generated candidates, response records or test/runtime data. No frontend, API
contract, sample source, offline translator or dependency pin was changed.

## Actual preparation checks

* Actual Python source interpreter: 2.7.18. Recorded 31 cases; three existing
  MathTests passed. All original inventory hashes remained unchanged.
* Actual target interpreter: 3.12.16. The **unmigrated** module failed syntax
  with one error as expected. No passing target migration is claimed.
* Synthetic first/repair context guards measured 3,718 / 4,882 bytes plus framing,
  within the 7,936 input allowance. This was offline size checking, not Meta use.
* 27 P8 unit tests passed using in-memory HTTP and explicitly fake Docker
  results. They do not establish migration success. Real target behavior and
  repair quality remain pending the separately approved model run.

Final fast backend regression (no Docker matrix or Meta requests):

```text
pytest tests -q -m "not docker" --tb=short -p no:cacheprovider --basetemp=<unique ignored path>
448 passed, 51 deselected in 25.55s
```

The restricted Windows test process stalled in TestClient; only that task-owned
process was stopped and the suite rerun outside that restriction. A report
comparison failure during development was corrected by using the same sorted
JSON rendering for HTML and JSON; the final suite above includes that correction.
