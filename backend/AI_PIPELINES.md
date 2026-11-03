# P7 — structured model-response migration and security verification

Current live operation is documented in [P13_LIVE_DEMO.md](P13_LIVE_DEMO.md).
Historical verified results are in [P82_LIVE_RESULT.md](P82_LIVE_RESULT.md) and
[P83_PHP_LIVE_RESULT.md](P83_PHP_LIVE_RESULT.md). Generic AIJob live launching
remains disabled; the P7 results below are historical offline checks.

Implemented in `integration/p4`, starting at frontend `0e4c97f`. This milestone
connects LLMClient to both language adapters and the existing verification/fix
engines. **Only mock/replay generation was exercised. No genuine Meta request,
provider validation, credit usage or Live AI readiness is claimed.**

## Architecture and entry points

`LanguageRegistry().get(language).migrate_ai(AIJob(...), client)` is the internal
entry point. A frozen AIJob holds project/cases, exact source/target versions,
iteration limit, optional security generation and bounded finding selectors.
No RunStore defaults, `.env` or process environment is changed to select a job.
The job owns/closes its client. All generation in that job shares its one budget.

Supported exercised pairs:

* Python 2.7 → 3.12: delegates to `core.pipeline.execute` with an injected
  StructuredTranslator and optional LLMFixGenerator. The original analyzer,
  golden recorder/comparator, existing tests, Bandit and SecurityFixEngine remain.
* PHP 7.4 → 8.3: delegates to `php.pipeline.execute`, using the same structured
  provider boundary and the existing PHP harness/comparator/scanner/fix verifier.

Analyze → Record source outcomes/tests → model-response Translate → Docker syntax,
golden and existing tests → bounded model-response repair → Security → optional
verified model-response security proposals → Report. Retry is permitted only for
offline verification failures, within max_iterations (1..5) and shared LLM limits.
Malformed/unbound responses, unavailable model/replay or budget errors stop the
job; no fixture or provider fallback is substituted.

The existing fixture pipelines remain explicit and independent. Supplying a
translator with a PHP fixture manifest or a separate security session is rejected.
Python model runs do not read translation/security fixture settings. Tests may
author mock/replay responses from our own demo code; that does not make them AI
output, and it is not a runtime fallback.

## Prompts and structured replies

`ai/prompts.py` has separate Python and PHP translation instructions. The security
prompt names the target language/version in its JSON context and asks for minimal
single-file changes and honest impacts. All source/findings/feedback are untrusted
data. Expected golden values and raw test failure bodies are never sent. Repair
feedback contains status, case/test IDs or a generic failure marker plus the
previous candidate.

ModelPatch/v1 requires exactly these fields (no extra keys, fences or coercion):

```json
{
  "task": "translate",
  "language": "php",
  "file": "src/legacy.php",
  "source_sha256": "<64 lowercase hex characters>",
  "finding_id": null,
  "explanation": "Explain this candidate; do not claim tests ran",
  "proposed_code": "<?php /* complete single-file candidate */",
  "behavior_impact": "preserves",
  "confidence": 0.8,
  "review_areas": []
}
```

Security uses task=security and the exact finding_id. Binding fields must match
the request. The provider cannot select paths, provenance, tests, commands/mounts,
or trusted status. Output cannot target tests/dependencies/service/traversal paths.
Impact is preserves/changes/unknown; review areas are api/configuration/crypto/
data_format. Unknown/changed translation impact is stopped with needs_review.

Response source_sha256 binds the UTF-8 context text (read with normalized newlines).
Separate project hashes always use actual inventoried bytes before/after copying
and execution. Confidence and declared preservation never replace Docker checks
or the independent security acceptance policy.

The older fenced-code LiveTranslator/parse_code and legacy proposal parsing
methods remain compatibility boundaries for P5.1 tests; they do not activate P7.
P7 generation uses the strict shared ModelPatch schema for both languages.

## Offline model transport and budgets

LLMClient accepts an explicit per-client mode override. A mock_responder callback
is permitted only in mock mode; it is trusted local test code that returns text,
not a mechanism to execute generated code. Default canned mock text is not a
translation and fails the structured schema. Scripted mock/replay require frozen
LLMLimits: call count, conservative input/output byte allowance against token
limits, total reservation, timeout and cost policy. The client hard maximum is
10 calls and 8192 output tokens per call; oversized whole files require manual
planning, not silent truncation or automatically increased budgets.

Replay is a bounded local JSON file, not provider history or paid execution:

