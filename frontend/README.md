# Proofport Console — P4.2

Static HTML/CSS/vanilla JavaScript; no build step, dependencies, CDN or third-party requests at runtime. The existing three-column redesign and themes are preserved. The backend serves `frontend/` at `/` on the same origin.

## Backend prerequisite

The v1 contract was read directly with:

```text
git show backend/codex:backend/API_CONTROL_PLANE.md
```

Contract revision: backend `e2817d0`. Frontend base: `968c5b8`.
This frontend commit does not merge backend branches. Until P4.1 is integrated into the server checkout, that older backend returns capabilities 404 and the console deliberately uses the legacy form.

With a P4.1 backend serving these files, open http://127.0.0.1:8000 and choose **Migration → Run control**. Refresh the browser after updating scripts. Operations and versions no longer require editing `.env`.

## Connected API routes

| Route | Usage |
| --- | --- |
| GET `/api/v1/capabilities` | Discover policy, instance ID, Docker, verified runtimes and operation matrix; explicit refresh and before every submission/retry |
| GET `/api/v1/projects` | Registered projects and project-bound fixture/golden profiles |
| POST `/api/v1/projects/resolve` | Register a workspace-relative path, then use the returned project ID |
| POST `/api/v1/runs/preflight` | Check the current request; HTTP 200 with `can_start: false` blocks Start |
| POST `/api/v1/runs` | Create a run; HTTP 202 `{run_id}` with an Idempotency-Key |
| GET `/api/v1/runs/{id}` | Immutable parameters, effective execution mode, lifecycle, finalized, partial results and legacy state |
| GET `/api/health` | Connection health every 5 seconds; its startup Docker/config echoes do not override v1 readiness |
| POST `/api/runs` | Legacy form only, sends only `source_path` and `max_iterations`; never automatically retried |
| GET `/api/runs/{id}` | Legacy state polling |
| GET `/api/runs/{id}/events?since=N` | Both modes: sequential cursor polling, de-duplicated by seq |
| GET `/api/runs/{id}/report?format=json` | Both modes: final report retrieval; HTML/JSON download links use the same route |

Only **capabilities HTTP 404** selects legacy mode. Timeout, HTTP 503, malformed JSON/shape, projects 404 or run 404 never silently downgrade. Metadata errors offer explicit refresh.

## Run control

1. Select an enabled operation and a registered available project. Custom paths must be workspace-relative and pass server policy; there is no upload or clone.
2. Choose source/target Python from the intersection of the operation matrix and configured, available, verified runtimes with the correct source/target role. Image presence alone is insufficient.
3. Select available profiles bound to that project. Missing migration profiles block migration. Custom projects do not automatically gain fixture or golden profiles.
4. Click **Check readiness**. Specific errors include their code, message and field. Any form edit/refresh invalidates preflight; late responses cannot approve the edited configuration.
5. Click **Start run** after successful preflight. Creation rechecks conditions and may still reject a busy worker or changed project/runtime.

Current server operation matrix (documentation only; selectors use capabilities):

| Operation | Versions | Execution |
| --- | --- | --- |
| Migration | 2.7 → 3.12 | offline_fixtures, requires fixture + cases profiles; iteration limit 1–5 |
| Security Audit | source 2.7, 3.12 or 3.13 | offline; no target, translation settings, cases or fixes |
| Compatibility Check | 3.12 → 3.12; 3.12 → 3.13; 3.13 → 3.12 | offline; explicit syntax/tests/behavior level |
| Simulation | No runtime/version claims | Separate migration demo if the server offers it; no Docker required |

Compatibility behavior requires a bound cases profile. Tests/behavior also require an existing nonempty passing unittest suite; preflight/worker determine this, not an invented catalog field. The UI never silently downgrades behavior to syntax. Audit parse coverage may be partial, especially with Python 2/new grammar.

Example submitted migration request:

```json
{"operation":"migration","project_id":"legacy_shop","execution_mode":"offline_fixtures","source_version":"2.7","target_version":"3.12","max_iterations":5,"fixture_profile_id":"legacy_shop_py27_py312","cases_profile_id":"legacy_shop_golden"}
```

Only operation-specific whitelisted fields are sent. Browser callers never provide Docker commands, mounts, image names, API keys or manifest/cases file paths.

## Submission safety and completion

Each new intent gets a fresh UUID Idempotency-Key. Network/parse/server failures preserve the original payload, key and instance ID, including in browser storage when available. **Retry identical submission** explicitly resends those exact bytes/values, even after editing the form; it does not substitute normalized preflight parameters. No POST is automatically repeated. Known HTTP 4xx rejections clear that intent and require fresh preflight. Forgetting an uncertain intent asks for acknowledgment because a job may already exist.

Before a retry/submission the console checks instance ID. An old intent from a different backend instance is marked stale and cannot be resubmitted. A restart between the final capability read and POST cannot be made atomic by this API; run-detail instance checking detects the mismatch rather than silently attaching to another instance. No durable/multi-process guarantees are claimed.

Polling uses v1 details plus legacy events, once per second with backoff on failures. `finalizing` remains active. Three independent states are displayed:

- Backend lifecycle/finalized: whether the worker finished and released its slot.
- Final report: idle/loading/ready/error; matching terminal state and complete event contents are required before acceptance. Report retrieval can be retried without creating a run.
- Browser evidence chain: checking/ok/broken/empty/unavailable. Receiving a report does not imply a valid chain; this local hash consistency check is not an external signature.

Run IDs and this browser's history are retained locally. Backend runs remain in memory and disappear on restart; missing IDs are marked lost, never recreated. Detaching a run does not cancel the backend job.

## Provenance and security

Per-run v1 execution/parameters override deployment guesses and `health.llm_mode`. Imported newer reports use `verification.control.parameters`; older saved reports retain the legacy provenance path. Saved report replay is local read-only viewing, not backend execution.

Simulation metrics/tests are labeled simulated. Offline fixtures are pre-written patches, not AI migration. Offline audit/compatibility checks do not translate code. Live Meta AI and AI Security Fix remain disabled; no generation endpoint or button is invented. A server-origin history entry named `live` internally means an API connection, not a model call.

Bandit findings remain potential warnings. Zero findings are not proof of safety; no scan and a clean scan are distinct. Syntax, existing tests and recorded behavior remain separate tri-state checks; null means not confirmed. Pipeline activity events do not by themselves prove that a stage passed. Detailed CWE/diffs/fix decisions still require the final report.

## Files and verification

`js/api.js` retains legacy methods and adds v1 methods. `js/control.js` manages discovery, draft, profiles, preflight and immutable submission intent. `js/control-form.js` mounts the controls once so ordinary polling preserves input/focus. `store.js` handles v1 polling and report consistency. Labels, shell, panels and views consume per-run metadata. No runtime libraries were added.

Tests require Node.js (tested with v24.22.1); the dashboard itself does not require Node:

```text
node --test frontend/tests/*.test.cjs
```

The tests use mock fetch, explicit contract fixtures, real WebCrypto hash checks, deterministic polling and a small DOM adapter for component wiring. They do not execute projects, Docker or Meta, and are not browser layout/end-to-end verification. Contract fixtures are not migration/security evidence. No screenshots are generated.

Before release, separately authorized branch integration and a browser smoke test against the P4.1 server are still required. No merge, rebase or push is part of this change. No backend, root tests or sample sources are changed.
