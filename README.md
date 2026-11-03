# Proofport

**Port legacy code. Prove it works.**

Demo video: [DEMO_VIDEO_URL] | Track: Indie Developer | Theme: Push the Frontier

Proofport is a local web app for migrating Python 2.7 code to Python 3.12.
Muse Spark proposes translations; Docker checks syntax, recorded behavior and existing tests before acceptance.
The same verification approach supports PHP 7.4 to 8.3 and conservative security-patch review.
A dashboard shows progress, findings, unchanged-source hashes and evidence-backed reports.

**Why:** a plausible rewrite can silently change integer division, rounding, encodings or exception behavior.
Proofport compares observable results and retains failures, so a green status has a defined, inspectable scope.

## Built during the hackathon

All Proofport-owned code was written during the **Oct 27–Nov 4, 2026** build window
for the Meta Global AI Developer Hackathon; no code from earlier projects was reused.
We built the migration pipeline, Docker sandbox runner, comparator, security pass,
evidence log, API Control Plane and dashboard. `samples/legacy_shop` is our own
MIT-licensed Python 2 demo library, written for this project; PHP fixtures are also owned.
Team: **Proofport**, one Solo Developer / Project Creator: [PUBLIC_NAME], [GITHUB_PROFILE_URL].

External runtime/test dependencies are FastAPI, Uvicorn, the OpenAI SDK,
python-dotenv, Pydantic, HTTPX and pytest, with transitives pinned in
[`backend/requirements.txt`](backend/requirements.txt).
Bandit 1.8.6 runs in its Docker image; Python/PHP use official interpreter images.
The frontend uses plain HTML/CSS/JavaScript, with Node only for tests.
See [third-party notices](THIRD_PARTY_NOTICES.md).

## How it uses Meta models

[`LLMClient`](backend/llm/client.py) calls the OpenAI-compatible Meta Model API
at `https://api.meta.ai/v1`; recorded real runs used **`muse-spark-1.3`**.
It reads `MODEL_API_KEY`, `MODEL_NAME`, `MODEL_BASE_URL` and `LLM_MODE`.
The active structured path is [ModelSession](backend/ai/provider.py) with
[language-specific prompts](backend/ai/prompts.py):
- Translation: propose one complete Python/PHP file, preserving public APIs and behavior.
- Repair: receive original source, previous candidate and failing-case expected/actual evidence.
- Security: propose code and explain behavior impact for a scanner-selected finding.
Model confidence does not establish exploitability or authorize a fix; standalone model triage is not a dashboard feature.
Live jobs require explicit module/finding approval and call/token/cost limits; paid transport retries and fixture fallback are disabled.
Public API/UI live generation stays disabled. Mock/replay are labelled and never presented as a new live Meta run.

## What it does

- Analyze Python/PHP projects and run bounded fixture migrations on working copies.
- Record golden observations, compare typed results and run existing tests in Docker.
- Separate syntax, tests and behavior verification; preserve originals and roll back failed candidates.
- Audit Python with Bandit and PHP with limited rules; retain open/review/reverted decisions.
- Export HTML/JSON reports with SHA-256 hashes, provenance and hash-chained evidence.
- Control projects, versions, profiles and preflight through the dashboard and `/api/v1`; preserve five legacy endpoints.
- Replay saved reports and verify evidence without a new model call.

## Results

Historical real Meta runs, **not new live executions or offline fixture results**:

| Run | Golden cases | Existing tests | Decision / estimated cost |
| --- | --- | --- | --- |
| Python `mathutils.py`, 2.7 → 3.12 | 31/31 | 3/3 | Accepted scoped migration / $0.00831575 |
| PHP `src/legacy.php`, 7.4 → 8.3 | 22/22 | 9/9 | Accepted scoped migration / $0.00612075 |
| Python unsafe-eval proposal | 5/9 | 0/1 | Rejected, rolled back, `needs_review` / $0.013249 |
| Whole-project live migration (planned; unverified) | [FILL IN FROM A REAL RUN] | [FILL IN FROM A REAL RUN] | Not established |

Costs are recorded estimates at configured rates, not provider invoices; allowances remain visible in reports.
Source summaries: [Python](backend/P82_LIVE_RESULT.md), [PHP](backend/P83_PHP_LIVE_RESULT.md), [rejected fix](backend/P84_SECURITY_LIVE_RESULT.md).
Raw live recordings are intentionally not committed. Reviewed evidence-pack download: [REVIEWED_EVIDENCE_PACK_URL].
Use **Open saved report** with a supplied pack; viewing it is replay, never new generation.

