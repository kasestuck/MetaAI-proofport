# P8.3 — first real PHP migration preparation, awaiting separate paid permission

Result update: [P83_PHP_LIVE_RESULT.md](P83_PHP_LIVE_RESULT.md) records the later,
separately authorized successful live trial: one genuine Meta request, 22/22
golden cases, 9/9 existing tests and estimated USD 0.00612075. The preparation
notes below are historical; originals and baseline receipts remain unchanged.

Branch: `integration/p4`. This milestone made **zero Meta API requests** and
spent **USD 0**. It prepares a runnable, bounded local trial; it does not claim
successful PHP AI migration. Original php_shop, frontend and public API are
unchanged. No PHP offline translation/security patch manifest is read.

## Selected file and genuine incompatibilities

Owned project: `tests/fixtures/php_shop`; selected file: **`src/legacy.php`**.
Two small functions use `each()` and `$text{0}`. PHP 8 removed both `each()` and
curly-brace offset access. Reference:
https://www.php.net/manual/en/migration80.incompatible.php .

The model may replace only that file, preserving namespace, signatures, ordered
mixed integer/string array keys, false for an empty array and byte-string offset
behavior. Its context is the selected source, not security modules or credentials.
All other source, data and **the entire native test file remain byte-identical**.

## Real baseline checks

Already-installed official images were inspected and pinned; no pulls occurred:

| Runtime | Image ID |
| --- | --- |
| PHP 7.4.33 | `sha256:620a6b9f4d4feef2210026172570465e9d0c1de79766418d3affd09190a7fda5` |
| PHP 8.3.36 | `sha256:600bce7c7acf524756e5aac989f4a763aed709960d7326970bb670f46efee53a` |

Actual PHP 7.4.33 lint passed. All **22 golden cases** were freshly recorded,
including **five cases** for the two selected functions. **9/9 existing native
tests passed**, with their original names and assertions. No PHP code ran on
Windows; only copied project files executed in Docker.

Actual PHP 8.3.36 runtime/protocol was confirmed. Original target lint failed
only for `src/legacy.php`, as expected. No translated candidate, target test pass
or target behavior match is claimed: target acceptance flags remain null.
Original project hashes and baseline HTML/JSON/evidence/artifact checks passed.

Retained preparation:

`backend/.work/p83-php-39cfcb6a2adf49a99b9948db31e01870/`

It contains original copied sources, recorded golden results, original test
outcomes, runtime/lint/analysis data, prepared.json, preparation.log,
baseline-report.json, baseline-report.html and baseline-report-receipt.json.

| Artifact | SHA-256 |
| --- | --- |
| Original selected file bytes | `f6389b36c56260eaf9167536d19eb3814de61daaddca0583b4c756167c590ae1` |
| Prepared manifest | `015df7d6eda0f1c05a7894564d06c25df593dc2638c735ff7541bc28c7de1ac5` |
| Baseline JSON report | `ec69edbeec76ab8091bef9fbf6bac59a58bbc8daab09b98306a8de05c34aa6f2` |
| Preparation evidence | `b87718f4c1274397e9d36a504f034b5846275a3ec94fd020156884825a8b35f1` |

## Concrete paid trial plan — not executed

1. Recheck original and copied bytes, recorded inputs, baseline receipts, pinned
   images, approved model and exact immutable LLMLimits.
2. Make one genuine `muse-spark-1.3` translation request using the existing
   ignored `backend/.tmp/meta-smoke.env`. Require strict ModelPatch JSON bound
   to language=php, task=translate, file=src/legacy.php and original source hash.
3. Retain response/provenance/prompt hash and an iteration copy. Run PHP 8.3
   syntax checks, the unchanged nine tests and all 22 typed golden comparisons.
4. Only a locally verified failure permits the second request, within the same
   shared budget. PHP repair prompt receives original source, previous candidate,
   failed call arguments and typed expected/actual observations. Failures outside
   the selected file require review rather than broader patch authority.
