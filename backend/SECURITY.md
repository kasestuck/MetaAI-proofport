# Offline security verification (P2)

This is a tested offline verification/decision engine, **not a validated Meta AI
Security Fix product**. No API generation is enabled and no credits are needed.
Warnings are potential risks, not automatically confirmed vulnerabilities.

## Use with the supplied project

Use the existing Docker images and fixture migration setup from `README.md`:

```powershell
$env:LLM_MODE = 'mock'
$env:PROOFPORT_PIPELINE = 'fixtures'
$env:PROOFPORT_CASES_FILE = 'tests/fixtures/legacy_shop/cases.json'
$env:PROOFPORT_FIXTURE_FILE = 'tests/fixtures/legacy_shop/patches.json'
$env:PROOFPORT_SECURITY_FIXTURES = 'tests/fixtures/security/legacy_shop_fixes.json'
.\start.bat
```

POST the unchanged body `{"source_path":"samples/legacy_shop","max_iterations":1}`.
The new setting is server configuration, not an API request extension. With
security fixtures enabled, live/replay migration requests are refused before
SDK construction. No automatic fallback or paid model generation is allowed.
Without this setting the existing migration-only workflow remains available.

## Components and boundaries

- `core/security.py`: real Bandit adapter, recommendations, CWE, confidence,
  description and context. IDs fingerprint file/test/symbol/occurrence, so line
  movement alone does not change identity. Ambiguous patch locations cannot
  authorize an automatic change. The API Finding fields remain unchanged;
  richer data is internal and exported in reports.
- `security/models.py`: bounded, validated proposal schema: finding ID,
  explanation, proposed code, behavior impact, confidence, origin mode,
  disposition and compatibility review areas. Confidence never authorizes a fix.
- `security/providers.py`: source-hash-bound offline fixtures. The future
  `LLMFixGenerator` has a schema, request builder for `LLMClient` and response
  parser. `generate()` is deliberately disabled. Model responses cannot label
  themselves trusted fixtures; live/replay proposals are not accepted here.
- `security/policy.py`: independent compatibility checks and a deliberately
  narrow supported hardening rule, plus contextual subprocess triage.
- `security/engine.py`: staged candidate projects, actual Docker checks,
  rescan, decisions, atomic acceptance, rollback, hashes and attempt evidence.

The request builder accepts already-redacted source; it makes no request.
Prompt quality, model-generated fixes, real Meta responses, replay and model
failure handling must be validated in a separately authorized future stage.

## Transaction and evidence

Each proposal is evaluated in a separate candidate project outside both the
original and the accepted migration. Original paths, escaping links, tests and
non-Python patch targets are rejected. No writable host mount is exposed to
project execution. Only the existing Docker sandbox runs target Python.

The engine verifies a nonempty, passing baseline, then for each proposal:

1. Compile all project Python in Docker Python 3.12.
2. Run the recorded golden inputs and compare exact IDs/results/output.
3. Run unchanged existing tests, checking test IDs, counts and pass statuses.
4. Rescan with Bandit, including new findings and severity escalation.
5. Recheck original SHA-256 hashes and accepted-copy consistency.
6. Evaluate compatibility and supported-policy constraints independently of
   the provider's explanation, confidence and scanner warning count.
7. Atomically accept only an approved file or retain the old accepted copy.

Invalid syntax skips dynamic execution with explicit `ran=false`, not fictional
results; a real scanner parse-error result is still recorded. Behavioral
failures never become success because a scanner warning disappeared. Review
proposals may be tested, but their staging changes are never committed.

After all proposals, the engine reruns accepted-project checks and the scanner.
Final validation or evidence-integrity failure rolls back committed security
changes to the previously verified migration. The broken log is not rewritten
to make its chain appear intact. A successful security-pass status means the
accepted project passed the recorded checks, **not** that all proposals were
accepted or all vulnerabilities were removed.