### Try Proofport — 10 Judge Test Scenarios

[Ten owned offline scenarios](judge_tests/README.md) cover Python/PHP migration, math, compatibility, security decisions and rollback.
The last full run returned **5 PASS, 5 NEEDS_REVIEW, 0 FAIL/SKIP**, exit 0; expected review means rejection assertions passed, not a fixed vulnerability.
After installing dependencies and the listed local images, run `judge_tests\run.bat` or `judge_tests\run.bat --scenario 05`.
Saved summaries contain actual checks/hashes; missing mandatory Docker checks produce SKIP and nonzero exit.

## Quick start — Windows

Requirements: **Python 3.12**, **Docker Desktop using Linux containers**, and internet for initial dependency/image setup.
A **Meta Model API key is needed only for separately authorized live CLI jobs**; offline checks and replay need none.

From PowerShell at the repository root:
```powershell
# Optional; preserve any existing private configuration.
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\start.bat
```
`start.bat` creates/checks `.venv`, installs `backend/requirements.txt`, starts FastAPI and opens **http://127.0.0.1:8000**.
The example defaults to **`LLM_MODE=mock`**: canned client answers, not AI migration.
Setting `LLM_MODE=live` alone neither grants paid permission nor enables live dashboard runs.
Keep any live key in ignored private configuration; see [live setup and limits](backend/META_LIVE_READINESS.md).

Start Docker Desktop. In another terminal, explicitly prepare the Python demo images and local verification receipts:
```powershell
docker info --format '{{.OSType}}'
docker pull python:2.7
docker pull python:3.12-slim
docker build -t proofport-bandit:1.8.6 -f backend/sandbox/Dockerfile.bandit backend/sandbox
.venv/Scripts/python.exe -c "from backend.core.versions import VersionRegistry; r=VersionRegistry(); print(r.verify('2.7')); print(r.verify('3.12'))"
```
The application does not pull images automatically. Refresh the dashboard:
**Migration → Run control → Python → legacy_shop** (`samples/legacy_shop`), **2.7 → 3.12**,
fixture profile `legacy_shop_py27_py312`, cases profile `legacy_shop_golden`, then **Check readiness → Start run**.
This runs authored **offline fixtures with real Docker checks**, not a fresh AI translation.
Replay requires an explicitly selected saved report/response recording; there is no automatic fallback.
For PHP/images, API details and tests, see the [runbook](docs/DEMO_RUNBOOK.md),
[API contract](backend/API_CONTROL_PLANE.md) and [judge setup](judge_tests/README.md).
Change a busy port with `$env:PROOFPORT_PORT = '8765'` before starting; do not stop another service.

## Architecture

```text
Browser dashboard -> FastAPI -> RunSpec / readiness / single-run gate
  -> Python / PHP adapter -> analyze -> record original behavior
  -> translate <-> Docker syntax / golden / existing-test verification
       |                     -> security proposal / rescan / decision
       +-> LLMClient -> Meta API (approved CLI), mock or explicit replay
  -> SHA-256 + chained evidence -> HTML / JSON / saved-report replay
```

FastAPI serves the static frontend and both API generations.
Immutable RunSpec and project policy constrain paths, runtimes and profiles.
Adapters reuse the recorder, comparator and language-specific verification engines.
Docker runs copies as non-root, without network, with read-only mounts and resource/time limits.
The verifier—not the model—decides acceptance; failed candidates are reverted.
Evidence records prompt hashes, usage and decisions; receipts check report consistency.

## Limitations

- Migration scope is Python **2.7 → 3.12** and PHP **7.4 → 8.3**; verified profiles are not universal project support.
- Docker is mandatory for project execution: **no reduced-isolation host fallback exists**. Static-only checks do not claim runtime verification.
- Recorded cases establish observed equivalence, not a proof for every input; documented comparison allowances are visible.
- Behavior/API/configuration/crypto-changing fixes remain `needs_review`, not automatically accepted; the live eval proposal failed verification.
- Python 2 Bandit coverage is partial; PHP rules are lexical. Zero findings is not proof of security.
- Hash chains establish local consistency, not external attestation. Docker is not protection against every kernel exploit.
- One active local run; no multi-tenant hosting, automatic dependency installation or arbitrary-project live UI workflow.

## AI assistance

Code was written with help from Codex and Claude Code; they are tools, not team members.

## License

[MIT](LICENSE), copyright 2026. Preserve the sample license and [third-party notices](THIRD_PARTY_NOTICES.md).
