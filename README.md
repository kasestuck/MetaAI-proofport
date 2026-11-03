# Proofport

**Port legacy code. Prove it works.**

Proofport is a local Python/PHP modernization console. It records the original
program's behavior in Docker, asks Meta Muse Spark for a translation or security
proposal, and independently checks syntax, golden cases and existing tests before
accepting a result. Originals stay unchanged. Failed or policy-changing fixes
require review.

Built for the **Meta Global AI Developer Hackathon 2026**, Indie Developer track,
**Push the Frontier** theme. This is a prototype with finite verified scenarios,
not universal migration support or a security certification.

## Confirmed Meta AI results

These are previously executed **real Meta Model API runs**, using `muse-spark-1.3`.
Viewing their saved evidence is replay; it makes no new model request.

| Scenario | Docker verification | Decision | Historical estimated cost |
| --- | --- | --- | --- |
| Python `mathutils.py`, 2.7.18 → 3.12.16 | **31/31** golden cases, **3/3** MathTests | Accepted scoped migration; one call | $0.00831575 |
| PHP `src/legacy.php`, 7.4.33 → 8.3.36 | **22/22** golden cases, **9/9** native tests | Accepted scoped migration; one call | $0.00612075 |
| Python unsafe-eval proposal, B307 / CWE-78 | Syntax passed; **5/9** cases, **0/1** ConfigTests; B110 appeared | Rejected, rolled back, **needs_review**; one call | $0.013249 |

Costs use recorded usage and configured rates, not an independent provider invoice.
Comparison uses documented allowances, including PHP deprecation notices; the
original reports retain those allowances rather than hiding them.
Neither successful migration needed AI repair. The eval proposal is **not** a
successful security fix. Original summaries:
[Python](backend/P82_LIVE_RESULT.md), [PHP](backend/P83_PHP_LIVE_RESULT.md),
[rejected security proposal](backend/P84_SECURITY_LIVE_RESULT.md).

## Quick Start — Windows

Install **Python 3.12** and **Docker Desktop with Linux containers**. Use Git or
an extracted checkout. The frontend is plain HTML/CSS/JavaScript: no Node build,
CDN or API key is required to run the app or view saved reports.

From PowerShell in the repository root:

```powershell
.\start.bat
```

This creates `.venv` if missing, installs [pinned dependencies](backend/requirements.txt),
serves the frontend and opens `http://127.0.0.1:8000` after health succeeds.
Initial package installation needs internet. Ctrl+C stops your server. If the
port is occupied, choose another; never stop somebody else's service:

```powershell
$env:PROOFPORT_PORT = '8765'
.\start.bat
```

After dependencies are installed, an alternative without package installation or
automatic browser opening is:

```powershell
.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8765
```

Open **Migration → Run control**, choose Python/PHP, an available operation,
project, versions and matching profiles, then **Check readiness** and **Start run**.
Capabilities and preflight determine actual availability. No `.env` edits are
needed to switch operations. Missing Docker blocks dynamic checks without host fallback.

### Explicit Docker setup

Image setup is an operator action. The application **never downloads images or
installs project dependencies automatically**. Install only what you will use;
the following setup commands use the network:

```powershell
docker info --format '{{.OSType}}'  # must report linux
docker pull python:2.7
docker pull python:3.12-slim
docker build -t proofport-bandit:1.8.6 -f backend/sandbox/Dockerfile.bandit backend/sandbox
# Optional PHP demo:
docker pull php:7.4.33-cli
docker pull php:8.3.36-cli
```

On a fresh clone, installed images are **available**, not yet **verified**.
After installing app dependencies, explicitly create local proof receipts:

```powershell
.venv/Scripts/python.exe -c "from backend.core.versions import VersionRegistry; r=VersionRegistry(); print(r.verify('2.7')); print(r.verify('3.12'))"
# Optional: real PHP fixture demo with tests, golden cases, rollback and receipt.
.venv/Scripts/python.exe -m backend.php verify-demo
```

