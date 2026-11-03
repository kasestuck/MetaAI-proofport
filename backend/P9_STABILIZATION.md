# P9: stabilization audit and verified limits

Branch: `integration/p4`. Starting commit: `da55dda`.
No Meta API calls, new model tokens or API charges were made during P9.
Original Python/PHP source files and fixture data were not edited. No image
downloads, merge, rebase, push, screenshots or unrelated service stops were used.

## Confirmed defects and corrections

No P0 defect was established in the exercised paths. This is a bounded audit,
not a claim that no P0 or other undiscovered defect exists.

| Priority | Confirmed problem | Correction and regression evidence |
| --- | --- | --- |
| P1 | P8.4 repair repeated the full previous evaluator, schema and observations; local input guard rejected it before sending. | Compact observations into typed deltas and a compact schema. If still too large, replace only the previous candidate with explicitly labelled, hashed diagnostic excerpts. Keep full original source and require complete replacement output. Hard limit remains unchanged. Synthetic and retained real-response tests cover this path. |
| P1 | A security request described migration source/target versions even when verifying an already migrated file. | Security context uses the actual verification runtime on both sides. Protected P8.4 explicitly uses 2.7; ordinary Python/PHP security verification uses 3.12/8.3. |
| P1 | Successful compilation did not reveal unavailable Python 2.7 AST APIs. | Trusted Docker-only direct AST-reference inspection is an additional check. Missing unguarded attributes block dynamic acceptance. Syntax and runtime-API results remain separate. |
| P1 | Local input/budget rejection happened outside the client's stop handling. | Mark client stopped and retain safe rejection/size diagnostics without inventing an API attempt, usage or spend. |
| P1 | Direct Python security attempts bypassed secret-value initialization performed by the outer engine. | Initialize redaction from all scanner findings in the affected file before creating diffs/results. Test checks returned and saved records. |
| P1 | PHP XSS detection ignored unsafe output if another operand contained an escaping call. | Only treat an entire escaped output expression as escaped. Concatenation and multiple-operand regression cases retain warnings. This is still a lexical heuristic. |
| P1 | Generated PHP proposals hashed normalized text instead of the actual source bytes. | Bind proposals to raw bytes; the narrowly supported constant-command policy tolerates CRLF in its exact known transformation. Original hashes still use actual bytes. |
| P1 | PHP final scan/verification failure could leave promoted fixes and `verified=true`. | Final syntax/tests/golden checks, scan coverage, accepted-copy hashes, original hashes and evidence must all pass. Failure returns the untouched baseline pointer and reverts decisions and saved attempt records. Both verification runtimes can be required explicitly. |
| P1 | Replay sorted and deduplicated evidence, allowing invalid supplied order/duplicates to become green. | Preserve saved evidence exactly. Reject malformed entries; report duplicate/reordered chains as broken. Polling deduplication is separate; final live reports must still match final events exactly. |
| P1 | Local API accepted attacker-controlled Host/foreign browser Origin. | Restrict Host to local development hosts and reject cross-origin `/api/` requests; add `nosniff`. Same-origin requests and CLI requests without Origin keep their contracts. This is local-only hardening, not remote authentication. |
| P2 | Catalog advertised linked profiles as available although preflight rejected them. | Catalog uses the same profile path policy as preflight. |
| P2 | Excessively nested replay JSON escaped the safe replay error boundary. | Convert parser recursion failure into a safe `model_replay_unavailable`, with no response or network fallback. |

## P8.4 diagnosis and remaining decision

The retained genuine proposal used `ast.Bytes` and `ast.NameConstant`, absent in
Python 2.7. Its broad catch returned raw strings, explaining 5/9 golden matches
and 0/1 ConfigTests despite successful compilation. Bandit B307 disappeared but
B110 appeared; warnings were not suppressed or automatically dismissed.

The first response completed; the second request was rejected locally by the
16,149-unit input estimate against 9,216, not truncated by Meta or misparsed.
The original report/evidence were kept unchanged and verified again.

