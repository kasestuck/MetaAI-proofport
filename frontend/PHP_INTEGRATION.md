# P6.5 — Python / PHP console integration

Implemented in `integration/p4` against the actual P6.2/P6.3 backend contract:
`backend/PHP_OFFLINE.md`, RunSpec, and live local capabilities/projects responses.
Backend baseline: `3cddb71`, `0e8e157`, `f1dc330`. Only frontend and its
documentation changed. No build step, browser runtime dependencies, CDN, Meta
requests, backend edits, sample edits or new endpoints were introduced.

## Using the interface

Open the local backend in the browser, refresh scripts, then choose **Migration →
Run control → Project language**. Python remains the default. PHP can be selected
to inspect readiness even when unavailable; the reason is displayed and Start
remains blocked. Capability errors do not silently switch language or use the
legacy API. Only capabilities HTTP 404 selects the original Python legacy form.

1. Select Python or PHP. Registered projects are filtered by their server
   language. Unknown/mixed projects are not silently assigned to PHP. Older
   Python-only catalogs without language metadata retain their previous behavior.
2. Choose an offered operation. PHP uses `languages.php.supported_operations`
   and its operation policy, never the root Python matrix or image presence alone.
3. Choose versions and server-bound profiles. Migration/compatibility version
   pairs also require configured, available, verified runtimes with correct roles.
   Registering a custom project refreshes the catalog and does not invent profiles.
4. Click **Check readiness**, then **Start run**. HTTP 200 with `can_start: false`
   blocks launch; backend errors are shown. Any edit, including language, clears
   preflight. A late reply cannot approve a changed form.
5. Follow the monitor, Security, Compatibility and Evidence tabs. Finalizing,
   report retrieval and browser evidence-chain verification remain separate.

The currently verified backend exposes these PHP policies (documentation, not
hardcoded availability):

| Operation | Input | Mode / requirement |
| --- | --- | --- |
| Migration | PHP 7.4 → 8.3 | offline_fixtures, matching fixture + golden profiles |
| Security Audit | source label 7.4 or 8.3 | offline, limited static PHP rules, no project execution |
| Compatibility Check | PHP 7.4 → 8.3 | offline, explicit syntax/tests/behavior level |

Audit source version is an operator label, not interpreter detection or execution
proof. When the backend still lists static audit as ready, it remains selectable
without Docker or Bandit. Dynamic operations stay blocked without their runtimes.
PHP simulation and live generation are not offered.

For the owned demo select the returned `php_shop` project. Its profiles are
`php_shop_74_83`, `php_shop_golden` and optional `php_shop_security`, all read from
the server catalog. The **Optional security fixture checks · not AI** selector
defaults to None; checking proposals requires an explicit choice. It is a setting
on the existing migration endpoint, not a new AI Security Fix action.

The PHP source demo contains legacy syntax: a compatibility check of the
unchanged project on 8.3 is expected to fail. A successful fixture migration
verifies the translated copy; it does not make the original source compatible.
The UI cannot register the backend's private `.work/` copies as project paths.

## Requests and result mapping

All six `/api/v1` endpoints are reused, along with legacy state/events/reports.
PHP bodies explicitly include `language: "php"`; existing Python payloads keep
their prior defaults/shape. Only operation-specific fields leave the browser.
Security fixture IDs cannot be substituted with arbitrary paths, Python profiles,
Docker commands or mount options.

Uncertain submission retries retain the original language, optional security
profile, payload, instance ID and Idempotency-Key even after form edits/reload.
No automatic POST/retry or live fallback was added. Instance changes still make
old intents stale. PHP language is retained with browser run history and the
last attached ID, while per-run parameters/report provenance override the form.

PHP migration shows PHP files → Golden cases → Fixture migration → Verification
→ Security findings → Evidence. Static audit omits execution/migration stages;
compatibility omits translation/security and only shows recording when selected.
Activity comes from phases/events, never estimated percent or ETA. Module green
in static audit is labeled Audited and does not mean behavior or safety verified.

The PHP comparator exposes outcome hashes/reasons rather than raw expected/actual
values. Mismatch details use those exact fields; they do not invent missing raw
outputs. Existing tests on source/target show actual `tests.php` patch versions.
PHP state metrics count golden comparisons; existing tests are listed separately.

Compatibility maps PHP `syntax_passed`, `tests_passed`, `behavior_verified`
independently. False is Failed; null/missing is Not verified. Failed runs never
receive an overall green verdict even if a prior individual check passed. Python
continues to use its existing syntax_compatible/recorded_cases_match fields.

PHP scanner findings are joined by ID from security_audit.findings,
security_before/after.findings and security_fix.decisions. Rows show real CWE,
confidence, severity, file/line, status and recommendation. The eight PHP rule
IDs have readable category labels; absent findings/categories are not fabricated.
No Bandit provenance is assigned to PHP. Coverage stays limited/partial, and a
clean scan is not a security guarantee.