These checks use Docker, never call Meta and never pull images. Refresh the UI
afterward. Receipts bind code, actual source bytes and image IDs; changes can
correctly invalidate readiness. Optional Python 3.13 compatibility additionally
needs `python:3.13-slim` and `VersionRegistry().verify('3.13')`; do not install
the entire version matrix. Details: [Docker/demo runbook](docs/DEMO_RUNBOOK.md).

## Execution modes

| Mode | What happens |
| --- | --- |
| Offline fixtures | Authored patches with **real Docker checks**, no model calls; not AI migration. |
| Offline checks | Analysis, audit or selected compatibility checks; no translation or paid calls. |
| Simulation | Labelled synthetic migration/test metrics; no real migration claim. |
| Saved real run | Read-only historical Meta results/evidence; **not a new live run**. |
| Live Meta | Separately authorized bounded developer CLI jobs; **disabled in the public API/UI**. |

Current offline migration pairs are Python **2.7 → 3.12** and PHP **7.4 → 8.3**,
for project-bound demo profiles. Image presence alone never enables migration.
Available compatibility operations do not imply that a selected project passes.

### Three-scenario saved-evidence demo

Actual local recordings are deliberately not committed. The owner can export
a checked portable pack from the workstation containing the original recordings:

```powershell
$proofportDemo = .venv/Scripts/python.exe -m backend.release prepare-demo | ConvertFrom-Json
.venv/Scripts/python.exe -m backend.release verify-demo --pack $proofportDemo.pack
$proofportDemo.pack
```

The new ignored folder/ZIP contains unchanged original reports, their sealed
artifacts, source snapshots and explicitly labelled display projections. Use
**Open saved report** to select `proofport-python.json`, `proofport-php.json` or
`proofport-security.json`. Wait for the independent browser chain check. Original
HTML reports are linked from the pack's `index.html`.

Fresh clones do not include these local recordings. Publishing a reviewed
proof-pack download and video remains an owner action in the
[submission checklist](docs/SUBMISSION_CHECKLIST.md); no link is invented here.

## Architecture

```text
Browser → FastAPI /api/v1 → immutable RunSpec + shared single-run gate
  → project policy + readiness → language adapter (Python / PHP)
  → analyze → record original behavior → translate / propose patch
  → Docker syntax + golden comparison + existing tests → bounded repair
  → security rescan + conservative decision → JSON/HTML + chained evidence
                        ↘ LLMClient (explicit mock / replay / authorized live)
```

The model proposes code; it does not decide whether its own proposal passed.
Docker uses a non-root UID, no network, read-only sources/root/tools, dropped
capabilities and CPU/memory/PID/output/time limits. No key or Docker socket is
mounted into a project. There is no host execution fallback.

All five legacy endpoints and six `/api/v1` endpoints remain. State, events and
reports are separate; `finalizing` is not completion. See
[API Control Plane](backend/API_CONTROL_PLANE.md), [PHP](backend/PHP_OFFLINE.md),
[architecture/history](backend/ARCHITECTURE.md) and [P9 audit](backend/P9_STABILIZATION.md).

## Meta AI integration

`LLMClient` uses the OpenAI-compatible SDK with `MODEL_API_KEY`, `MODEL_NAME`,
`MODEL_BASE_URL=https://api.meta.ai/v1` and `LLM_MODE`. The verified historical
model ID is `muse-spark-1.3`. `.env.example` defaults to offline/mock. Real keys
belong only in ignored private configuration, never the frontend or a submission.

Live jobs need separate approval, strict file/finding bindings, structured JSON,
call/token/cost reservations, zero automatic transport retries and Docker checks.
There is no live-to-fixture fallback. The P8 trial limit was two calls, a $0.05
estimated cap, 9,216 input / 3,072 output allowance and 30 seconds per call. This
is historical trial configuration, not future permission or a current-price guarantee.
[Live readiness](backend/META_LIVE_READINESS.md) and the P8 result documents give
details. **Never rerun paid commands just to inspect saved results.**

## Limitations and security

- Finite tests are evidence for measured inputs, not universal equivalence. Genuine
  Python evidence covers one module/scoped test class; PHP AI-translated one file
  and ran the unchanged nine-test demo suite.
- The full Python **offline fixture** demo passes 90 cases and ten existing tests;
  this is not a whole-project live AI migration.
