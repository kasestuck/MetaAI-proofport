# Backend skeleton

Python 3.12 is required. Run `start.bat` from any directory. It creates `.venv`,
installs `backend/requirements.txt`, serves `http://127.0.0.1:8000`, and opens
the browser after the server is ready. Ctrl+C stops the server. API docs: `/docs`.
If port 8000 is occupied, set `PROOFPORT_PORT=8001` in the terminal before
starting the batch file. The browser uses the selected port.

The worker is **simulated**, even when `LLM_MODE=live`. It never executes or
modifies source files. Migration/test counts, security remediation, tokens, and
costs in run metrics are demo estimates. SHA-256 hashes and the evidence chain
are real. Each run rechecks all original files before finishing. Data lives in
memory and disappears when the server stops. Only one run can be active.

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
Replay and the real sandbox/pipeline belong to later milestones. Simulation
reports always show reduced isolation because no sandbox runs.

Run tests from the repo root:

```powershell
.venv/Scripts/python.exe -m pytest tests -q
```
