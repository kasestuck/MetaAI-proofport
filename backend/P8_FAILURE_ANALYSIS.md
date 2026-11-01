# P8.1 — failed live mathutils migration: diagnosis and offline improvements

Work is on `integration/p4`. This stage makes **zero Meta API calls** and spends
no credits. Original sample files, frontend, public API and the failed P8 run's
artifacts are unchanged. The failed live result remains failed; no successful
AI repair or migration is claimed.

## Evidence and exact limits of the diagnosis

The P8 report/evidence/artifact receipts were independently verified before
analysis and after the offline reproduction. Original report SHA-256:
`14d0dfed6aa9d37b27e39686a6820d278db02e73c1f54c083b249099b9f2bea5`.

P8 made two genuine requests to `muse-spark-1.3`: 2,181 input / 2,576 completion
tokens, estimated USD 0.01367425. The first candidate compiled and passed three
MathTests, but only 26/31 golden comparisons. The second request reported 1,275
input / **1,536 completion tokens**, exactly its 1,536 output cap. The client
stopped and rolled back; no third request or fallback was sent.

What is established:

* `model_incomplete_response` in the P8 client was raised only when the SDK's
  `choice.finish_reason != "stop"`. The HTTP envelope and token usage had already
  been parsed and recorded. The candidate-content JSON and ModelPatch parsers
  had **not** been reached. This was not a ModelPatch/code-extraction failure.
* The recorded completion count reached the cap. Provider truncation is the
  leading explanation, not a proven historical finish reason.
* P8 did not retain the actual finish_reason, reasoning-token breakdown or second
  content body. `length`, content filtering and tool-related termination shared
  one error code. We cannot recover the exact reason, prove the second content
  was cut mid-JSON, establish JSON completeness or exclude an SDK finish-reason
  discrepancy retrospectively. No such missing data is invented.

Meta documents `length` as output-limit termination, and `max_completion_tokens`
counts visible **and reasoning** tokens. The old records cannot distinguish them.
Source: https://dev.meta.ai/docs/api-reference/chat-completions/schemas .

## The five reproduced semantic mismatches

| Case | Actual Python 2.7 behavior | Failed Python 3.12 candidate | Cause |
| --- | --- | --- | --- |
| mean_float `[1.5, 2.0]` | float `1.75` | float `1.0` | `sum(values) / len(values)` changed unconditionally to `//` |
| median_float `[1.5, 2.0]` | float `1.75` | float `1.0` | even-length average changed unconditionally to `//` |
| round_1 `-2.5` | int `-3` | int `-2` | `floor(x + 0.5)` handles negative ties differently |
| round_3 `-0.5` | int `-1` | int `0` | same negative-half rounding error |
| tiers_2 `([1,2,5.9], 2.5)` | keys `1.0, 2.0, 5.0` | keys `0.0, 5.0` | float divisor should use true division; floor merged buckets |

Python 2 traditional division floors integer/long pairs, including negatives,
but uses floating-point division when either built-in numeric operand is float.
The model's blanket `//` substitution preserved the integer tests and broke
float inputs. Python 2 `round(x)` ties are away from zero; Python 3's builtin uses
ties to even. The model instead used a positive-half formula that failed for
negatives. The original measured behavior is authoritative even where a
docstring/bucket description suggests a different intended algorithm.

References: https://docs.python.org/2/reference/expressions.html#binary-arithmetic-operations ,
https://docs.python.org/2/library/functions.html#round ,
https://docs.python.org/3.12/library/functions.html#round .

## Changes

`ai/feedback.py` builds explicit bounded repair feedback from real failed
comparisons: case IDs, original calls/arguments, typed expected/actual results,
syntax observations and failed existing-test IDs. Only failing cases are sent.
Repeated module/ID fields and empty output channels are omitted to conserve
context; nonempty output and typed values are preserved. The helper rejects
oversized feedback (16 cases / 16 KiB); LLMClient still applies the tighter
per-request input guard. No silent truncation or budget increase is used.

The local P8 runner explicitly enables this feedback. Generic Python/PHP jobs
retain their previous no-expected-values default. Existing private-context
redaction and the credential-in-prompt guard cover the expanded context.

