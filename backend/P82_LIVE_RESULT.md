# P8.2 — genuine Meta mathutils migration verified

Explicitly authorized in this session: at most two requests, estimated USD 0.05,
9,216 input allowance / 3,072 completion tokens per call, 30-second timeout,
no transport retries or fixture fallback. Branch: `integration/p4`.

The new immutable `p8.2` CLI profile preserves the old `p8` profile; no global
environment, `.env`, RunStore configuration, public API or frontend was changed.
Prepared profile/limits must match execution. The iteration loop derives its
bound from that profile. An exclusive execution marker prevents paid restarts.
Two full reservations would cost USD 0.049152 at the configured Standard rates.

## Actual result

* Model: `muse-spark-1.3`, genuine live generation; no fixture/replay content.
* **One API request and one verified iteration.** No second request or AI Fix.
* Input tokens: **910**. Completion tokens: **1,689**, including **1,118 reasoning
  tokens** reported by the provider. Total input + completion: **2,599**.
* Estimated cost: **USD 0.00831575**, under the USD 0.05 cap. Reserved envelope
  for the one attempted request: USD 0.024576. This is configured-rate accounting,
  not an independent provider invoice or provider-side spending guarantee.
* Original wire `finish_reason=stop`; SDK agrees. JSON object valid, complete
  strict ModelPatch accepted; output limit not reached (1,689 < 3,072).
* Docker source: **Python 2.7.18**. Freshly recorded **31 golden cases**;
  all **three existing MathTests** passed.
* Docker target: **Python 3.12.16**. Syntax passed, **31/31 golden comparisons**
  matched and the same **3/3 MathTests** passed.
* Status: **done / ai_migration=true**, for this module and recorded scope.
* Original full-project inventory hashes unchanged. Evidence chain, artifact
  hashes, persisted events and HTML/JSON consistency independently verified.

The existing test class/assertions are copied verbatim into a scoped project;
imports are narrowed to `mathutils`. The full legacy_shop test suite and other
modules are not migrated/verified by this result. This is finite behavioral
evidence, not universal equivalence or a security audit. The improved repair
prompt was not exercised by this successful live run because no repair was
needed. Python/PHP public Live AI and AI Security Fix remain disabled.

## Retained local proof

Ignored workspace (no generated source, responses, credentials or runtime data
are staged in Git):

`backend/.work/p8-mathutils-bec88702e50948428fe35e2fa029af3e/`

Includes fresh source/target observations, analysis, byte hashes, original scoped
copy, `candidate/legacy_shop/mathutils.py`, `iteration_01/`, actual model response,
safe finish/token diagnostics, verification_01.json, evidence.log, report.json,
report.html and report_receipt.json. The previous failed P8 workspace is retained
unchanged. Credentials remain only in the ignored private smoke environment file.

| Artifact | SHA-256 |
| --- | --- |
| Prompt | `2b1fd8a1075c82c388cdc8fe158e1562214acbff360b2c3a70899572117399ab` |
| Model content | `407ebf03da187d5b75dce26e707334c8ce01cb5825aea2fa0db6bc416a1627e2` |
| Accepted candidate bytes | `d0c737a82d9f0564797a4139f4a3ebecb6bdf693dbe955674b3c2edaceeb8da8` |
| JSON report | `28b81b24a608e38112841788095f3ddd3835f4a493937b2851d52f27e930e123` |
| HTML report | `be83d1b2ce45d1f7bb5b0e40ec6bd17ecaa54428cb2d7d1a7c9b2b06b26119f2` |
| Evidence log | `5ad2336e989c6469551deb83a23203d74e8e8ca218345b956d314b1352e469f9` |

## Recheck retained reports without a paid call

After adding the bounded profile, the targeted mock/transport tests passed
(`117 passed in 11.32s`). The final fast backend regression also passed:

```text
470 passed, 52 deselected in 25.33s
```

The 52 other Docker tests were not rerun. The actual P8.2 source/target Docker
checks above ran directly as part of the single authorized live job. Unit tests
cover exact profile caps, rejecting a prepared-profile switch and stopping after
two failed candidates with rollback. No additional paid call was used for tests.

```python
from pathlib import Path
from backend.ai.first_live import verify_export
assert verify_export(Path("backend/.work/p8-mathutils-bec88702e50948428fe35e2fa029af3e"))
```

The actual paid command used the new prepared workspace exactly once:

```powershell
.venv/Scripts/python.exe -m backend.ai.first_live --execute --acknowledge-paid-api --profile p8.2 --workspace backend/.work/p8-mathutils-bec88702e50948428fe35e2fa029af3e
```

Do not rerun paid execution to inspect reports. Any additional genuine model
request needs separate authorization. No merge, rebase, push, screenshot,
image download or unrelated service shutdown was performed.