```json
{
  "mode": "explicit_model_response_replay_not_live",
  "responses": [
    {"prompt_hash": "<SHA-256 of compact JSON [system,user,true]>", "response": "<structured JSON text>"}
  ]
}
```

At most ten ordered records/2 MB are accepted. Changed prompts, source context,
schema, order or exhaustion fail closed. Replay never invents usage: actual
provider calls/tokens/cost are zero. response_calls/response_attempts and reserved
tokens are recorded separately; they are not billed model usage. ai_migration,
provider_validated and live_enabled remain false. No raw prompt/provider body is
stored in evidence; only hashes, safe outcomes and sanitized proposal metadata.

The existing SDK live client still has explicit authorization, verified-price
requirements, call/token/cost reservations, timeout and zero HTTP retries. Its
in-memory HTTP tests remain part of the fast suite. **ModelSession currently
rejects live clients even if a key is configured.** Iteration loops cannot spend
paid requests. A future live rollout must keep a separate operator/per-call
approval boundary for any additional paid repair; setting LLM_MODE/key is not
permission and must not activate automatic paid retries.

## Security proposals, review and rollback

LLMFixGenerator now operates only with an explicit bounded ModelSession. It sends
one finding (selected fields only) and one redacted source file, not the project,
raw scanner body, keys or golden answers. It returns a typed FixProposal; its
mode is assigned from the transport, not model JSON. Finding filters and a limit
of 1..4 proposals keep remaining findings open rather than silently spending.

Python and PHP security engines stage proposals on separate copies and check
syntax, recorded cases, unchanged existing suites, source hashes and rescan.
For model responses, changed behavior/test failure or incomplete coverage means
needs_review with rollback. Syntax failure is reverted, with later checks marked
not run. Passing checks or warning disappearance alone do not authorize changes.

Independent auto-acceptance remains deliberately narrow: Python's exact
constant-shell→literal absolute argv transformation, or PHP's exact owned
constant printf→literal argv transformation. Other changes, public API, eval,
queries, credentials, crypto/configuration/data formats require review. No model
false-positive dismissal is enabled. Findings remain potential risks unless
independent evidence establishes more; clean output is not complete security.

Failed model iterations/candidates are retained. Python restores its copied
project to the last verified translation/original baseline; PHP promotes only
verified copies and retains rejected branches. Security-pass failure reverts
accepted security changes to the verified migration baseline. Originals are
never patched. Final source/evidence checks repeat before export; integrity
failure prevents success and removes any accepted-result claim.

Known private assignment literals are replaced by placeholders in model context
and restored locally without sending their values. Short ambiguous literals need
manual context preparation. This is bounded redaction, not a generic secret/DLP
scanner. The configured model credential in any inventoried input/filename blocks
the job before copying/execution. Error/usage records never contain the key;
sentinel tests cover source, data and model response/error cases. Generated code
is only syntax-checked/tested/executed in Docker. No Composer/pip install or
image pull is performed by this workflow.

## API and frontend

All existing routes and request/state contracts remain. No new HTTP launch mode
or frontend control was added. Capabilities add model_workflows metadata marked
internal_language_adapter/public_launchable=false. Root/language operation modes
stay offline_fixtures/offline/simulation; live and ai_security_fix remain disabled.
Preflight makes no model requests. Existing PHP offline readiness still requires
its current code/demo/image/artifact-bound proof. It does not certify Meta AI.

## Local use

Python API example for a deliberately authored local responder:

```python
from pathlib import Path
from backend.ai.pipeline import AIJob
from backend.languages.registry import LanguageRegistry
from backend.llm.client import LLMClient
from backend.llm.budget import LLMLimits

# provide_json is trusted test code returning a bound ModelPatch JSON string.
client = LLMClient(mode="mock", mock_responder=provide_json,
    limits=LLMLimits(max_calls=4, max_input_tokens=16384,
                     max_output_tokens=8192, max_total_tokens=98304))
job = AIJob(Path("tests/fixtures/security_subject"), "python",
    Path("tests/fixtures/security_subject/cases.json"), "2.7", "3.12",
    max_iterations=3, security_fixes=True, security_rules=("B602",))
result, artifacts = LanguageRegistry().get("python").migrate_ai(job, client)
```

Explicit bound replay CLI (a valid responses file must already exist):

