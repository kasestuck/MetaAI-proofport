# P5.1: first Meta call readiness — 2026-11-01

P7 update: [AI_PIPELINES.md](AI_PIPELINES.md) describes the new strict shared JSON
ModelPatch boundary, language adapters and mock/replay security generators.
The fenced-code/disabled-generator paragraphs below describe the preserved P5.1
interfaces. P7 model workflows still reject live clients and have made no Meta
request. Existing paid-smoke authorization and client budget gates remain intact.

No genuine model request was performed. No API credit was used. The provider,
account permissions and model quality remain unverified until a separately
authorized live smoke. Work stays on `integration/p4`; the HTTP control plane
and security generator still reject live execution.

## Audit and changes

The existing client correctly read MODEL_API_KEY, MODEL_NAME, MODEL_BASE_URL
(default https://api.meta.ai/v1) and LLM_MODE, with environment overriding dotenv.
Mock mode was free/offline. However, live mode previously depended only on
configuration, used two implicit SDK retries, had no output/call/spend budget,
collapsed distinct HTTP failures, and could discard usage on invalid replies.
The old README also implied that live migration could already be enabled.

The client now requires `allow_live=True` and an explicit frozen `LLMLimits`,
in addition to live mode, key/model and explicitly supplied positive token prices.
It constructs SDK/HTTP clients only at the first authorized request. There is no
live-to-mock/fixture fallback and no new browser endpoint/authorization toggle.

- 401, 403, 429, timeout, connection, bad-request, missing-model and provider
  errors have separate safe codes. Raw provider exceptions/bodies are withheld.
- SDK retries are zero, including on 429. A failed/incomplete request stops that
  client session. A timeout can have an unknown billed outcome; never retry it
  automatically or interpret zero reported usage as proof of no charge.
- All requests have a completion-token cap, n=1, no streaming/tools and minimal
  reasoning. No automatic parameter/model fallback sends a second request.
- Responses must contain one completed plain-text choice and valid original
  integer token counts with matching total. Refusals, tools, truncation, empty
  content and missing/malformed usage are rejected.
- JSON mode also rejects invalid/non-object JSON, non-finite values and duplicate
  keys. Known usage is recorded even if the generated content is rejected.
- An audit test exposed SDK integer coercion: string usage counters looked valid
  after SDK parsing. The client now checks the original HTTP JSON counters via
  the SDK's raw-response interface before accounting.

The existing pinned `openai==3.19.0` actually uses `httpx2`. Tests use its real SDK
with `httpx2.MockTransport`; merely mocking a different httpx package would not
exercise the installed transport. No dependency versions were changed.

## Format compatibility

Translator continues to require exactly one complete fenced Python module.
Transport text is tested through LiveTranslator/parse_code, without executing
generated code. Translator has no new default authorization: constructing it
with live configuration alone is still blocked by the client, and the migration
worker already stops before translator construction.

Security proposals continue to use FixProposal fields: finding_id, explanation,
proposed_code, behavior_impact, confidence, and existing disposition/review fields.
HTTP-mocked JSON passes the existing schema and finding-ID checks; parsing forces
model provenance to live so a response cannot call itself a trusted fixture.
LLMFixGenerator.generate still raises OfflineOnlyError. No model patch is applied,
verified or advertised as fixed, and the offline security engine/fixtures were
not modified.

## Budgets and their limits

The first-call smoke is fixed at one attempt, 2048 input-token allowance, 256
completion tokens and 2304 reserved total tokens, with a 15-second SDK network
timeout and explicit dollar cap at most $0.05. Typical requested smoke cap is
$0.01. These limits are not applied to mock canned answers, which remain free.

Before sending, the client reserves the *full* input allowance plus output cap
and the corresponding cost at operator-supplied rates. UTF-8 message byte count
plus a 256-token framing allowance conservatively gates input size. It is not a
provider-verified tokenizer or a formal bound on provider-side prompt expansion.
Reservations remain consumed on success and failure; concurrent calls cannot
reserve the same remaining budget. Failed/unknown attempts have a separate
record containing only a prompt hash, reservation and safe outcome code.

Actual usage above the reserved envelope is recorded and stops the session. It
cannot undo charges already made. Cost values are estimates using the configured
model rates, with no cached-input discount assumed. Provider behavior, rate
changes or unknown timeout outcomes cannot be turned into a guaranteed client-side
dollar ceiling. Set/check the provider's own spending controls too. Limits are
per client/process, not a durable account-wide quota across manual CLI restarts.

## Credential checks

The checked repository has no configured MODEL_API_KEY/MODEL_NAME. Root `.env`
is not tracked and is ignored by the existing local `.git/info/exclude`. That
local exclusion is not a repository-wide ignore policy for other clones.

Before an executed smoke, a read-only Git guard requires any in-repository
credential file to be ignored, rejects tracked credential files, and checks
tracked working-file contents for the configured key. The key is not passed as
a Git command argument or written to a temporary pattern file. This is not a
generic secret detector or a scan/cleanup of every historical Git blob. If a key
has ever been committed/shared, it needs provider rotation and separate reviewed
history cleanup; this milestone does not rewrite history.

The client no longer retains the complete dotenv/OS settings dictionary. Its
usage/attempt snapshots contain no key, source, prompt or generated content.
The smoke never prints model text, request/response bodies or credentials.
Sentinel tests confirm that provider errors/key echoes do not leak through
exceptions, logging, usage records or smoke JSON output. Credential-containing
prompts and model content are rejected. Live requests are refused when SDK/HTTP
debug logging is enabled, rather than enabling diagnostic headers/body dumps.

Live base URLs are restricted to HTTPS api.meta.ai `/v1`, without credentials,
query strings, custom ports or fragments. The owned HTTP client does not inherit
environment proxies and does not follow redirects. No key, settings DTO or new
live capability is exposed to frontend/report routes. Frontend is unchanged.

## Official contract references

Checked public documentation, without authenticated provider requests:

- [Meta Quickstart](https://dev.meta.ai/docs/quickstart): SDK-compatible base URL
  and dashboard-provided credentials/model IDs.
- [Chat Completions](https://dev.meta.ai/docs/protocols/chat-completions): text
  response format, max_completion_tokens and minimal reasoning option.
- [Errors](https://dev.meta.ai/docs/error-handling): HTTP error categories.
- [Pricing](https://dev.meta.ai/docs/pricing-rate-limits): model-specific rates;
  Standard/Contributor are distinct selections, never an automatic switch.

Use the model ID actually available in your account. No model name or price is
guessed from the hackathon credit balance. The public reference is not proof of
your account's permissions or a successful SDK call.

## First genuine request — user action after separate authorization

1. Obtain the API key privately from the Meta dashboard. Do not paste it into
   this chat, source code, a command-line argument or screenshots.
2. Confirm the exact available model ID, its data mode and current input/output
   prices in the dashboard. Check account spending controls and authorize one
   synthetic request with the chosen dollar cap.
3. In a private ignored file, for example `backend/.tmp/meta-smoke.env`, set:

   ```dotenv
   LLM_MODE=live
   MODEL_API_KEY=<private key entered locally>
   MODEL_NAME=<exact account model ID>
   MODEL_BASE_URL=https://api.meta.ai/v1
   PRICE_IN_PER_MTOK=<verified positive input price>
   PRICE_OUT_PER_MTOK=<verified positive output price>
   ```

   Existing process environment variables override that file. This file is for
   the standalone smoke, not an instruction to enable live server operations.
4. Preview offline; this command cannot make a model request:

   ```powershell
   .venv/Scripts/python.exe -m backend.llm.smoke --env-file backend/.tmp/meta-smoke.env
   ```

5. **Only after separate permission**, run once:

   ```powershell
   .venv/Scripts/python.exe -m backend.llm.smoke --env-file backend/.tmp/meta-smoke.env --execute --acknowledge-paid-api --max-cost-usd 0.01
   ```

The command sends only a synthetic JSON connectivity prompt, not a project.
It validates `{"proofport_smoke":"ok"}` and prints safe accounting metadata.
It does not migrate code, enable live HTTP runs, modify the source, or call the
security generator. If the model needs more than 256 tokens it can fail with a
truncated response: do not automatically raise the cap or repeat the request.
After any failure, check provider billing/outcome before authorizing another call.

## Local verification

```text
pytest tests -q -m "not docker" -p no:cacheprovider
247 passed, 41 deselected in 13.92s
```

The added HTTP tests replace all sockets with an explicit failure and route SDK
requests only through in-memory MockTransport. Covered: successful reply, 401,
403, 429, timeout, connection/server errors, malformed HTTP JSON, invalid generated
JSON, empty/truncated/refused replies, malformed usage, all budget dimensions,
concurrent reservation, missing key/prices/permission, URL/redirect restrictions,
debug logging, credential leakage, Translator/security parsers and CLI gates.
The new smoke command was run only in its offline default mode on this checkout;
it reported executed=false and provider_validated=false.

Docker tests were deselected. No offline fixtures, replay behavior, Docker
checks, frontend or public API contract were changed. No merge/rebase/push.
