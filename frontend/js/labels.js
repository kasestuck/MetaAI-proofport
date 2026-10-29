/*
 * Honest labelling rules (FRONTEND_HANDOFF.md §4, §5, §6, §7, §9).
 *
 * Everything that decides what the user is told about a run's provenance
 * lives here, so the rules can be reviewed in one place. Rule of thumb:
 * when the data is missing or ambiguous, say "not verified" / "unknown",
 * never "success".
 */
(function (PP) {
  "use strict";

  const RUN_STATUS = {
    queued: { label: "Queued", tone: "muted", desc: "Accepted; the worker has not started yet." },
    running: { label: "Running", tone: "info", desc: "The worker is executing." },
    done: { label: "Done", tone: "ok", desc: "The selected operation finished. Read the report before drawing conclusions." },
    failed: { label: "Failed", tone: "err", desc: "The run did not complete its required verification." },
  };

  const MODULE_STATUS = {
    pending: { label: "Pending", tone: "muted" },
    translating: { label: "Translating", tone: "info" },
    testing: { label: "Testing", tone: "info" },
    fixing: { label: "Retrying", tone: "warn" }, // migration retry, not a security fix
    green: { label: "Green", tone: "ok" },
    failed: { label: "Failed", tone: "err" },
  };

  const FINDING_STATUS = {
    open: { label: "Open", tone: "warn", desc: "Open warning; no verified fix." },
    fixed: { label: "Fixed", tone: "ok", desc: "A verified patch was accepted in the working copy. Originals are unchanged." },
    false_positive: { label: "False positive", tone: "muted", desc: "Classified with contextual justification." },
    needs_review: { label: "Needs review", tone: "warn", desc: "Manual decision required; not an accepted fix." },
    fix_reverted: { label: "Fix reverted", tone: "err", desc: "The attempt was rejected and rolled back." },
  };

  // `phase` is a free-form string; unknown values get a neutral label.
  const PHASES = [
    { id: "analyzing", label: "Analyze" },
    { id: "recording", label: "Record golden" },
    { id: "migrating", label: "Migrate" },
    { id: "security", label: "Security" },
    { id: "reporting", label: "Report" },
  ];

  const EVENT_TYPES = {
    run_started: { label: "Run started", tone: "info" },
    hashes_recorded: { label: "Hashes recorded", tone: "info" },
    golden_recorded: { label: "Golden recorded", tone: "info" },
    patch_applied: { label: "Candidate staged", tone: "muted" }, // staged ≠ accepted (handoff §3)
    model_call: { label: "Model call", tone: "info" },
    sandbox_run: { label: "Sandbox run", tone: "muted" },
    test_result: { label: "Test result", tone: "ok" },
    security_finding: { label: "Security finding", tone: "warn" },
    security_fix: { label: "Security fix", tone: "ok" },
    fix_reverted: { label: "Fix reverted", tone: "err" },
    error: { label: "Error", tone: "err" },
    run_finished: { label: "Run finished", tone: "info" },
  };

  const COMPAT_LEVEL = {
    not_verified: { label: "Compatibility not verified", tone: "muted" },
    syntax_compatible: { label: "Syntax accepted by the selected interpreter", tone: "info" },
    tests_passed: { label: "Existing tests passed (not golden equivalence)", tone: "info" },
    behavior_verified: { label: "Behavior matched on recorded cases", tone: "ok" },
  };

  // Actionable hints for known error codes. The list is open: unknown codes
  // are shown verbatim with the backend message.
  const ERROR_HINTS = {
    run_busy: "Another run is in progress on this server. Wait for it to finish; the backend has no queue.",
    source_not_found: "The path must exist on the backend machine (relative to the repository root or absolute).",
    source_unreadable: "The backend could not read the source folder.",
    source_empty: "The folder contains no Python modules.",
    source_changed: "Source files changed while being inspected. Try again once they are stable.",
    unsupported_migration_pair: "Migration supports only Python 2.7 → 3.12. Use the server's compatibility pipeline for other versions.",
    invalid_request: "The request was rejected by the backend validator.",
    pipeline_unavailable: "The server pipeline is not configured for this operation (for example PROOFPORT_CASES_FILE is missing). An operator must change the server configuration and restart.",
    offline_only: "Security fixtures require PROOFPORT_PIPELINE=fixtures and LLM_MODE=mock on the server.",
    docker_unavailable: "Docker is not available to the backend. Start Docker Desktop and restart the backend. There is no host-execution fallback.",
    model_unavailable: "The Meta model is not configured or reachable (key/model missing). No demonstration result is substituted.",
    run_not_found: "The run no longer exists on the server. Runs are kept in memory and are lost when the backend restarts.",
    run_not_finished: "The report becomes available after the run finishes.",
    evidence_corrupted: "The evidence log failed integrity verification. Results can no longer be trusted.",
    runtime_unavailable: "The required Python Docker image is not installed locally. Images are never pulled automatically.",
    unverified_version: "The Python runtime is available but not verified. An operator must run explicit runtime verification.",
    source_version_ambiguous: "The source Python version is ambiguous. An operator must set PROOFPORT_SOURCE_VERSION.",
    behavior_mismatch: "Recorded behavior differs on the target interpreter. See failed comparisons.",
    target_tests_failed: "Existing tests failed on the target interpreter.",
    target_syntax_incompatible: "The source does not compile on the selected target interpreter.",
    legacy_tests_failed: "The original test suite is empty or does not fully pass on Python 2.7.",
    insufficient_cases: "At least one module lacks golden coverage, so it cannot be marked green.",
    verification_failed: "A required verification step failed. See the verification details below.",
    network_error: "The backend is unreachable. Check that the server is running.",
    timeout: "The backend did not respond in time.",
  };

  function runStatus(status) {
    return RUN_STATUS[status] || { label: String(status || "Unknown"), tone: "muted", desc: "" };
  }
  function moduleStatus(status) {
    return MODULE_STATUS[status] || { label: String(status || "Unknown"), tone: "muted" };
  }
  function findingStatus(status) {
    return FINDING_STATUS[status] || { label: String(status || "Unknown"), tone: "muted", desc: "" };
  }
  function eventType(type) {
    return EVENT_TYPES[type] || { label: String(type || "event"), tone: "muted" };
  }
  function phaseLabel(phase) {
    const known = PHASES.find((p) => p.id === phase);
    return known ? known.label : (phase ? String(phase) : "—");
  }
  function errorHint(code) {
    return ERROR_HINTS[code] || null;
  }
  function compatLevel(level) {
    return COMPAT_LEVEL[level] || { label: level ? String(level) : "Unknown", tone: "muted" };
  }

  /** Tri-state check: true = confirmed, false = failed, null/undefined = not confirmed / not run. */
  function tri(value) {
    if (value === true) return { label: "Confirmed", tone: "ok", icon: "check" };
    if (value === false) return { label: "Failed", tone: "err", icon: "x" };
    return { label: "Not confirmed", tone: "muted", icon: "dash" };
  }

  /** Backend LLM_MODE as reported by /api/health (configuration, not a key/model check). */
  function llmMode(mode) {
    switch (mode) {
      case "live":
        return { id: "live", label: "Live", tone: "info", desc: "LLM_MODE=live is configured. The API does not verify the key, model or Meta availability." };
      case "mock":
        return { id: "mock", label: "Mock", tone: "warn", desc: "No Meta AI calls are made. Mock responses are not translations." };
      case "replay":
        return { id: "replay", label: "Replay", tone: "muted", desc: "LLM_MODE=replay is configured, but backend replay is not implemented." };
      default:
        return { id: null, label: "Unknown", tone: "muted", desc: "LLM mode unknown (backend not reachable)." };
    }
  }

  const PIPELINES = {
    simulation: { label: "Simulation", tone: "warn", desc: "Simulated migration, tests, fixes, tokens and cost. Only file hashes and the evidence chain are real." },
    fixtures: { label: "Offline fixtures", tone: "info", desc: "Pre-written patches verified in Docker. Not AI migration." },
    analyze: { label: "Offline analysis", tone: "info", desc: "Static analysis in Docker. No migration, no model calls." },
    audit: { label: "Security audit", tone: "info", desc: "Static Bandit scan in Docker. No fixes, no project execution." },
    compatibility: { label: "Compatibility check", tone: "info", desc: "Syntax, existing tests and optional golden comparison on a target interpreter. Code is not translated." },
    static_only: { label: "Not verified", tone: "muted", desc: "Only static inventory and hashing ran. Zeros mean not scanned, not success." },
    live: { label: "Live Meta path", tone: "warn", desc: "Live model path. AI results are claimed only when the report confirms model calls and passing checks." },
    verify: { label: "Docker verify (live translator)", tone: "warn", desc: "Requires Docker, golden cases and a live translator. Mock LLM mode does not translate." },
  };

  /**
   * Provenance of the current run. Priority:
   *   1. Final report (settings.pipeline + simulation + verification) — authoritative.
   *   2. Deployment profile from config.js — operator declared.
   *   3. Event log hints — only to label *more* conservatively (simulation).
   *   4. Unknown.
   */
  function provenance(run) {
    if (!run) return null;
    const replayPrefix = run.origin === "replay" ? "Saved report · " : "";
    const report = run.report;
    if (report) {
      const v = report.verification || {};
      const state = report.state || {};
      if (report.simulation === true) {
        return Object.assign({ id: "simulation", source: "report", simulated: true }, PIPELINES.simulation, { label: replayPrefix + "Simulation" });
      }
      const pipeline = (report.settings && report.settings.pipeline) || "static_only";
      if (pipeline === "live") {
        const calls = Number(v.model_calls) || 0;
        const trusted = state.status === "done" && v.ai_migration === true && calls > 0 && state.chain_intact === true && state.hashes && state.hashes.unchanged === true;
        return trusted
          ? { id: "live", source: "report", label: replayPrefix + "Live Meta AI · verified scope", tone: "ok", desc: `Model-produced result verified on the recorded scope (${calls} recorded model calls).` }
          : { id: "live", source: "report", label: replayPrefix + "Live Meta path · not verified", tone: "warn", desc: "The live path did not produce a verified AI migration. No AI result is claimed." };
      }
      const known = PIPELINES[pipeline] || { label: pipeline, tone: "muted", desc: "" };
      return Object.assign({ id: pipeline, source: "report" }, known, { label: replayPrefix + known.label });
    }
    const declared = PP.config.deployment && PP.config.deployment.pipeline;
    if (declared && PIPELINES[declared]) {
      return Object.assign({ id: declared, source: "config", simulated: declared === "simulation" }, PIPELINES[declared], { label: PIPELINES[declared].label + " (declared)" });
    }
    const first = (run.events || []).find((e) => e.type === "run_started");
    if (first && typeof first.detail === "string" && first.detail.startsWith("SIMULATED")) {
      return Object.assign({ id: "simulation", source: "events", simulated: true }, PIPELINES.simulation);
    }
    return { id: null, source: "none", label: "Mode not determined", tone: "muted", desc: "The API exposes the pipeline only in the final report. Labels update when the run finishes." };
  }

  /** True when metrics must be presented as simulated (handoff §4, §7). */
  function isSimulated(run) {
    const p = provenance(run);
    return !!(p && p.id === "simulation");
  }

  PP.labels = {
    PHASES, runStatus, moduleStatus, findingStatus, eventType, phaseLabel, errorHint, compatLevel, tri, llmMode, provenance, isSimulated,
  };
})(window.PP);
