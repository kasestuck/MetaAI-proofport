# P13: fixed-scope Dashboard live demos

Implemented preparation for two live demos using the existing P8 CLI engines:

| Profile | Scope | Required Docker verification |
| --- | --- | --- |
| `python_mathutils` | `samples/legacy_shop`, only `legacy_shop/mathutils.py`; existing MathTests copied verbatim | Python 2.7 → 3.12; 31 golden cases, 3 tests |
| `php_legacy` | `tests/fixtures/php_shop`, only `src/legacy.php`; other files unchanged | PHP 7.4.33 → 8.3.36; 22 cases, 9 tests |

This is not arbitrary-project live migration or live AI Security Fix. The prior
eval proposal stays rejected/needs_review. A live migration does **not** run a
security audit: zero security counts mean not scanned. Originals remain read-only.
Preparation/testing made **zero real Meta requests and zero paid calls**.
The new private key is not configured on this workstation; it is not claimed
authorized/available. First genuine Dashboard execution still needs owner consent.

## Local configuration without exposing a key

The ignored local file `backend/.tmp/meta-demo.env` has been prepared with an
empty key and approval disabled. For another clone, from repo root in PowerShell:

```powershell
New-Item -ItemType Directory -Force backend/.tmp | Out-Null
if (!(Test-Path backend/.tmp/meta-demo.env)) { Copy-Item backend/ai/meta-demo.env.example backend/.tmp/meta-demo.env }
code backend/.tmp/meta-demo.env
```

Enter a **newly issued** key locally in `MODEL_API_KEY`. Do not paste it into
chat, browser fields, terminal commands, video, issues or tracked files.
After entering a new key, set `LIVE_DEMO_KEY_CONFIRMED_NEW=true` in that private
file. Keep `LIVE_DEMO_APPROVED=false` until the owner separately authorizes the
first paid run; only then change it to `true`. Do not use the retired smoke key.
If it matches the retained old smoke configuration, admission refuses it locally.
A later 401/403 catalog or inference error also blocks/stops execution.

The template fixes `LLM_MODE=live`, model `muse-spark-1.3`, base URL
`https://api.meta.ai/v1` and standard prices 1.25 input / 4.25 output per million
tokens. The demo reads **only this isolated file**, not root `.env` or model
environment overrides. The browser cannot supply keys, paths, commands, prices,
runtime mounts, token limits or iteration limits.

## Model availability and pricing