```powershell
.venv/Scripts/python.exe -m backend.ai --language php --project tests/fixtures/php_shop --cases tests/fixtures/php_profiles/cases.json --responses <local-response-recording.json> --max-calls 6 --security-fixes --security-rule PHP-CMD --security-scope constant_banner --security-scope unsafe_command
```

Artifacts are retained under backend/.work/ai-run-* (tests use unique retained
backend/.tmp roots): JSON/HTML reports, hash-chained logs, original/iteration/
rejected/verified copies, actual golden outcomes, checks and security attempts.
No generated/runtime data, environment file or replay containing private project
data belongs in Git. Offline model reports are internal diagnostic reports,
not a newly advertised API-export format or a Live AI badge.

## Verification in this milestone

Actual outputs (each pytest call used a distinct retained backend/.tmp base):

```text
pytest tests -q -m "not docker" -p no:cacheprovider
421 passed, 51 deselected in 8.71s

PROOFPORT_DOCKER_TESTS=1 pytest tests/test_ai_integration.py -q -p no:cacheprovider
4 passed in 68.70s

# Selected PHP proof, PHP replay and existing Python migration regression:
3 passed, 5 deselected in 37.84s

# Final Python mock/retry/security and PHP replay/security after export guards:
2 passed in 41.99s

node --test frontend/tests/*.test.cjs
tests 66; pass 66; fail 0

python -m backend.llm.smoke
executed=false; provider_validated=false; key/model/prices configured=false
```

Five distinct Docker scenarios passed overall; repeated selected cases validate
the final guards, not an expanded version/stress matrix. Forty-six other Docker
tests were not rerun. The model replies are explicit mock/replay test data, not
genuine model output.

* Python 2.7.18 → 3.12.16: real syntax failure, behavior/test mismatch, then
  successful offline-response repair; 3/3 golden cases and 2 source/target tests.
  A separately generated constant-command patch passed all checks and was accepted.
* Python security-budget exhaustion: failed with budget_exceeded, one response,
  no fallback; verified translation restored and rejected tree retained.
* PHP 7.4.33 → 8.3.36: six exact replayed responses, 22/22 golden cases and
  9 source/target tests; one independently supported hardening accepted, one
  unknown-impact proposal needs_review/rolled back; 10 → 9 potential warnings.
* Existing PHP fixture proof passed all fourteen checks; Python legacy migration
  regression still passed 90/90 golden cases and 10 existing tests per interpreter.
* All originals and evidence chains were checked. Unit tests additionally cover
  bad/duplicate JSON, stale bindings, missing model/replay, budget limits,
  private context, review/rollback, tampered final evidence and public live rejection.

No screenshots, real Meta requests, stress tests, broad Docker version matrix,
frontend edits, service shutdowns, merge/rebase or push.

Changed files: `ai/{__init__,__main__,models,pipeline,prompts,provider}.py`,
`llm/{client,replay}.py`, `core/{pipeline,capabilities}.py`,
`languages/{base,python,php}.py`, `php/{pipeline,fixes}.py`,
`security/{models,providers,engine}.py`,
`tests/test_ai{,_replay,_security,_integration}.py`, and backend documentation
`AI_PIPELINES.md`, `API_CONTROL_PLANE.md`, `ARCHITECTURE.md`,
`META_LIVE_READINESS.md`. Frontend, sample sources and dependency pins are unchanged.

## First genuine Meta request: separate permission still required

1. Privately supply MODEL_API_KEY and the actual dashboard MODEL_NAME in an
   ignored local `.env`; use MODEL_BASE_URL=https://api.meta.ai/v1 and verified
   positive PRICE_IN_PER_MTOK / PRICE_OUT_PER_MTOK for that model. Never paste
   the key into chat/frontend or commit it. Read META_LIVE_READINESS.md.
2. Run the free preview: `.venv/Scripts/python.exe -m backend.llm.smoke`.
   Current preview reported no key/model/prices configured, executed=false.
3. Obtain explicit permission for **one** bounded paid connectivity smoke.
   Only then use the existing `--execute --acknowledge-paid-api --max-cost-usd
   0.01` smoke options. No such command was executed in P7.
4. Inspect real authorization, JSON/schema support, usage and billing. A synthetic
   smoke proves connectivity only. Separately authorize/review the central live
   workflow gate and manual per-call approvals before real migration/security
   samples. Public capabilities must stay disabled until those checks pass.

The adapter/prompt/schema/verification architecture is wired; genuine provider
behavior, model quality, real AI repair success and safe paid continuation still
need this authorized validation. API keys alone do not make Live AI ready.