5. A complete candidate is accepted only with **22/22 golden matches and 9/9
   existing tests**, passing syntax and original/non-target/evidence integrity.
   Otherwise retain rejected copies and restore the original working copy.
6. Export JSON/HTML, usage and safe finish_reason/content/JSON diagnostics,
   hash-chained evidence, source/candidate/response hashes and receipts. Verify
   the exports independently. Never serialize credentials or raw provider errors.

Only the existing profile's explicit deprecation-notice difference is allowed.
Ordered arrays, key/value types, binary strings, stdout, other warnings and
exception/runtime-error observations remain strict. Finite cases do not prove
every input, extension, database/web behavior or security. No security fix,
PHPUnit dependency installation, fallback translation or public Live API is added.

The existing sandbox stays network-disabled and read-only, non-root, 1 CPU,
256 MiB, 32 PIDs with bounded time/output; only scoped source and trusted harness
are mounted. No model key is passed to Docker or frontend. Invalid/truncated
responses, timeout, rate limit, authorization errors or exhausted budgets stop
without automatic paid retry. No partial-code recovery or auto-continuation.

## Limits and cost estimate

Frozen per-run profile, independent of global RunStore/environment switches:

* Maximum **two** model requests, zero HTTP retries.
* Per request: **9,216 input allowance**, **3,072 completion tokens** (including
  reasoning), **30-second timeout**. Total reservation: **24,576 tokens**.
* Estimated cost cap **USD 0.05**. Full reservation per request: **USD 0.024576**;
  two full reservations: **USD 0.049152**. Reservations are not refunded/reused.
* Configured Standard rates: USD 1.25/M input and USD 4.25/M output, checked
  against https://dev.meta.ai/docs/pricing-rate-limits . No cached-input discount
  is assumed. Local estimates are not provider-side spending guarantees.

Offline synthetic context-size checks measured **3,300** initial / **6,727**
repair bytes including framing, within the 9,216 input guard. These are size
checks, not actual model token counts or evidence of a successful repair.

## Entry points

Free preparation (already completed above):

```powershell
.venv/Scripts/python.exe -m backend.ai.first_php_live --prepare
```

**Only after separate explicit PHP paid approval**, execute the prepared workspace
once (an exclusive execution marker prevents accidental paid restarts):

```powershell
.venv/Scripts/python.exe -m backend.ai.first_php_live --execute --acknowledge-paid-api --workspace backend/.work/p83-php-39cfcb6a2adf49a99b9948db31e01870
```

Independent baseline verification, no model request:

```python
from pathlib import Path
from backend.ai import artifacts, first_php_live
assert artifacts.verify(Path("backend/.work/p83-php-39cfcb6a2adf49a99b9948db31e01870"),
                        first_php_live.unchanged, stem="baseline-report")
```

Generic Python/PHP AIJob and public API live activation remain disabled. The new
PHPModuleLiveApproval is a separate internal explicit file/hash/budget-bound
approval object. Environment settings alone cannot enable generation. Mock/replay
tests return the original incompatible code and explicitly fake verification
outcomes; they do not supply a corrected fixture or prove actual AI migration.

## Actual test results

```text
pytest tests -q -m "not docker" --tb=short -p no:cacheprovider --basetemp=<unique ignored path>
495 passed, 53 deselected in 34.91s

PROOFPORT_DOCKER_TESTS=1 pytest tests/test_first_php_live_docker.py -q --tb=short -p no:cacheprovider --basetemp=<unique ignored path>
1 passed in 8.25s
```

Coverage includes baseline receipts, exact budget caps, changed source/data/
report detection, file/task binding, one-call success and two-call repair using
explicit test doubles, syntax/behavior failure rollback, timeout/invalid/truncated
response stop, unchanged native tests and bound replay. One Windows unit test
initially exceeded the path length limit; its uniquely retained temporary child
name was shortened, without deleting artifacts or weakening verification.
The existing Python fast tests pass. No heavy Docker matrix was repeated.
