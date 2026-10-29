/*
 * Application state, backend health loop, run polling and saved-report replay.
 *
 * Polling contract (FRONTEND_HANDOFF.md §8):
 *  - sequential (never overlapping) GET state + GET events?since=cursor;
 *  - per-run cursor, events de-duplicated by seq;
 *  - exponential backoff on errors, 404 => run lost (backend restarted);
 *  - on done/failed: final fetch of state/events/report JSON, retried a few
 *    times because the worker may still append final events;
 *  - POST /api/runs is never retried automatically.
 *
 * Views subscribe with PP.store.subscribe(fn) and read PP.store.state.
 */
(function (PP) {
  "use strict";

  const { api } = PP;
  const cfg = PP.config;
  const TERMINAL = new Set(["done", "failed"]);

  const state = {
    health: { status: "unknown", data: null, error: null, checkedAt: 0 },
    run: null,
    starting: false,
    startError: null,
  };

  const listeners = new Set();
  let emitQueued = false;

  function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  // Coalesce synchronous bursts of changes into one render. A microtask (not
  // requestAnimationFrame) so state still renders while the tab is hidden.
  function emit() {
    if (emitQueued) return;
    emitQueued = true;
    queueMicrotask(() => {
      emitQueued = false;
      for (const fn of listeners) {
        try { fn(state); } catch (err) { console.error("[proofport] render failed", err); }
      }
    });
  }

  // ---------- Persistence of the last known run id (browser memory only) ----------
  function remember(run) {
    try {
      localStorage.setItem(cfg.storageKey, JSON.stringify({ id: run.id, source: run.source, maxIterations: run.maxIterations, startedAt: run.startedAt }));
    } catch (_) { /* storage may be unavailable; non-critical */ }
  }
  function recall() {
    try {
      const raw = localStorage.getItem(cfg.storageKey);
      const data = raw ? JSON.parse(raw) : null;
      return data && typeof data.id === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(data.id) ? data : null;
    } catch (_) { return null; }
  }
  function forget() {
    try { localStorage.removeItem(cfg.storageKey); } catch (_) { /* ignore */ }
  }

  // ---------- Health ----------
  async function checkHealth() {
    try {
      const data = await api.health();
      const wasOffline = state.health.status !== "online";
      state.health = { status: "online", data, error: null, checkedAt: Date.now() };
      emit();
      return wasOffline;
    } catch (err) {
      state.health = { status: "offline", data: state.health.data, error: err, checkedAt: Date.now() };
      emit();
      return false;
    }
  }

  async function healthLoop() {
    for (;;) {
      const cameOnline = await checkHealth();
      if (cameOnline && !state.run) restoreRemembered();
      await PP.util.sleep(cfg.healthIntervalMs);
    }
  }

  // ---------- Runs ----------
  let pollToken = 0; // incremented to cancel any in-flight polling loop

  function newRun(id, meta, origin) {
    return {
      id,
      origin: origin || "live",
      source: meta && meta.source || null,
      maxIterations: meta && meta.maxIterations || null,
      startedAt: meta && meta.startedAt || Date.now(),
      restored: !!(meta && meta.restored),
      state: null,
      events: [],
      seqs: new Set(),
      cursor: 0,
      phasesSeen: [],
      report: null,
      reportStatus: "idle",
      reportError: null,
      polling: false,
      pollError: null,
      lost: false,
      finalized: false,
      chain: null,
      fileName: null,
    };
  }

  function applyState(run, snapshot) {
    run.state = snapshot;
    const phase = snapshot && snapshot.phase;
    if (phase && run.phasesSeen[run.phasesSeen.length - 1] !== phase) run.phasesSeen.push(phase);
  }

  function applyEvents(run, batch) {
    if (!Array.isArray(batch) || !batch.length) return false;
    let added = false;
    for (const event of batch) {
      if (!event || typeof event.seq !== "number" || run.seqs.has(event.seq)) continue;
      run.seqs.add(event.seq);
      run.events.push(event);
      added = true;
    }
    if (added) {
      run.events.sort((a, b) => a.seq - b.seq);
      run.cursor = run.events[run.events.length - 1].seq;
      verifyChainLater(run);
    }
    return added;
  }

  let chainVersion = 0;
  function verifyChainLater(run) {
    const version = ++chainVersion;
    PP.integrity.verifyChain(run.events).then((result) => {
      if (version !== chainVersion || state.run !== run) return;
      run.chain = result;
      emit();
    });
  }

  function attach(id, meta) {
    const token = ++pollToken;
    const run = newRun(id, meta, "live");
    state.run = run;
    remember(run);
    emit();
    pollLoop(run, token);
  }

  async function pollLoop(run, token) {
    run.polling = true;
    let delay = cfg.pollIntervalMs;
    while (token === pollToken) {
      try {
        const snapshot = await api.getRun(run.id);
        if (token !== pollToken) return;
        const batch = await api.getEvents(run.id, run.cursor);
        if (token !== pollToken) return;
        applyState(run, snapshot);
        applyEvents(run, batch);
        run.pollError = null;
        delay = cfg.pollIntervalMs;
        if (state.health.status !== "online") checkHealth();
        emit();
        if (TERMINAL.has(snapshot.status)) {
          await finalize(run, token);
          return;
        }
      } catch (err) {
        if (token !== pollToken) return;
        if (err.kind === "http" && err.status === 404) {
          run.lost = true;
          run.polling = false;
          run.pollError = err;
          forget();
          emit();
          return;
        }
        run.pollError = err;
        if (err.kind === "network") state.health = Object.assign({}, state.health, { status: "offline", error: err });
        delay = Math.min(delay * 2, cfg.maxBackoffMs);
        emit();
      }
      await PP.util.sleep(delay);
    }
  }

  async function finalize(run, token) {
    run.reportStatus = "loading";
    emit();
    const attempts = 4;
    for (let i = 0; i < attempts && token === pollToken; i++) {
      try {
        const report = await api.getReport(run.id);
        if (token !== pollToken) return;
        const snapshot = await api.getRun(run.id);
        const batch = await api.getEvents(run.id, run.cursor);
        if (token !== pollToken) return;
        applyState(run, snapshot);
        const newEvents = applyEvents(run, batch);
        run.report = report;
        run.reportStatus = "ready";
        run.reportError = null;
        const reportEvents = Array.isArray(report.events) ? report.events : [];
        const consistent = !newEvents
          && report.state && report.state.status === snapshot.status
          && reportEvents.length === run.events.length;
        if (consistent || i === attempts - 1) {
          applyEvents(run, reportEvents); // fills any gap; de-duplicated by seq
          break;
        }
      } catch (err) {
        if (token !== pollToken) return;
        if (err.kind === "http" && err.status === 404) { run.lost = true; forget(); break; }
        run.reportError = err;
        if (i === attempts - 1) run.reportStatus = "error";
      }
      emit();
      await PP.util.sleep(800);
    }
    if (token !== pollToken) return;
    run.polling = false;
    run.finalized = true;
    emit();
  }

  /** Manually retry fetching the report after a report error. */
  function retryReport() {
    const run = state.run;
    if (!run || run.origin !== "live" || run.lost) return;
    const token = ++pollToken;
    run.finalized = false;
    pollLoop(run, token);
  }

  async function startRun(sourcePath, maxIterations) {
    if (state.starting) return;
    state.starting = true;
    state.startError = null;
    emit();
    try {
      const result = await api.startRun(sourcePath, maxIterations);
      if (!result || typeof result.run_id !== "string") throw new api.ApiError("parse", 200, "unexpected_response", "The backend did not return a run_id.");
      attach(result.run_id, { source: sourcePath, maxIterations, startedAt: Date.now() });
      PP.util.toast("Run started", "Run " + result.run_id.slice(0, 8) + " accepted by the backend.", "ok");
    } catch (err) {
      if (err.kind === "network") {
        // POST is not idempotent: the run may have started even though the response was lost.
        err.message += " The request may still have reached the server; do not resend blindly.";
      }
      state.startError = err;
      PP.util.toast("Run not started", err.message, "err");
    } finally {
      state.starting = false;
      emit();
    }
  }

  function restoreRemembered() {
    const saved = recall();
    if (saved) attach(saved.id, Object.assign({}, saved, { restored: true }));
  }

  function clearRun() {
    pollToken++;
    if (state.run && state.run.origin === "live") forget();
    state.run = null;
    state.startError = null;
    emit();
  }

  /** Return from a replayed report to the last remembered live run, if any. */
  function leaveReplay() {
    pollToken++;
    state.run = null;
    emit();
    restoreRemembered();
  }

  // ---------- Replay of a saved report (local file, read-only) ----------
  function validateReport(data) {
    if (!data || typeof data !== "object") return "The file is not a JSON object.";
    if (!data.state || typeof data.state !== "object" || !Array.isArray(data.state.modules)) return "Missing `state.modules`; this is not a Proofport report.";
    if (!Array.isArray(data.events)) return "Missing `events` array.";
    if (!data.settings || typeof data.settings !== "object") return "Missing `settings`.";
    if (typeof data.simulation !== "boolean") return "Missing `simulation` flag.";
    return null;
  }

  async function loadReplay(file) {
    let data;
    try {
      if (file.size > 50 * 1024 * 1024) throw new Error("File is larger than 50 MB.");
      data = JSON.parse(await file.text());
    } catch (err) {
      PP.util.toast("Cannot open report", err.message, "err");
      return false;
    }
    const problem = validateReport(data);
    if (problem) {
      PP.util.toast("Cannot open report", problem, "err");
      return false;
    }
    pollToken++; // stop polling a live run; it keeps running on the server
    const match = /proofport-([A-Za-z0-9]+)\.json$/.exec(file.name || "");
    const run = newRun(match ? match[1] : "saved-report", null, "replay");
    run.fileName = file.name || "report.json";
    applyState(run, data.state);
    applyEvents(run, data.events);
    run.report = data;
    run.reportStatus = "ready";
    run.finalized = true;
    state.run = run;
    emit();
    PP.util.toast("Saved report loaded", "Replaying " + run.fileName + " locally. Nothing was sent to the backend.", "ok");
    return true;
  }

  function init() {
    healthLoop();
  }

  PP.store = { state, subscribe, emit, init, startRun, clearRun, retryReport, loadReplay, leaveReplay, recall, TERMINAL };
})(window.PP);
