# P8.4 — first live security proposal preparation; separate paid consent pending

Branch: `integration/p4`. **Zero genuine Meta API requests, USD 0 spent in P8.4.**
This milestone prepares generation and independent verification of one eval
proposal. No AI security fix is claimed, no existing acceptance policy is loosened,
and public API/AI Security Fix controls remain disabled. Frontend, original sample
sources, API contracts and previous Python/PHP proof artifacts are unchanged.

## Selected potential risk

* Finding **B307-501c959a03faf42afa68fc25**, Bandit B307.
* `samples/legacy_shop/legacy_shop/config.py:7`, scope `parse_value`, column 15.
* Severity **MEDIUM**, confidence **HIGH**, **CWE-78 as assigned by Bandit 1.8.6**.
* Status **open**; `potential_risk_not_confirmed`. Untrusted external input
  reachability and exploitability have not been established.

`parse_value` strips text, evaluates a Python expression and returns the raw
string on errors. A controlled Docker probe confirmed `1 + 2 -> 3` and
`__import__('math').sqrt(9) -> 3.0`. These are non-destructive language-contract
witnesses, not exploit proof. Bandit reference:
https://bandit.readthedocs.io/en/1.8.6/blacklists/blacklist_calls.html#b307-eval .

## Critical runtime/contract boundary

Only mathutils was AI-migrated previously; **config.py is still original legacy
code**. Security verification must not silently combine a new Python migration
with a security patch. `parse_value('1 / 2')` returns integer 0 on Python 2.7;
the unchanged code returns float 0.5 on Python 3.12. Thus this trial verifies
behavior and existing tests on **Python 2.7**, with **additional Python 3.12
syntax** only. It does not certify Python 3.12 behavioral compatibility.

Replacing eval with literal_eval changes the accepted expression language.
Dropping calls/names may be a desired security restriction but is a contract
change requiring review. Even literal_eval needs input/depth/resource bounds;
it is not a general safety guarantee for untrusted inputs:
https://docs.python.org/3.12/library/ast.html#ast.literal_eval .

## Actual baseline and regression evidence

All target code executed only inside the existing read-only, network-disabled,
non-root Docker sandbox, with 1 CPU, 256 MiB, 32 PIDs and bounded time/output.
Existing local Python 2.7, Python 3.12 and proofport-bandit:1.8.6 image IDs were
pinned. No images/dependencies were downloaded or unrelated services stopped.

* Actual **Python 2.7.18**: nine existing config golden inputs recorded; the
  existing **ConfigTests.test_load passed (1/1)**. The class/method/assertions
  are copied verbatim with narrowed imports; this is **not the full ten-test
  legacy_shop suite**. Test source and all sample files remain unchanged.
* Source syntax passed on Python 2.7.18 and Python 3.12.16.
* Cross-runtime diagnostic: **8/9** cases match on the original Python 3.12
  code; only `config.parse_6` differs (integer vs float division).
* Complete scoped Bandit scan confirmed the chosen eval finding.
* A separately labelled **authored diagnostic, not model output**, replaced
  eval with literal_eval on a staged copy. Real Docker checks: syntax passed on
  both runtimes, 1/1 ConfigTests passed, but only **8/9 golden cases** matched.
  `config.parse_6` changed from integer 0 to raw text `1 / 2`. Bandit warning
  disappeared, yet the engine assigned **needs_review**, rejected the change
  and verified the accepted working copy/original hashes were unchanged.
* No proposed working security patch or successful model fixture is supplied.
  Mock HTTP tests return unchanged eval code and fake verification outcomes;
  they test guards, not actual remediation. The authored regression is never
  loaded as a future model answer or fallback.

Retained user preparation:
`backend/.work/p84-security-afc0c284439542fa999c2d5a8b58999d/`.
It contains source copy, nine-case golden recording, existing test result,
two-runtime syntax/cross-runtime observations, contract probes, Bandit scan,
prepared.json, preparation.log, baseline-report.json/HTML and their receipt.

| Artifact | SHA-256 |
| --- | --- |
| Original config.py bytes | `e5b566143812fd3fc4bb7cfa8121ccb401e1ddd4d9b8f728a74bb8b91c84fc08` |
| Normalized model source binding | `9fd4014ae97d79a2b2b1313f8db175b493549e7047021f7e414dfb1b6fecac75` |
| Prepared manifest | `98853b02344b3e5047525cb7fffb5a0f07fa4a8cb59d2619fd3661f3996b9d54` |
| Baseline JSON report | `073ff0f90c3237f8dd5f2cf15b9d11d48e0031cd7e9de5aeef45ed1a16af72ef` |
| Preparation evidence | `5b85db21dd0ac5483adae6314b30f2502aa8ea7581629a923a2c68f985ff03fa` |

