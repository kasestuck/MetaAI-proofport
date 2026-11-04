# Proofport

**Port legacy code. Prove it works.**

Demo video: https://youtu.be/-P6cKxvSha8 | Track: Indie Developer | Theme: Push the Frontier

Proofport is a local Python/PHP modernization app. Muse Spark proposes translations; Docker checks syntax, golden cases and existing tests before acceptance. Python 2.7 → 3.12 and PHP 7.4 → 8.3 have verified scoped live demonstrations. The dashboard shows progress, security findings, unchanged-source hashes and HTML/JSON evidence. **Why:** rewrites can silently change division, rounding, encodings and exceptions; acceptance should depend on measured behavior.

## Built during the hackathon

All Proofport-owned code was written during **Oct 27–Nov 4, 2026** for the Meta Global AI Developer Hackathon; no earlier-project code was reused. We built the pipeline, Docker runner, comparator, security pass, evidence log, API Control Plane and dashboard. `samples/legacy_shop` is our own MIT Python 2 demo; `tests/fixtures/php_shop` is our own PHP demo. Team: **Proofport**, one Solo Developer. Dependencies: FastAPI, Uvicorn, OpenAI SDK, python-dotenv, Pydantic, HTTPX and pytest, with pinned transitives in [backend/requirements.txt](backend/requirements.txt). Bandit 1.8.6 runs in Docker; runtime images are official Python/PHP. Frontend: plain HTML/CSS/JavaScript, no build or CDN; Node is for tests. See [third-party notices](THIRD_PARTY_NOTICES.md).

## How it uses Meta models

[LLMClient](backend/llm/client.py) calls `https://api.meta.ai/v1`; genuine recorded runs used `muse-spark-1.3`. Settings: `MODEL_API_KEY`, `MODEL_NAME`, `MODEL_BASE_URL`, `LLM_MODE`. [ModelSession](backend/ai/provider.py) uses [language-specific prompts](backend/ai/prompts.py) for complete-file translation, repair from original/previous code plus expected/actual failures, and scanner-selected security proposals. Models propose; Docker checks and conservative policy decide. Standalone automatic model triage is not a dashboard feature. Live CLI jobs require separate module/finding approval and call/token/cost limits. Generic live generation stays disabled; the [P13 Dashboard demo](backend/P13_LIVE_DEMO.md) allows only the two fixed modules with local owner permission and fresh paid UI consent. No paid transport retries or hidden fixture fallback. Mock, offline fixtures and saved replay never become new live Meta runs.

## What it does

- Analyze Python/PHP, record golden observations, compare typed results and run existing tests in Docker.
- Work on copies; verify syntax/tests/behavior separately; roll back failed or incompatible candidates.
- Export HTML/JSON, SHA-256, model provenance, report receipts and hash-chained evidence.
- Offer migration, audit, compatibility and preflight through `/api/v1`; preserve five legacy endpoints and saved-report replay.

### Our PHP implementation

`backend/php/` provides its own analyzer, Docker harness, comparator, scanner and fix verifier; PHP is not parsed with Python AST or scanned with Bandit.

| Operation | Implemented scope |
| --- | --- |
| Migration | PHP **7.4.33 → 8.3.36**, original `php_shop`, 22 golden cases, 9 native tests; authored fixture mode plus the separately approved P13 single-file live demo. |
| Security audit | Limited lexical rules for SQL injection, XSS, command injection, unsafe deserialization, path traversal, hardcoded secrets, weak hashing and unsafe uploads. Findings are potential risks. |
| Compatibility | PHP **7.4 → 8.3**; separate syntax, tests and behavior results. The unchanged legacy demo is expected to expose incompatibilities. |
| Fix verification | Offline proposals, both runtimes, golden/tests/rescan and rollback; changed contracts remain `needs_review`. |

Actual Meta migration of `src/legacy.php` is recorded below. PHP 8.4, arbitrary version pairs and unrestricted live UI migration are not enabled. [PHP implementation and limits](backend/PHP_OFFLINE.md) · [PHP live result](backend/P83_PHP_LIVE_RESULT.md)

## Results

Historical real Meta runs, **not new runs or authored fixture results**:

| Run | Golden cases | Tests | Decision / estimated cost |
| --- | --- | --- | --- |
| Python `mathutils.py`, 2.7 → 3.12 | 31/31 | 3/3 | Accepted scoped migration / $0.00831575 |
| PHP `src/legacy.php`, 7.4 → 8.3 | 22/22 | 9/9 | Accepted scoped migration / $0.00612075 |
| Python unsafe-eval proposal | 5/9 | 0/1 | Rejected, rolled back, `needs_review` / $0.013249 |