The improved prompt explicitly covers Python 2 AST classes, Name nodes for
True/False/None, `long`, integer division, public signatures and raw-string
fallback. It warns that unrestricted names/calls cannot be removed without a
contract decision. It forbids hiding eval and requires honest changed/unknown
behavior declarations and review of parser resource limits.

Using the actual retained response and failing observations, the new repair
context measured **8,115 UTF-8 bytes + 256 framing = 8,371 / 9,216**. This is a
conservative local unit count, not an official Meta token count. The recorded
candidate is also rejected by the new Python 2.7 Docker AST check. No new model
answer or corrected live eval patch was generated or claimed.

Future approved batches retain: two calls, 9,216 input / 3,072 output allowance,
30-second timeout, $0.05 cap and maximum reservation $0.049152 at the previously
configured rates. SDK retries remain zero. Transport/API/incomplete-output
errors stop; only verified code failures can request another iteration within
an explicitly approved batch. No hidden fixture fallback exists.

**Eval remains `needs_review`.** A restricted expression language intentionally
changes the old contract. Passing nine inputs and one test cannot prove arbitrary
eval equivalence, complete attack resistance or resistance to resource exhaustion.

## Python findings: actual review

One full explicitly labelled fixture migration supplied a Python 3.12 verification
copy: **90/90 golden matches, 10/10 original tests on 2.7 and 10/10 on 3.12**.
Every one of its eight Bandit findings received a separate retained attempt,
syntax check, 90-case comparison, existing tests, rescan and original-hash check.
No candidate was promoted: **8 before / 8 after, all eight `needs_review`**.

| Finding | Context and proposed direction | Actual offline diagnostic result |
| --- | --- | --- |
| B307 / CWE-78 | Config expression parsing is callable, but external input trust is unknown. Review and restrict the accepted expression contract. | Literal-only parsing changed golden behavior; rejected. |
| B403 / CWE-502 | Pickle import is an advisory; actual load operation is reviewed separately. | Unchanged-context checks passed; import alone is insufficient to establish or dismiss exploitability. |
| B404 / CWE-78 | Subprocess import is an advisory; this file also has a shell call. | Unchanged-context checks passed; no blanket false-positive dismissal. |
| B105 / CWE-259 | Demo literal is not evidence of a real deployed credential. Real credentials require configuration/rotation review. | Externalizing the value changed golden behavior; rejected, diff/observations redacted. |
| B324 / CWE-327 | MD5 output format is part of recorded behavior. Design a password-hash/data migration rather than silently changing it. | SHA-256 negative diagnostic changed golden output; rejected. SHA-256 alone is not a proposed production password KDF. |
| B301 / CWE-502 | Snapshot reader consumes serialized input; trust/reachability is unproved. Review allowed types and stored-data format. | JSON negative diagnostic broke pickle behavior; rejected. |
| B608 / CWE-89 | Formatted SQL sink accepts caller input; production DB exposure is unproved. Review parameterization and intentionally accepted inputs. | Parameterized-query fixture changed recorded behavior; rejected. |
| B602 / CWE-78 | Archive command uses caller-controlled shell arguments. Review literal executable, argument semantics and allowed inputs. | Shell removal passed finite cases/tests but lacks the narrow independently verified constant-argument policy; kept for review. |

Bandit on the original Python 2 project remains **partial**, with four parse
errors. A clean original-project security verdict must not be shown. The migrated
verification copy's scan had no parse errors. No exploitability was confirmed.

## PHP findings: actual review

The retained genuine P8.3 candidate was copied, not regenerated from a patch.
All ten findings were reviewed with explicitly authored offline proposals, never
labelled Meta output. Each candidate was checked in **both 7.4.33 and 8.3.36**:
syntax, 22 golden cases and nine existing tests, then lexical rescan and hashes.
Final accepted copy passed both runtimes again: **10 before / 9 after**.