PHP fix reports use `verified`, `source_unchanged`, attempt
`originals_unchanged` and `security_rescan`; these are distinct from Python's
fields. Needs review and rejected attempts may overlap. Syntax failure shows
later checks as Not run. Rescan Recorded does not alone mean a patch was accepted.
The accepted-copy scope and rollback are visible; model-generated fixes remain
disabled and no unsupported approve/reject endpoint/button was added.

Evidence uses existing cursor polling and independent WebCrypto chain checks.
Download HTML/JSON only after finalized. Saved API-export reports replay locally
with explicit Saved report / offline fixture labels. Replay makes no project or
model calls; a valid local hash chain is not an external signature. The standalone
engine report without the API state envelope is not an API-export replay format.

## Verification performed

```text
node --test frontend/tests/*.test.cjs
tests 66; pass 66; fail 0; skipped 0

JavaScript syntax: 24 .js/.cjs files passed node --check
```

The 40 prior tests remain and 26 PHP cases cover language/project/version/profile
selection, unavailable proof/images, static audit without Docker/Bandit, blocked
and stale preflight, request whitelisting, HTTP 202, language-safe idempotency and
reload, finalizing, findings/decisions, null checks, mismatches and saved evidence.
These mock-fetch/DOM contract fixtures are test data, not migration evidence.

An installed headless Chrome was also used against real local API at
`http://127.0.0.1:8001`:

* Python migration preflight accepted its original 2.7 → 3.12 request.
* One PHP fixture migration, one iteration, with optional security fixtures:
  **22/22 golden comparisons**, **9 source + 9 target tests**, one accepted
  hardening, one needs_review and two rejected/rolled-back proposals.
* Busy preflight returned actual run_busy and blocked the UI.
* PHP static audit: **10 potential warnings**, project_executed=false, reduced
  isolation; CWE/category/scanner information rendered correctly.
* Unchanged legacy PHP compatibility syntax check: expected failed,
  syntax_passed=false, tests_passed=null. UI gave no success verdict.
* Python simulation completed with explicit simulation labels. This is browser
  regression coverage, not a new claim of real Python migration.
* Final reports, legacy events/HTML export, independent evidence verification,
  unchanged source hashes, no false Live badge, and all result tabs passed.
* Viewport width **390 px**: language control visible, no page overflow. Existing
  themes, responsive grids and animations were preserved. No visual screenshot
  review or screenshots/video/trace were produced.
* **0 JavaScript exceptions; 0 external requests.** No Meta calls, package/image
  downloads or heavy Docker matrix. The Docker work was limited to the one PHP
  migration and the target syntax check needed for UI integration verification.

After the final labels changed, three already-generated real PHP reports were
reopened in Chrome read-only: all three passed current UI/evidence checks without
new POSTs or Docker execution. Full Python Docker regressions were not repeated;
they were verified in P6.2/P6.3 and backend files are unchanged here.

The opt-in smoke is deliberately separate from lightweight `*.test.cjs`:

```powershell
# Start the existing backend on a free loopback port; no .env editing needed.
.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8001

# Requires an already-installed Playwright module and Chrome. No installs/pulls.
# If Playwright is outside the default module search path, set NODE_PATH to its
# existing node_modules directory; do not download it as a test side effect.
$env:PROOFPORT_FRONTEND_PHP_SMOKE = '1'
$env:PROOFPORT_INTEGRATION_URL = 'http://127.0.0.1:8001'
node frontend/tests/php.browser.integration.cjs
```

An actual local proof and runtime images must already be ready. Missing readiness
fails the opt-in test explicitly; the browser never runs verify-demo or pulls
images. See the backend operator guide for that separate action.

## Changed files

* `js/control.js`, `js/control-form.js`: language-aware discovery, safe payloads,
  profiles, static-audit readiness, form and resolve/catalog refresh.
* `js/labels.js`, `js/store.js`, `js/app.js`: language/provenance/history, new
  evidence types and Docker banner that does not block static work.
* `js/views/migration.js`, `security.js`, `compatibility.js`: PHP stages, metrics,
  checks/findings/fix-field mapping and honest failed/unverified states.
* `js/views/overview.js`, `evidence.js`, `shared.js`: language/patch labels, PHP
  source tests and explicit Not verified tri-state labels.
* `tests/harness.cjs`, `php-fixtures.cjs`, `php.test.cjs`,
  `php.browser.integration.cjs`: lightweight regression/contract and opt-in smoke.
* `README.md`, `PHP_INTEGRATION.md`: frontend documentation only.

Remaining limits belong to the backend: finite cases, limited lexical security
rules, narrow accepted fixture policy, no automatic dependency installation,
no verified live PHP AI migration/security fix, no universal project equivalence.