Each real run adds `backend/.work/<run_id>/security_attempts/`: per-attempt
candidate copies, `attempt.json` and a final `security_report.json`. The main
hash-chained evidence log remains append-only. Reports contain before/after
findings, recommendations, decisions, tests, reasons, redacted code diffs,
original/accepted project hashes, isolation and processing mode. Staging source
copies are private local artifacts and can contain original embedded values;
they are git-ignored. Detected secret literal values and their encoded forms
are redacted from JSON/HTML diffs and results, not printed as source snippets.

## Decision meanings

| Status | Meaning |
| --- | --- |
| `open` | No supported proposal or insufficient independent triage evidence; no confirmed-vulnerability claim. |
| `fixed` | A supported hardening transformation passed real checks and rescan. This resolves the specific finding in recorded scope, not universal security. |
| `false_positive` | Specific constant-argv/non-shell context independently checked with passing behavior tests; the raw advisory remains visible. |
| `needs_review` | Behavioral/API/configuration/crypto/data-format impact or unsupported transformation; candidate is not accepted. |
| `fix_reverted` | Syntax, behavior, scan or verification failure, or a later validation/integrity failure; changes are not retained. |

Automatic hardening currently supports only an exact `/usr/bin/printf` constant-command
`subprocess.check_output(..., shell=True)` to identical literal absolute argv
with `shell=False`, with all other AST nodes unchanged. Literal commands are
not assumed harmless: interpreters such as `/bin/sh -c` are outside this policy.
Only fixed alphanumeric/underscore/hyphen printf arguments are accepted. No shell metacharacters,
expansions, arbitrary arguments or code changes are allowed by this rule. A new
LOW B603 advisory in that exact verified context is explicitly triaged and
retained; other new/escalated findings prevent acceptance. There are no broad
automatic eval, query, credential, serialization or crypto transformations.

## Actual legacy_shop outcome and limitations

The original 90 cases and 10 tests are retained, including the arithmetic eval
and SQL injection behavior. Four authored proposals are exercised:

- Eval to literal-only evaluation: changes the supported expression language;
  the arithmetic golden case fails. `needs_review`.
- SQL parameters: the recorded injection input returns a different result.
  `needs_review`, even though blocking that input is desirable security policy.
- `cp` argument list: nominal golden inputs pass, but the existing unrestricted
  public API exposes shell word splitting and expansion semantics. Passing a
  sample is insufficient to approve that contract change. `needs_review`.
- Required environment-backed `SECRET_KEY`: changes configuration and may
  change password hashes; without new configuration imports/cases fail.
  `needs_review`. The executor does not inject a secret to hide this failure.

No legacy_shop security change is automatically accepted. Its eight raw target
warnings remain. Five items need review: these four plus the existing MD5 item.
The separate constant-command project under `tests/fixtures/security_subject/`
demonstrates a genuinely accepted, behavior-preserving hardening fixture,
contextual triage and rollback paths. It is not a replacement legacy_shop or
evidence of AI-generated remediation. Its fixture tests run only inside Docker;
host pytest excludes the fixture directory from collection.

The initial Python 2 scan still has four parse failures; report it as partial.
The migrated Python 3 scan has no parse errors. Finite behavior cases do not
prove all possible inputs, filesystem formats or full security. Bandit coverage
is limited and contextual triage is intentionally narrow. Tests should not be
weakened or removed to force a security fix to pass.

The conservative choices follow Python's documentation for
[literal evaluation and its limits](https://docs.python.org/3.12/library/ast.html#ast.literal_eval),
[subprocess security](https://docs.python.org/3.12/library/subprocess.html#security-considerations)
and [SQL parameter binding](https://docs.python.org/3.12/library/sqlite3.html#sqlite3-placeholders).

## Run checks

```powershell
$env:PROOFPORT_DOCKER_TESTS = '1'
.venv/Scripts/python.exe -m pytest tests -q
```

Integration tests execute the original/candidate code, scanner, failure/rollback
and physical log-tampering scenarios in real Docker. API/model methods are
forbidden by test guards in the offline security tests. No live AI Security Fix
readiness is claimed until genuine Meta integration is separately tested.