## Proposed paid flow — NOT executed

1. Validate ignored local credentials without printing them; repeat project/copy,
   selected finding, image ID, input, report/evidence and frozen budget checks.
2. Exclusively create an execution marker. One request to the already smoke-tested
   `muse-spark-1.3` receives the finding's minimal selected fields, source config.py,
   strict ModelPatch schema and security-only preservation/review instructions.
   Binding includes task=security, file, finding ID, source hash and runtime=2.7.
   No code from unrelated modules, credentials or golden outputs is sent initially.
3. Save the actual sanitized response/provenance/prompt hash. LLMFixGenerator
   feeds the same independent SecurityFixEngine staging/checking/policy path.
4. Check **Python 2.7 syntax + Python 3.12 syntax → nine Python 2.7 golden
   comparisons → the unchanged ConfigTests → Bandit rescan → original/working
   SHA-256 and evidence integrity → decision**. Retain every attempt/check/diff.
5. Only a verification failure may request a second, bounded proposal with previous
   model code and failed expected/actual observations. A passing candidate that
   only needs policy review does not spend a second call. Timeout, API/JSON/schema
   failure, unavailable model or exhausted budget stops without retry/fallback.
6. **B307 remains protected. No generated eval patch is automatically accepted or
   reported fixed**, even if finite checks pass and Bandit goes quiet. Changed
   behavior/insufficient proof means needs_review; failed syntax means fix_reverted.
   Rejected branches remain, and the working copy is kept/restored to baseline.
7. Export JSON/HTML, safe finish/token diagnostics, scans, proposal metadata,
   hashes and chained evidence. Verify receipts and originals independently.

The default SecurityFixEngine remains Python 3.12/offline, and its generic run()
still rejects live generation. New same-runtime checks and finding-bound live
verification are explicit per-instance options of the dedicated local trial.
The existing constant-shell allowlist and protected-eval review policy are not
expanded. Keys/env settings or a browser request cannot create live approval.

## Financial and response limits

* **At most two calls**, **USD 0.05** estimated cap, zero SDK/HTTP retries.
* **9,216 input allowance**, **3,072 completion tokens including reasoning**,
  **30-second timeout**, total reservation **24,576 tokens**.
* At configured Standard rates (USD 1.25/M input, USD 4.25/M output), maximum
  full reservation is **USD 0.024576 per call / USD 0.049152 total**.
  https://dev.meta.ai/docs/pricing-rate-limits . This is a local reservation/
  estimate, not a provider-side spending guarantee. Unknown charges after timeout
  cannot be undone; the marker prevents an accidental paid restart.
* Synthetic initial/repair context byte guards measured **4,658 / 5,975**, within
  9,216. This is offline serialization, not actual tokenizer/model usage. Larger
  candidates/feedback are rejected by the existing guard, not silently truncated.
* Only complete stop/strict JSON responses proceed. No partial-code recovery,
  untrusted host execution or hidden change to the selected language contract.

## Local commands

Free preparation (completed above):

```powershell
.venv/Scripts/python.exe -m backend.ai.first_security_live --prepare
```

Only **after a new explicit paid approval for this eval proposal trial**, execute
the prepared workspace once:

```powershell
.venv/Scripts/python.exe -m backend.ai.first_security_live --execute --acknowledge-paid-api --workspace backend/.work/p84-security-afc0c284439542fa999c2d5a8b58999d
```

Read-only baseline recheck, no model request:

```python
from pathlib import Path
from backend.ai import artifacts, first_security_live
assert artifacts.verify(Path("backend/.work/p84-security-afc0c284439542fa999c2d5a8b58999d"),
                        first_security_live.unchanged, stem="baseline-report")
```

## Actual tests

```text
pytest tests -q -m "not docker" --tb=short -p no:cacheprovider --basetemp=<unique ignored path>
507 passed, 54 deselected in 24.23s

PROOFPORT_DOCKER_TESTS=1 pytest tests/test_first_security_docker.py tests/test_first_php_live_docker.py -q --tb=short -p no:cacheprovider --basetemp=<unique ignored path>
2 passed in 23.47s
```

The Docker run covers the new security baseline, same-runtime verification,
literal-only mismatch/rescan/rollback and a PHP baseline regression. Its temporary
credentials are generated per test, avoiding a tracked literal that correctly
triggered the credential Git guard in an initial attempt. No protection was
bypassed and no genuine key was printed. Python/PHP fast regressions pass; no
heavy matrix, frontend change, merge, rebase, push or screenshot occurred.