Costs use recorded usage/configured rates, not provider invoices. Comparison allowances stay visible. [Python proof summary](backend/P82_LIVE_RESULT.md) · [Rejected fix summary](backend/P84_SECURITY_LIVE_RESULT.md).

## Quick start — Windows and VS Code

Install Git, **Python 3.12**, Docker Desktop (**Linux containers**) and optionally VS Code; Node 24 is needed only for frontend tests. No API key is needed for offline checks/replay. A new private Meta key and separate approval are required for live CLI or the fixed P13 Dashboard demo. For a fresh clone, run these commands in PowerShell, then use **Terminal → New Terminal** in VS Code:
```powershell
git clone https://github.com/kasestuck/MetaAI-proofport.git
cd MetaAI-proofport
code .
if (!(Test-Path .venv/Scripts/python.exe)) { py -3.12 -m venv .venv }
.venv/Scripts/python.exe --version
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\start.bat
```
For an existing checkout, skip cloning and open its root. If `code` is unavailable, use **File → Open Folder**. Choose **Python: Select Interpreter → .venv/Scripts/python.exe** if using VS Code's Python extension; terminal commands above need no environment activation. Existing venv must be Python 3.12. `start.bat` checks it, installs pins, starts FastAPI and opens **http://127.0.0.1:8000** for offline setup, or **http://127.0.0.1:8765** when the private P13 live configuration is approved. Use another terminal for setup/tests; keep the server terminal open. Ctrl+C stops your app. To change port, set `$env:PROOFPORT_PORT = '8765'` before `.\start.bat`. `.env.example` defaults to `LLM_MODE=mock`; changing it to live alone does not enable paid calls or live UI migration.

### Docker images and Python readiness

Start Docker Desktop. Explicitly prepare the images you need; all ten judge scenarios use this complete list:
```powershell
docker info --format '{{.OSType}}'
docker pull python:2.7
docker pull python:3.12-slim
docker pull python:3.13-slim
docker pull php:7.4.33-cli
docker pull php:8.3.36-cli
docker build -t proofport-bandit:1.8.6 -f backend/sandbox/Dockerfile.bandit backend/sandbox
.venv/Scripts/python.exe -c "from backend.core.versions import VersionRegistry; r=VersionRegistry(); print(r.verify('2.7')); print(r.verify('3.12')); print(r.verify('3.13'))"
```
Docker info must say `linux`. Images alone mean available, not verified; the explicit receipt checks execute only in Docker. For Python migration, refresh **Migration → Run control → Python → legacy_shop → 2.7 → 3.12**. Select fixture `legacy_shop_py27_py312` and cases `legacy_shop_golden`, then **Check readiness → Start run**. This is authored **offline fixture migration**, not a new Meta answer. The app never pulls images automatically.

### Run PHP

After the PHP image setup above, create the local UI readiness receipt and try CLI operations:
```powershell
.venv/Scripts/python.exe -m backend.php verify-demo
.venv/Scripts/python.exe -m backend.php migration
.venv/Scripts/python.exe -m backend.php audit
.venv/Scripts/python.exe -m backend.php compatibility --level behavior
```
`verify-demo` checks real E2E and records local proof. CLI defaults to the owned `tests/fixtures/php_shop`; no host PHP or Composer installation is needed. Compatibility checks the **unchanged** source; an incompatible legacy demo can correctly return failure. Migration checks a translated working copy. In the UI select **PHP → php_shop → Migration → 7.4 → 8.3**, fixture `php_shop_74_83`, cases `php_shop_golden`, then preflight/start. Audit and Compatibility are separate operations; use only options currently offered by capabilities. Optional security fixture: `php_shop_security`. Read `syntax_passed`, `tests_passed`, `behavior_verified` separately: null means not run, never success.

### Your own server — private Linux access

