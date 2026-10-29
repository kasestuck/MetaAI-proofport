/*
 * Deployment profile for the Proofport console.
 *
 * The backend decides the pipeline (PROOFPORT_PIPELINE) and LLM mode
 * (LLM_MODE) at server start; the API does not expose the pipeline before a
 * report exists (see backend/FRONTEND_HANDOFF.md §1, §7). An operator MAY
 * declare the pipeline here so the console can label runs before the final
 * report arrives. Leave `pipeline` as null when unknown: the UI then shows
 * "mode not determined" until the report's `settings.pipeline` is available.
 *
 * Never put API keys or credentials in this file.
 */
window.PP = window.PP || {};

window.PP.config = {
  // Same-origin API (the backend serves this folder at "/"). Use an absolute
  // origin only behind a proxy; the backend has no CORS middleware.
  apiBase: "",

  // Sequential polling interval for run state + events (handoff §8: 0.5–1 s;
  // product brief: 1–2 s).
  pollIntervalMs: 1000,

  // Health check interval while idle / while the backend is offline.
  healthIntervalMs: 5000,

  // Max backoff after network errors while polling a run.
  maxBackoffMs: 10000,

  // Per-request timeout. Reports can be large, so they get more time.
  requestTimeoutMs: 10000,
  reportTimeoutMs: 30000,

  deployment: {
    // One of: null | "verify" | "fixtures" | "simulation" | "analyze" | "audit" | "compatibility"
    pipeline: null,
  },

  // Demo project cards are defined in js/views/migration.js (PROJECTS).

  storageKey: "proofport.console.lastRun",
};
