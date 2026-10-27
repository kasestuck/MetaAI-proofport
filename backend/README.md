# Backend skeleton

Python 3.12 is required. Run `start.bat` from any directory. It creates `.venv`,
installs `backend/requirements.txt`, serves `http://127.0.0.1:8000`, and opens
the browser after the server is ready. Ctrl+C stops the server. API docs: `/docs`.
If port 8000 is occupied, set `PROOFPORT_PORT=8001` in the terminal before
starting the batch file. The browser uses the selected port.

The real migration pipeline is **not implemented**. By default a run only
inventories directory sources and hashes actual files, then fails with
`docker_unavailable` or `pipeline_unavailable`. Dynamic tests, migration, model
calls, and security scans do not run; their metrics stay zero. No code is
executed on the host. Empty findings mean not scanned. Data is in memory and
disappears when the server stops. Only one run can be active.

For the original frontend plumbing demo, explicitly set both server settings:

```dotenv
PROOFPORT_PIPELINE=simulation
LLM_MODE=mock
```

Only that mode generates simulated green modules, test counts, security fixes,
tokens and costs. Its reports/events are labelled. It is rejected with live or
replay mode and does not prove migration. SHA-256 hashes and evidence chains
remain real in both modes. `PROOFPORT_PIPELINE=verify` is the default.

The provided checkout has no `docs/BRIEF.md` or `samples/legacy_shop`. The API
implements section 8 of the supplied full project specification. Add the real
samples to use `{"source_path":"samples/legacy_shop"}` with `POST /api/runs`.
Other local Python source folders also work. Missing sources return
`source_not_found`; no sample hashes are invented. Tests create their own
original Python 2 fixtures in temporary folders.

`backend.llm.client.LLMClient` defaults to offline `mock` mode. For real calls,
create an untracked `.env` in the repo root:

```dotenv
LLM_MODE=live
MODEL_API_KEY=your-key
MODEL_NAME=your-model
MODEL_BASE_URL=https://api.meta.ai/v1
PRICE_IN_PER_MTOK=1.25
PRICE_OUT_PER_MTOK=4.25
```

`LLM_MODE=mock` needs no key or model and incurs no charges. Environment
variables override `.env`. `complete(system, user, json_mode=False)` returns
text. `calls`, `tokens_in`, `tokens_out`, and `cost_usd` track actual client
usage; call records hold prompt hashes and duration, never prompt text or keys.
Live calls have a 30-second timeout and at most two SDK retries with backoff.
Replay has not been implemented: the health mode reports configuration, not
verified support. The real sandbox/pipeline remains blocked on prerequisites;
neither mock nor replay can substitute for execution. Reports show reduced
isolation because no sandbox runs; this never enables a host subprocess fallback.

Audit, concrete file plan, prerequisites, and proposed (unimplemented) API
extensions: [ARCHITECTURE.md](ARCHITECTURE.md). Check local P0 readiness without
executing sources, pulling images, or calling a model:

```powershell
.venv/Scripts/python.exe -m backend.core.readiness
```

Exit code 2 means not ready. It reports no credentials and does not infer
runtime correctness from image presence or a configured model name.

Run tests from the repo root:

```powershell
.venv/Scripts/python.exe -m pytest tests -q
```