- Original Python 2 Bandit coverage is partial (four parse errors). PHP rules are
  lexical heuristics, not full taint analysis. Zero findings never proves safety.
- Eight Python warnings remain for review. Broader PHP review accepted one narrow
  hardening and left nine warnings for review. Eval is never automatically accepted.
- Hash chains/receipts establish local consistency, not externally signed proof.
- Local-only, one active run, in-memory history/idempotency. No remote auth,
  hosted multi-tenant service, automatic project dependency installation or
  universal framework support. Docker does not cover every kernel/native exploit.

See [Security policy](SECURITY.md) and [release readiness](docs/RELEASE_READINESS.md).

## Try Proofport — 10 Judge Test Scenarios

The [judge suite](judge_tests/README.md) provides exactly ten independently
selectable owned scenarios: Python/PHP fixture migrations, math edges,
compatibility, SQL/eval/secrets/crypto, XSS, constant-command hardening and rollback.
All are **offline**, with actual Docker verification and zero Meta calls.

Install the pinned requirements in a Python 3.12 `.venv`, start Docker Desktop
with Linux containers, and explicitly install only the required images listed in
the suite README. Run Proofport with `start.bat` for optional UI inspection; the
suite itself needs no server, API key or manual `.env` changes.

```powershell
judge_tests\run.bat
judge_tests\run.bat --scenario 05
.venv/Scripts/python.exe judge_tests/runner.py --list
```

The runner prints a saved JSON summary with per-scenario PASS / FAIL / SKIP /
NEEDS_REVIEW, real hashes/checks and evidence. Exit 0 requires all selected
mandatory assertions to pass; a mandatory skip is nonzero. An expected
NEEDS_REVIEW confirms rejection/rollback, **not** an accepted security fix.

These ten offline scenarios are separate from the genuine historical Meta
migrations above. No fixture is substituted for a model answer and no saved
replay is presented as a new live run. See the [P11 release audit](docs/P11_RELEASE.md)
for actual results, branch preservation and publication limits.

## Tests

```powershell
.venv/Scripts/python.exe -m pytest -q -m "not docker"
node --test frontend/tests/*.test.cjs
.venv/Scripts/python.exe -m pip check
```

Node is only needed for tests (P10 used Node 24.22.1); the fast suite needs no npm
packages. Root pytest collects only `tests/`, excluding demo fixtures from host
execution. Docker checks are opt-in:

```powershell
$env:PROOFPORT_DOCKER_TESTS = '1'
.venv/Scripts/python.exe -m pytest tests/test_release_docker.py -q
```

Saved-candidate tests visibly skip when the original local proof is absent;
they never substitute a fixture. Other selected checks are documented in the
[release report](docs/RELEASE_READINESS.md); do not run the full Docker matrix
just to rehearse a saved demo.

## Built during the hackathon

Proofport and its owned demo projects were developed for this event. Local Git
history starts **October 27, 2026**. Project code was written for Proofport rather
than copied from an earlier project; third-party libraries retain their licenses.
Commit dates support the development record, not independent proof of originality.

## Team

| Field | Value |
| --- | --- |
| Team name | **Proofport** |
| Team size | **1** |
| Role | **Solo Developer / Project Creator** |
| Public name | **TODO — owner to provide** |
| GitHub profile | **TODO — owner to provide** |

Codex and Claude Code are development tools, **not team members**.

## AI Assistance Disclosure

The solo creator used **Codex** and **Claude Code** to assist with code, tests,
documentation and frontend work. Meta Muse Spark was used **inside the product**
for the recorded real Python/PHP translations and rejected security proposal.
Development assistance and product model usage are separate roles. The human
creator directs and reviews the project; actual execution and comparison
determine verification outcomes.

## License and demo materials

[MIT](LICENSE), explicitly selected by the owner. Preserve the sample license and
[third-party notices](THIRD_PARTY_NOTICES.md). This does not relicense interpreters,
dependencies, Docker Desktop or Meta services.

[Three-minute demo script](docs/DEMO_SCRIPT.md) ·
[Submission checklist](docs/SUBMISSION_CHECKLIST.md) ·
[Release readiness and blockers](docs/RELEASE_READINESS.md)