| Finding | Decision and limitations |
| --- | --- |
| Constant command in `commands.php` | One narrow exact allowlisted shell-to-argv hardening was accepted after all checks. This does not establish an original exploitable command injection. |
| XSS in `math.php` | `needs_review`: output consumer/HTML context unknown; unchanged-code diagnostic passed, warning retained. |
| SQL construction | `needs_review`: a numeric-input restriction passed finite cases but changes accepted inputs and is not parameterization. Real DB adapter/contract needs review. |
| Dynamic HTML output | `needs_review`: escaping passed finite cases but changes rendered output contract; coverage is insufficient. |
| Dynamic command execution | `needs_review`: disabling the command changed golden results. |
| Unserialization | `needs_review`: allowed-class restriction passed finite cases but object/data contracts remain untested; sink warning retained. |
| Filesystem path access | `needs_review`: basename restriction passed finite cases but changes nested-path support; confinement still needs design. |
| Embedded demo secret | `needs_review`: no real credential was established. No secret-source/configuration change was silently applied. |
| Weak password hash | `needs_review`: SHA-256 negative diagnostic failed golden and existing tests; it is not a production password-hash recommendation. |
| File upload | `needs_review`: source/size/extension guard passed finite cases, but positive upload, content validation and destination policy are unverified; warning retained. |

PHP scanning remains limited lexical analysis, without interprocedural taint
analysis, exploit confirmation or a claim of complete vulnerability coverage.
The broader review leaves nine findings for review. The standard three-proposal
fixture demo separately reports one fixed, one needs-review and one syntax-rejected
attempt; it does not attempt all ten findings.

## Actual test and integration results

Fast backend command (run from repository root):

```powershell
$p9base = 'backend/.tmp/p9-fast-' + [guid]::NewGuid().ToString('N').Substring(0,8)
.venv/Scripts/python.exe -m pytest tests -q -m "not docker" --basetemp=$p9base
node --test frontend/tests/*.test.cjs
```

Use a fresh short retained path for each pytest invocation; Windows has path
length limits. Project tests under demo directories execute only in Docker.

- Final fast backend: **519 passed, 56 deselected**.
- Frontend: **69 passed, 0 failed**. All frontend JavaScript syntax checks passed.
- Selected Docker regressions: **9 passed** across four bounded invocations:
  two AST/P8.4 tests; PHP migration proof + PHP isolation; three mock/replay AI
  orchestration tests + Python isolation + own-container timeout cleanup.

Actual final pytest summary: `519 passed, 56 deselected in 25.44s`.
Selected Docker summaries: `1 passed in 3.83s`, `1 passed in 2.18s`,
`2 passed in 22.89s`, `5 passed in 61.28s`. These are separate selected runs,
not a claim that all 56 Docker matrix cases were executed.

Additional real end-to-end results:

- Python migration browser/API: **90/90**, **10 original + 10 target tests**.
- Retained genuine P8.2 candidate: **31/31**, **3/3 MathTests**, zero new calls.
- Retained genuine P8.3 candidate: **22/22**, **9/9**, both PHP runtimes, zero calls.
- Real Python compatibility **3.12.16 → 3.13.18**: two cases + two tests passed.
- Real browser PHP migration/audit/compatibility and Python simulation: passed.
  Original unmodified PHP legacy syntax correctly fails 8.3 compatibility, with
  tests/behavior marked not verified. The copied migrated candidate passes.
- Real browser runs had **zero JavaScript exceptions and zero external requests**.
  No screenshots, video or trace recording was enabled.

Browser checks exercised health, capabilities, projects/resolve, version choices,
profiles, blocked preflight, HTTP 202, idempotency, busy, finalizing, early report
409, old endpoints, JSON/HTML, evidence and unchanged original hashes. They used
installed Chrome against `127.0.0.1:8765`. Only the opt-in probe adds a documented
two-second finalization delay; actual finalizer/checks/results are unchanged.