Official documentation checked **3 November 2026**:
[Meta overview](https://dev.meta.ai/docs/overview),
[pricing](https://dev.meta.ai/docs/pricing-rate-limits),
[model catalog GET](https://dev.meta.ai/docs/api-reference/models/list-models).
They list `muse-spark-1.3`, the base URL above, and standard input/output prices
of $1.25/$4.25 per million tokens. Contributor mode is not selected.

**Check model access (catalog only)** makes one bounded `GET /v1/models`, no
generation request, tools or retry. Until it succeeds for the current private
configuration, status stays not_verified and paid admission is blocked. A catalog
success is not a smoke test, a credit/billing check or a guarantee of future
inference availability. The result expires after five minutes. Key/configuration
changes invalidate it. No remote request is made by ordinary readiness GETs.

## Launch and record the three-minute demo

1. Start Docker Desktop in Linux mode and prepare the existing Python/PHP images
   per the root README. No model code executes on the Windows host.
2. Run `start.bat`. Alternatively, after dependencies are installed:

   ```powershell
   .venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8765 --workers 1
   ```

3. Open the shown URL → **Migration** → **Real Meta AI demo** → **Live Meta AI**.
4. Configure the new key **before recording**, never with the file on screen.
   Once the separate owner permission is granted, enable the private operator
   flag, click **Check model access (catalog only)**, then **Refresh readiness**.
5. Select Python mathutils or PHP legacy.php. Read the exact scope and budget.
   Check the paid-consent checkbox, press **Start paid live demo — up to $0.05**,
   and confirm the dialog. Each additional run requires fresh consent.
6. Show actual baseline recording, translation/repair, Docker checks, usage/cost
   and final report/evidence. No percent/ETA is invented. Do not call the run
   successful until finalized, all required cases/tests match, source hashes are
   unchanged, report export succeeds and the independent browser chain check passes.
7. For the security segment select **Saved Replay** and open the reviewed prior
   rejected eval report. Say it is a historical rejected proposal, not a new call.
   **Offline Fixtures** returns to ordinary Run control for authored demo patches.
8. After recording, set `LIVE_DEMO_APPROVED=false` to block future paid calls.
   This cannot undo an already submitted request or its billing.

Allow time for real calls/checks; two live jobs may not fit into three minutes.
Record the actual runs honestly or use clearly labelled saved evidence; never
replace a failed call with fixtures while retaining a live label.

## Cost and admission rules

- Each run uses the existing immutable P8.2 envelope: at most **2 calls**,
  **9,216 input / 3,072 output tokens per call**, **24,576 total reserved tokens**,
  **$0.05 estimated budget**, **30 seconds per request**.
- At the documented rates, two full reservations total **$0.049152**. This is
  conservative client accounting, not an enforceable provider invoice cap.
- Local operator permission, fresh catalog status and a **120-second one-use UI
  consent** are all required. Consent binds source/cases bytes, image IDs and
  private configuration. Creation repeats checks, then takes the common run slot.
- Only local verification failures permit a second model repair. Timeout,
  API/auth/rate-limit errors, invalid/incomplete JSON or exhausted reservations
  stop; there are no automatic paid transport retries or fixture fallback.
- On an uncertain HTTP submission, the UI does not POST again automatically.
  Refresh metadata and **Attach active / latest live run**. Do not start another paid job
  until the prior outcome is reviewed. An identical idempotency key/payload
  returns the existing run; changed parameters conflict. Restart loses tickets
  and in-memory idempotency; never automatically replay an old approval.

## Success, rejection and evidence

The model proposes code; existing P8/P8.3 engines run syntax/golden/existing tests
in pinned Docker images and seal their original reports. The dashboard bridge
writes a **separate** HTML/JSON report and chain, referencing the retained raw
report SHA-256; it never overwrites a CLI report or receipt.

Progress counts come from observed checks. Syntax/test/behavior failure cannot
turn a module green; rejected candidates are retained and their working copy is
restored. Failed or incomplete generation stays failed, with a safe error code.
Timeout can leave token usage/billing unknown, which is displayed as unknown.
No key, provider body or exception text is sent to the browser/evidence.
Backend finalization, report loading and browser chain verification are distinct.

## Additive API

The five legacy and six existing v1 routes remain. Generic v1 `execution_mode=live`
continues to be refused; only these two new profile-based demos can authorize it.
`GET /api/v1/capabilities` adds a separate `live_demo` metadata object.

| Endpoint | Purpose |
| --- | --- |
| GET `/api/v1/live-demo` | Local configuration/model status, fixed profiles and per-profile readiness; no inference |
| POST `/api/v1/live-demo/model-check` | Explicit catalog GET only; no generation |
| POST `/api/v1/live-demo/confirm` | `{profile, consent:true}` → opaque `approval_id`, expiry, limits, instance ID |
| POST `/api/v1/live-demo/runs` | `{profile, approval_id}` plus required `Idempotency-Key` → HTTP 202 `{run_id}` |

Run polling uses existing `GET /api/v1/runs/{id}`; events and reports use existing
legacy routes. Specialized runs add `result.live_demo` metadata. No existing
RunState field or status enum changes. Live/scoped provenance overrides the
deployment's default mock mode. Saved replay always remains replay.

## Verification performed

Fast tests use mock HTTP and fake metadata only. Real Docker integration tests
use an isolated ignored Git root and explicit retained-response HTTP replay;
any ordinary HTTP transport is forbidden. They do not constitute new Meta usage.
Missing retained genuine candidates cause an explicit skip, never a fixture
substitution. Regression coverage includes missing/retired keys, auth/catalog
errors, budget reservation, timeout, invalid JSON, changed consent bindings,
busy/idempotency, real golden mismatch/rollback, evidence tamper rejection and
secret isolation. See the final task report for actual counts and local commits.

Actual final checks on 3 November 2026: **579 fast backend tests passed**
(63 Docker cases deselected), **78 frontend tests passed**, JavaScript syntax
checks passed. The five focused real Docker/HTTP-replay tests passed: Python
31/31 + 3/3, PHP 22/22 + 9/9, deliberate golden mismatch with two bounded repair
attempts/rejection, timeout with one attempt/unknown billing, and invalid JSON
with one attempt. Rollback restores actual candidate bytes; bridge-chain
corruption cannot preserve a successful state. No test made a real Meta call.
Python/PHP offline judge regressions were also checked separately; raw results
are retained under ignored `backend/.work/`. No images were pulled.