The separate Python repair prompt includes the original source, previous
candidate and supplied observations. It explains mixed integer/float division,
negative ties, precision and API preservation; forbids test edits and hardcoded
answers; requests a complete single-file JSON patch with concise explanation.
The first translation still uses the normal Python prompt. Security repair and
public live capabilities are not enabled or changed.

`llm/client.py` and `CallAttempt` now retain safe diagnostics in evidence/reports:
allowlisted original wire finish reason; SDK/wire agreement; completion and
optional validated reasoning-token counts; output cap/reached flag; content hash
and byte length; strict JSON-object-valid flag. Unknown provider strings are not
logged. Raw headers/content/credentials are not retained in diagnostics.

The parser rejects a non-stop finish reason **even if its JSON is complete**,
and rejects incomplete/duplicate/nonfinite/non-object JSON even with `stop`.
An exact token count alone does not reject an otherwise complete `stop` response.
SDK/wire content or finish-reason disagreements also stop the session. Strict
ModelPatch binding and complete-code Docker checks remain. No partial JSON repair,
code splicing, auto-continuation or paid retry was added. Report exports now also
contain safe `model_attempts`, including a failed second response's diagnostics.

## Offline verification and provenance

The actual **failed** first model candidate is curated as a regression input in
`tests/fixtures/p8_failed_candidate/`, with original and normalized hashes and
prompt provenance. It is not a fix, a successful translation or a runtime fallback.
No corrected candidate is provided. Mock/replay prompt tests deliberately return
the still-incorrect previous code: they validate transport/context, not behavior.

A real Docker regression freshly recorded all 31 cases in Python 2.7.18 and
executed the saved bad candidate in Python 3.12.16. It reproduced **exactly the
same five failures**, 26/31 matches and 3/3 scoped MathTests per interpreter.
Original hashes and evidence chain passed. No PHP/Docker stress matrix or image
downloads were run. Output was retained in a unique ignored backend/.tmp folder.

The compact full repair context for the actual five cases measured **7,713**
bytes including the existing guard's framing allowance, within the unchanged
7,936 input allowance. This size check used only a local responder; it does not
predict real model quality or token usage.

Tests cover expected/actual propagation, private-value redaction, generic-adapter
privacy, hash-bound replay, oversize rejection, valid JSON with `length`, partial
JSON with `stop`, filtering, exact output-limit success, unknown finish reasons,
SDK/wire mismatch, reasoning metadata and existing rollback/budget/evidence guards.

Final actual outputs (each run used a distinct retained backend/.tmp directory):

```text
pytest tests -q -m "not docker" --tb=short -p no:cacheprovider --basetemp=<unique>
467 passed, 52 deselected in 13.47s

PROOFPORT_DOCKER_TESTS=1 pytest tests/test_p8_regression_docker.py -q --tb=short -p no:cacheprovider --basetemp=<unique>
1 passed in 6.03s
```

An older simple SDK test double supplied only usage in its fake raw response;
it was updated to include the actual choices/message/finish_reason envelope
required by the new consistency check. No production check was weakened.

## Recommended next live profile — not enabled or executed

Keep `muse-spark-1.3`, minimal reasoning, zero HTTP retries, 30-second timeout,
read-only/network-disabled Docker and the same 31 cases / three existing tests.
Request separate approval for a **new** workspace; never relaunch the failed one.

Consider **two calls**, 9,216 input allowance and 3,072 completion tokens per
call, 24,576 total reservation and an unchanged USD **0.05** cap. At configured
Standard rates USD 1.25/M input and 4.25/M output, two full reservations total
USD **0.049152**. This doubles completion room (including reasoning), leaving
space for the measured detailed feedback without increasing the dollar cap.
It trades a third iteration for more output capacity. Current runtime defaults
remain at the old bounds; switching the bounded profile requires review and
separate paid approval. The local estimate is not a provider billing guarantee.

Only a separately approved genuine model run followed by passing unchanged
Docker comparisons/tests can demonstrate that the migration problem is fixed.