Use a host you administer with **SSH access, Python 3.12, Git, Docker Engine and permission to run Docker**; no public hosting/authentication layer is provided. On that server, clone/open the repo, then run:
```bash
git clone https://github.com/kasestuck/MetaAI-proofport.git
cd MetaAI-proofport
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
test -f .env || cp .env.example .env
# Run the docker pull/build commands above here, on the server.
.venv/bin/python -c "from backend.core.versions import VersionRegistry; r=VersionRegistry(); print(r.verify('2.7')); print(r.verify('3.12')); print(r.verify('3.13'))"
.venv/bin/python -m backend.php verify-demo
.venv/bin/python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8765 --workers 1
```
Keep that process running. From your own computer, replace the two server placeholders and open an SSH tunnel:
```powershell
ssh -N -L 8765:127.0.0.1:8765 "[SERVER_USER]@[SERVER_HOST]"
```
Open **http://127.0.0.1:8765** locally; keep SSH running. VS Code Remote SSH is optional, not required by Proofport. Keep the app bound to loopback: no API user authentication exists, and public/domain hosting is unsupported. Do not expose port 8765 or mount the Docker socket into projects. Use one worker because run locks/state are in memory; restarting loses the API run list, while retained disk reports remain. These are operator instructions, not a claim that this repo was deployed/tested on your Linux host. No server/settings changes are made by reading them.

### Try Proofport — 10 Judge Test Scenarios

To test correctly, run from the repository root in this order. Never execute the legacy sample or model candidates directly on Windows/Linux host:
```powershell
.venv/Scripts/python.exe -m pytest -q -m "not docker"
$frontendTests = (Get-ChildItem frontend/tests -Filter '*.test.cjs').FullName
node --test $frontendTests
.venv/Scripts/python.exe -m pip check
judge_tests\run.bat
judge_tests\run.bat --scenario 07
```
The last checked code release had **554 fast backend tests**, **73 frontend tests**, and all ten mandatory judge checks passed: **5 PASS, 5 NEEDS_REVIEW, 0 FAIL/SKIP**. These are historical observations, not a guarantee on another machine. See [Try Proofport — 10 Judge Test Scenarios](judge_tests/README.md) for all cases. PASS means that scenario's required assertions passed; expected NEEDS_REVIEW verifies rejection/rollback, not remediation. Mandatory SKIP/FAIL makes the judge exit nonzero. Results live in ignored `backend/.work/judge-<id>/`. Verify the latest saved summary/receipts/evidence without executing code:
```powershell
$summary = Get-ChildItem backend/.work/judge-*/summary.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
.venv/Scripts/python.exe judge_tests/runner.py --verify-summary $summary.FullName
```
Optional full Docker backend matrix (slower; no image auto-downloads); inspect missing-prerequisite skips rather than claiming them passed:
```powershell
$env:PROOFPORT_DOCKER_TESTS = '1'
.venv/Scripts/python.exe -m pytest -q -m docker
Remove-Item Env:\PROOFPORT_DOCKER_TESTS
```
On Linux, use `.venv/bin/python`, `node --test frontend/tests/*.test.cjs` and `.venv/bin/python judge_tests/runner.py`; enable Docker tests with `PROOFPORT_DOCKER_TESTS=1 .venv/bin/python -m pytest -q -m docker`. Saved genuine-candidate Docker tests need the original local live artifacts; a fresh clone may skip them. Never substitute fixtures as live evidence. UI smoke: check Python/PHP selection, preflight errors, real run completion, final HTML/JSON export and independent evidence verification; replay must remain labelled. [API contract](backend/API_CONTROL_PLANE.md) · [Runbook](docs/DEMO_RUNBOOK.md) · [Live approval/setup](backend/META_LIVE_READINESS.md)

## Architecture

```text
Browser -> FastAPI -> immutable RunSpec / readiness / single-run gate
  -> Python/PHP adapter -> analyze -> record -> translate <-> Docker verify
       -> LLMClient (approved Meta CLI / mock / explicit replay)
  -> security proposal / rescan / decision -> SHA-256 + evidence -> HTML/JSON
```
FastAPI serves the static dashboard and both API generations. Project policy restricts paths, profiles and runtimes. Adapters reuse recording, comparison and existing tests. Docker uses non-root, no network, read-only mounts and resource/time limits. The verifier decides acceptance; failed candidates roll back. Reports preserve provenance and local integrity receipts.

## Limitations

- Verified migration pairs are Python 2.7 → 3.12 and PHP 7.4 → 8.3; no universal framework/project support.
- Docker is mandatory for execution; no reduced-isolation host fallback. Finite cases do not prove equivalence for all inputs.
- Behavior/API/configuration/crypto changes remain `needs_review`; the genuine eval proposal failed verification.
- Python 2 Bandit coverage is partial; PHP rules are lexical. Zero findings is not proof of safety.
- Hashes prove local consistency, not external attestation; Docker does not prevent every kernel exploit. See [security policy](SECURITY.md).

## AI assistance

Code was written with help from Codex and Claude Code; they are tools, not team members.

## License

[MIT](LICENSE), copyright 2026. Preserve the sample license and [third-party notices](THIRD_PARTY_NOTICES.md).
