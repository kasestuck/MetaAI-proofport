# Proofport Console (frontend)

Static dashboard for the Proofport backend. Plain HTML, CSS and vanilla
JavaScript: no build step, no Node.js, no CDN, no web fonts, no requests to
third-party hosts. The backend serves this folder at `/` when it exists
(`backend/api/main.py`), so the console and API share one origin.

The source of truth for every API field and label used here is
[`backend/FRONTEND_HANDOFF.md`](../backend/FRONTEND_HANDOFF.md).

## Run

```bat
start.bat
```

or, with an existing `.venv`:

```bash
python -m backend.launcher
```

Open http://127.0.0.1:8000. The pipeline and LLM mode are **server settings**
(`.env` or environment, read at startup). Offline examples:

| Goal | Environment |
| --- | --- |
| UI demo, no Docker work | `LLM_MODE=mock`, `PROOFPORT_PIPELINE=simulation` |
| Offline fixture migration (Docker) | `LLM_MODE=mock`, `PROOFPORT_PIPELINE=fixtures`, `PROOFPORT_CASES_FILE=tests/fixtures/legacy_shop/cases.json`, `PROOFPORT_FIXTURE_FILE=tests/fixtures/legacy_shop/patches.json` |
| Compatibility check (Docker) | `PROOFPORT_PIPELINE=compatibility`, `PROOFPORT_TARGET_VERSION=3.13`, see `backend/UNIVERSAL.md` |

Do not enable `verify` + `live` with a real key just to look at the UI: that
path can send paid requests. After editing frontend files, hard-refresh the
browser (Ctrl+F5); StaticFiles allows the browser to cache scripts.

## Structure

```
index.html            Shell: sidebar, top bar, five view containers
css/tokens.css        Palette, type scale, spacing, motion (reduced-motion aware)
css/base.css          Reset, shell layout, responsive breakpoints (1180 / 760 px)
css/components.css    Cards, badges, buttons, tables, progress, banners, toasts
css/views.css         Stepper, module table, timeline, findings, evidence
js/config.js          Deployment profile (poll interval, optional declared pipeline, path presets)
js/util.js            h() DOM builder (text only), icons, formatters, small UI builders
js/api.js             The five endpoints + ApiError normalisation
js/labels.js          Honest labelling rules: statuses, provenance, error hints
js/integrity.js       Browser re-verification of the evidence hash chain (WebCrypto)
js/store.js           State, health loop, sequential polling, finalisation, replay
js/app.js             Hash router, banners, mode switch, render scheduling
js/views/*.js         overview, migration, security, compatibility, evidence (+ shared)
```

Scripts are classic (not ES modules), loaded in order, and attach to one
global `window.PP`. This avoids MIME-type problems with `.js` on Windows and
needs no bundler. A view is `{ title, sub, mount(root), update(state) }`.

## API usage

| Endpoint | Used for |
| --- | --- |
| `GET /api/health` | Every 5 s: backend online/offline, Docker (at server start), `llm_mode` |
| `POST /api/runs` | Start form: only `source_path` and `max_iterations`. Never retried automatically |
| `GET /api/runs/{id}` | Polled every 1 s, sequentially, with backoff up to 10 s on errors |
| `GET /api/runs/{id}/events?since=N` | Same loop; cursor per run, de-duplicated by `seq` |
| `GET /api/runs/{id}/report?format=json` | After `done`/`failed`, retried up to 4 times until state, events and report agree |
| `GET /api/runs/{id}/report?format=html\|json` | Download links in Evidence |

No other routes or request fields exist; do not add them on the frontend
without a backend change (see handoff §11).

## Modes and honesty rules

- **Live / Mock / Replay** switch in the top bar. Live and Mock reflect
  `llm_mode` from health. Replay is active while viewing a saved report JSON
  loaded from disk ("Open saved report"); nothing is re-executed. Backend
  `LLM_MODE=replay` is shown as "not implemented".
- Run provenance comes from the final report (`simulation`,
  `settings.pipeline`, `verification`). Before it arrives the label is "Mode
  not determined", unless `config.deployment.pipeline` declares it or the
  first event is marked `SIMULATED`.
- "Live Meta AI · verified scope" is shown only when the report says
  `ai_migration === true` with model calls > 0, status `done`, chain intact
  and originals unchanged.
- Simulated metrics carry a SIMULATED tag. Zero findings in
  compatibility/analyze/static runs read "not scanned". Tri-state checks show
  `null` as "Not confirmed", never as pass or fail.
- Untrusted backend text (paths, scanner output, diffs, events) is rendered
  only via `textContent`.

## Known limitations (API, not UI)

- Pipeline, target Python and fixtures cannot be chosen per run; the target
  field is informational.
- No run list, cancel, retry or upload; runs live in backend memory and become
  `404` after a restart (the console says so and clears the stored id).
- CWE, confidence, test outcomes, comparisons and fix attempts exist only in
  the final report, so these sections fill in after the run ends.
- No approve/reject endpoints for security decisions; the UI shows none.
- Phases shorter than the poll interval may appear as "not observed"; they are
  also inferred from evidence events.
