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
    // Runs opened in this browser, newest first. Live entries persist in
    // localStorage (ids only); replay entries keep the report in memory only.
    // This is not server history: the backend forgets runs on restart.
    history: [],
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
      trackHistory();
      for (const fn of listeners) {
        try { fn(state); } catch (err) { console.error("[proofport] render failed", err); }
      }
    });
  }

  // ---------- Persistence of the last known run id (browser memory only) ----------
  function remember(run) {
    try {
      localStorage.setItem(cfg.storageKey, JSON.stringify({ id: run.id, source: run.source, maxIterations: run.maxIterations, startedAt: run.startedAt, apiMode: run.apiMode, instanceId: run.instanceId, language: run.language }));
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

  // ---------- Run list (this browser only) ----------
  const HISTORY_KEY = cfg.storageKey + ".history";
  const HISTORY_MAX = 12;

  function loadHistory() {
    try {
      const list = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(list) ? list.filter((e) => e && typeof e.id === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(e.id)).slice(0, HISTORY_MAX) : [];
    } catch (_) { return []; }
  }

  function saveHistory() {
    try {
      const live = state.history.filter((e) => e.origin === "live").map(({ report, ...rest }) => rest);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(live));
    } catch (_) { /* ignore */ }
  }

  /** Upsert the current run into the list; called before every render. */
  function trackHistory() {
    const run = state.run;
    if (!run) return;
    const key = run.origin === "replay" ? "replay:" + run.fileName : run.id;
    const st = run.state;
    const entry = {
      key, id: run.id, origin: run.origin, source: run.source, fileName: run.fileName,
      startedAt: run.startedAt, maxIterations: run.maxIterations,
      apiMode: run.apiMode, instanceId: run.instanceId,
      language: PP.labels.language(run),
      status: run.lost ? "lost" : run.control ? run.control.lifecycle : st ? st.status : "connecting",
      events: run.events.length,
      pipeline: run.control ? run.control.parameters.operation + " · " + run.control.execution.effective : run.report ? (run.report.simulation ? "simulation" : run.report.settings && run.report.settings.pipeline) : null,
      report: run.origin === "replay" ? run.report : undefined,
    };
    const index = state.history.findIndex((e) => e.key === key);
    const before = index >= 0 ? JSON.stringify([state.history[index].status, state.history[index].events, state.history[index].pipeline]) : null;
    if (index >= 0) state.history[index] = entry;
    else state.history.unshift(entry);
    if (state.history.length > HISTORY_MAX) state.history.length = HISTORY_MAX;
    if (before !== JSON.stringify([entry.status, entry.events, entry.pipeline])) saveHistory();
  }

  /** Re-open a run from the list: re-attach to the server, or re-show a replayed report. */
  function openHistory(key) {
    const entry = state.history.find((e) => e.key === key);
    if (!entry) return;
    const run = state.run;
    if (run && (run.origin === "replay" ? "replay:" + run.fileName : run.id) === key) return;
    if (entry.origin === "replay" && entry.report) openReplayData(entry.report, entry.fileName);
    else if (entry.origin === "live") attach(entry.id, Object.assign({}, entry, { restored: true }));
  }

  function removeHistory(key) {
    state.history = state.history.filter((e) => e.key !== key);
    saveHistory();
    const run = state.run;
    if (run && (run.origin === "replay" ? "replay:" + run.fileName : run.id) === key) clearRun();
    else emit();
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
      apiMode: meta && meta.apiMode || (state.control && state.control.mode === "v1" ? "v1" : "legacy"),
      instanceId: meta && meta.instanceId || null,
      control: null,
      language: meta && meta.language || null,
      backendFinalized: false,
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
    run.chain = { status: "checking", count: run.events.length };
    PP.integrity.verifyChain(run.events).then((result) => {
      if (version !== chainVersion || state.run !== run) return;
      run.chain = result;
      emit();
    }).catch((err) => {
      if (version !== chainVersion || state.run !== run) return;
      run.chain = { status: "unavailable", count: run.events.length, reason: String(err.message || err) };
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

  async function snapshotFor(run, token) {
    if (run.apiMode !== "v1") return api.getRun(run.id);
    const details = await api.runDetails(run.id);
    if (token !== pollToken) return details && details.state;
    if (!details || details.run_id !== run.id || !details.state || !details.parameters || !details.execution
      || !details.result || typeof details.instance_id !== "string" || typeof details.finalized !== "boolean"
      || !["queued", "running", "finalizing", "done", "failed"].includes(details.lifecycle)
      || (TERMINAL.has(details.lifecycle) && details.state.status !== details.lifecycle)) {
      throw new api.ApiError("parse", 200, "unexpected_response", "Invalid v1 run details; legacy fallback is disabled.");
    }
    if (run.instanceId && details.instance_id !== run.instanceId) {
      PP.control.observeInstance(details.instance_id);
      run.lost = true;
      throw new api.ApiError("control", 0, "instance_changed", "Backend instance changed. This run cannot be resumed on the new instance.");
    }
    run.instanceId = details.instance_id;
    run.control = details;
    run.language = details.parameters.language || "python";
    run.backendFinalized = details.finalized;
    remember(run);
    return details.state;
  }

  function isFinished(run, snapshot) {
    return TERMINAL.has(snapshot.status) && (run.apiMode !== "v1"
      || (run.control && run.control.finalized === true && TERMINAL.has(run.control.lifecycle)));
  }

  async function pollLoop(run, token) {
    run.polling = true;
    let delay = cfg.pollIntervalMs;
    while (token === pollToken && !run.lost) {
      try {
        const snapshot = await snapshotFor(run, token);
        if (token !== pollToken) return;
        const batch = await api.getEvents(run.id, run.cursor);
        if (token !== pollToken) return;
        applyState(run, snapshot);
        applyEvents(run, batch);
        run.pollError = null;
        delay = cfg.pollIntervalMs;
        if (state.health.status !== "online") checkHealth();
        emit();
        if (isFinished(run, snapshot)) {
          run.backendFinalized = true;
          await finalize(run, token);
          return;
        }
      } catch (err) {
        if (token !== pollToken) return;
        if ((err.kind === "http" && err.status === 404) || err.code === "instance_changed") {
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
        const snapshot = await snapshotFor(run, token);
        const batch = await api.getEvents(run.id, run.cursor);
        if (token !== pollToken) return;
        applyState(run, snapshot);
        const newEvents = applyEvents(run, batch);
        const reportEvents = Array.isArray(report.events) ? report.events : [];
        const consistent = !newEvents
          && isFinished(run, snapshot)
          && report.state && report.state.status === snapshot.status
          && PP.integrity.canonical(reportEvents) === PP.integrity.canonical(run.events);
        if (!consistent) throw new api.ApiError("parse", 200, "report_inconsistent", "The report and final state/events are not consistent. Retry report retrieval.");
        run.report = report;
        run.reportStatus = "ready";
        run.reportError = null;
        verifyChainLater(run);
        break;
      } catch (err) {
        if (token !== pollToken) return;
        if ((err.kind === "http" && err.status === 404) || err.code === "instance_changed") { run.lost = true; forget(); run.reportStatus = "error"; run.reportError = err; break; }
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
    if (data.events.some((e) => !e || typeof e !== "object" || !Number.isSafeInteger(e.seq)
      || typeof e.prev_hash !== "string" || typeof e.entry_hash !== "string")) return "Malformed evidence entry.";
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
    openReplayData(data, file.name || "report.json");
    PP.util.toast("Saved report loaded", "Replaying " + (file.name || "report.json") + " locally. Nothing was sent to the backend.", "ok");
    return true;
  }

  function openReplayData(data, fileName) {
    pollToken++; // stop polling a live run; it keeps running on the server
    const match = /proofport-([A-Za-z0-9]+)\.json$/.exec(fileName);
    const run = newRun(match ? match[1] : "saved-report", null, "replay");
    run.fileName = fileName;
    applyState(run, data.state);
    // Replay must preserve duplicates/order. Polling deduplication would hide
    // corruption and could turn an invalid saved chain into a green result.
    run.events = data.events.slice();
    run.seqs = new Set(run.events.map((e) => e.seq));
    run.cursor = run.events.length ? run.events[run.events.length - 1].seq : 0;
    verifyChainLater(run);
    run.report = data;
    run.reportStatus = "ready";
    run.finalized = true;
    state.run = run;
    emit();
  }

  function init() {
    state.history = loadHistory().map((e) => Object.assign({}, e, { key: e.id, origin: "live" }));
    emit();
    PP.control.init().then(() => healthLoop());
  }

  PP.store = { state, subscribe, emit, init, startRun, attach, clearRun, retryReport, loadReplay, leaveReplay, recall, openHistory, removeHistory, TERMINAL };
})(window.PP);