Initial diagnostic failures were not counted as passes: unrestricted root pytest
collected Docker-only demo tests and failed collection; one unit double lacked
the newly required final verification call and was corrected; the first PHP
browser attempt correctly blocked an outdated proof receipt. The receipt was
renewed through actual Docker proof before the successful browser rerun. No
capability or test result was fabricated to bypass these checks.

## Retained evidence and reproducibility

Local generated artifacts are ignored, not committed or deleted:

- Full review: `backend/.work/p9-review-388918bf6b7f4bedb732c78659b22547/`.
  `review.json`, sealed `audit-report.json` / `audit-report.html`,
  `audit-receipt.json`, separate Python/PHP evidence logs and all rejected copies.
- Python full-fixture baseline: `backend/.work/p9-python-cc6d6ca01d2545818ba1c61c4a1b034c/`.
- Renewed PHP proof: `backend/.work/php-run-a0d8d44bc73d4d1582775a6b00de78cf/`.
- Real browser Python reports: `backend/.tmp/p43-real-2026-11-01T19-29-43-780Z/`.
- P8.4 context metric: under the retained `backend/.tmp/p9-p84-*` test directory.

`python -m backend.diagnostics.p9` deliberately repeats the owned-demo review in
fresh working directories using installed Docker images. It blocks model client
construction/completion explicitly. Do not run it as an ordinary fast test.
Current launch instructions are in the root README; the PHP browser probe is
`frontend/tests/php.browser.integration.cjs`. The historical P9 startup command was:

```powershell
.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8765
```

Choose an unused loopback port; never stop another service to obtain it. Live
generation remains unavailable through the public control plane.

## Outstanding risks and functionality limits

- Eval contract, dynamic commands, DB inputs, serialization, stored hashes,
  credentials and uploads need application-owner policy and more coverage.
- No new live repair was tested. P9 improves request construction and verification;
  it does not prove the next Meta proposal will be acceptable.
- Local byte/framing guard is not an official tokenizer. Reservation is a client
  estimate, not an enforceable provider-side billing guarantee. API uncertainty
  never triggers automatic paid retries.
- AST reference inspection is deliberately limited: direct ast references and
  simple hasattr branches. It is neither complete runtime API analysis nor a
  substitute for executing golden cases and tests.
- Loopback Host/Origin restrictions intentionally exclude arbitrary hostnames,
  reverse proxies and remote deployment. Authentication/authorization and durable
  multi-worker jobs are not implemented. Run/idempotency history is in memory.
- Hash chains and local receipts establish local consistency, not externally
  signed provenance or protection from an administrator rewriting all artifacts.
- Normal Docker resource/network/read-only restrictions and owned-container
  cleanup were verified. Daemon failure/crash fault recovery was not exhaustively
  tested; Docker shares its host kernel.
- Unqualified root `pytest` is not a supported command: it can collect original
  demo tests outside the container. Always use `pytest tests ...`; no demo files
  or root-level test configuration were edited in this milestone.
- No stress matrix, dependency-installation matrix or exhaustive scanner coverage
  was run. Verified runtimes here: Python 2.7.18/3.12.16 (migration), Python
  3.13.18 (limited compatibility), PHP 7.4.33/8.3.36. Other versions/pairs are
  not promoted by this audit.

The hackathon status is a verified offline/replay pipeline with retained genuine
module migrations and unresolved security policy decisions, not "all secure" or
a newly verified live AI Security Fix.

## Local change sets

- `a5abcdc`: bounded model repair context/diagnostics, Python runtime guard and
  redaction, PHP scanner/transaction checks, local API boundary and regressions.
- `b321283`: evidence-preserving frontend replay and three regressions; no design change.
- The following documentation/diagnostic commit contains this audit and the
  repeatable authored offline review command. Inspect the complete local range
  using `git log --oneline da55dda..HEAD`. No source branch was merged or pushed.
