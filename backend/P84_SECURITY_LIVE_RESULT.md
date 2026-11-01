# P8.4 — real Meta eval proposal verified and rejected pending review

Explicitly authorized live trial on `integration/p4` for finding
`B307-501c959a03faf42afa68fc25`, `legacy_shop/config.py:7`.
Bounds: two API requests, estimated USD 0.05, 9,216 input allowance / 3,072
completion tokens, 30-second timeout, no retry after API error/timeout, no fallback.
Original sources and the accepted working copy remain unchanged.

## Actual outcome

**Finding: needs_review. No patch accepted. No vulnerability-remediation claim.**
The model produced a genuine proposal, but dynamic verification failed. It was
retained on a rejected branch and rolled back. A second generation request was
blocked locally by input_budget_exceeded before HTTP; no limit was increased.

* Actual provider/model: Meta Model API, `muse-spark-1.3`, **one API request**.
* Tokens: **1,069 input / 2,803 completion**, total **3,872**. Completion usage
  includes **459 reasoning tokens**, not an additional separate token charge.
* Estimated cost **USD 0.013249**, below USD 0.05. One reservation consumed:
  USD 0.024576. Usage is complete; estimates use the configured Standard rates
  and are not an independently retrieved provider invoice.
* Original finish_reason **stop**, matching the SDK; JSON complete and valid.
  Output cap not reached (2,803 < 3,072); structured patch bindings accepted.
* Syntax: passed **Python 2.7** and additional **Python 3.12** Docker checks.
* Dynamic behavior on **Python 2.7.18: 5/9 golden cases matched**.
* Existing **ConfigTests: 0/1 passed**. The unchanged test failed because
  `open_days` became raw text; its first element was `[` rather than `mon`.
* Bandit rescan completed without parse errors. B307 disappeared from the
  candidate, but a new **B110 / CWE-703, LOW severity, HIGH confidence** warning
  appeared for try/except/pass in `_init_ops`. Both are scanner risk labels,
  not independently confirmed exploits.
* Full original inventory, working-copy hashes, report receipts, all retained
  artifact hashes and evidence chain were independently verified after execution.
  The earlier baseline reports remain valid and unchanged.

## What Meta proposed

The proposal replaces eval with a bounded AST-whitelist evaluator for literals,
containers, arithmetic, comparisons and boolean/unary expressions. It proposes
length/node/depth/container/operation limits and keeps the raw-string fallback.
It deliberately rejects dynamic calls, names, imports, lambdas and comprehensions.
The model honestly declared **behavior_impact=changes** and API/configuration/
data_format review areas. Resource robustness and full expression-language
compatibility are not established by these finite checks.

The four observed mismatches:

| Case | Source result | Candidate result |
| --- | --- | --- |
| config.parse_1 | list `[1, 2]` | raw string `[1, 2]` |
| config.parse_3 | bool False | raw string `False` |
| config.parse_6 | integer 0 for `1 / 2` | raw string `1 / 2` |
| config.load | open_days is a list | open_days is raw list text |

Static inspection found unguarded references to `ast.Bytes`, `ast.NameConstant`
and `ast.Constant` before the list/boolean/arithmetic branches. A separate,
read-only Docker stdlib diagnostic confirmed all three classes are absent in
Python 2.7.18 (`ast.Num` and `ast.Str` exist). For these inputs the missing-class
lookup raises and the broad exception handler returns raw text. This explains
the observed scalar-vs-container split; no generated code ran on Windows.

Even correcting this bug would not authorize acceptance: restricting the old
eval expression language changes its contract and B307 remains protected by the
independent manual-review policy. Warning disappearance alone is insufficient.

## Why no second paid request occurred

The first candidate was significantly longer than the preparation's synthetic
previous-candidate example. The reconstructed retry request measured **16,149
UTF-8 bytes including the existing guard framing allowance**, above the configured
9,216 allowance in the client's conservative byte-based input check.

This is a **local conservative guard**, not an observed provider input-token
count. The second request never reached the provider, consumed no second
reservation and has no provider token usage. The session stopped with
`input_budget_exceeded`; the original exclusive execution marker remains.
No automatic retry, fixture answer, hidden context truncation, budget change or
paid continuation was attempted.

## Retained proof

Ignored workspace:

`backend/.work/p84-security-afc0c284439542fa999c2d5a8b58999d/`

Includes original baseline, actual response_01.json, finding/source binding,
prompt hash, safe finish/token diagnostics, staged candidate and attempt.json
under attempts/54fe80fd038b450b986c9d9550b55718/, checks/diff/Bandit findings,
restored working/, evidence.log, report.json, report.html and report-receipt.json.
Credentials, generated responses/code and runtime evidence are not committed.

| Artifact | SHA-256 |
| --- | --- |
| Prompt | `2bea3cdff30363f647b456e53993e3a488b54c774651465846322f8f44a1e24c` |
| Model response content | `5c58f7214e56e4f8943bac3b1048653e016b4a217e4710cc62f723639d6b8244` |
| Proposed code, normalized UTF-8 | `0ccb6f09923e380b417bca13b527595055082410dc28132f996db68f706d3850` |
| Retained candidate file bytes | `88622150ae278b7462025aba00516237a0ec8f9260d1d620bce0f6a43e7df3c1` |
| JSON report | `f7670a32d20506c452e0de09ac2ec8bc2d36e037a701cd3d65b3382ead3bb612` |
| HTML report | `d204f752113fed5e99015531439be7563302a14a837a0f4563a794e044aa2610` |
| Evidence log | `8f63e5869c85b3f43aed0935fd4ed89cbc8765fa257c133c673a0ff5b3922694` |

Normalized code and Windows file-byte hashes differ because of newline encoding;
both are retained explicitly. No original file was rewritten.

Read-only recheck, no model request:

```python
from pathlib import Path
from backend.ai import artifacts, first_security_live
workspace = Path("backend/.work/p84-security-afc0c284439542fa999c2d5a8b58999d")
assert artifacts.verify(workspace, first_security_live.unchanged)
assert artifacts.verify(workspace, first_security_live.unchanged, stem="baseline-report")
```

No runtime implementation changed during this execution. The preparation's
507 passing fast tests were not repeated unnecessarily; actual syntax/golden/
existing-test/Bandit checks ran in this live job. No full legacy_shop suite,
automatic eval acceptance, frontend change, merge, rebase, push, screenshot,
image pull or unrelated process stop occurred. Any future model request needs
new authorization; this run is stopped and its original evidence is preserved.
