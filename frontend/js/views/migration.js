/*
 * Run control mounts the v1 operation form. Only capabilities 404 reveals
 * the older, server-configured form and informational operation cards below.
 * Both modes share phases, events, module summaries and saved-report replay.
 *
 * The start area is mounted once (typing is never interrupted); everything
 * below it re-renders on each store update.
 */
(function (PP) {
  "use strict";

  const { h, icon, fmt, badge, card, progress, indeterminate } = PP.util;
  const L = PP.labels;
  const S = PP.views.shared;

  let root, dynamic, sourceInput, iterInput, startBtn, formStatus, projectsHost, opsHost, readinessHost;
  const prevModuleStatus = new Map(); // module name -> last status, for the "turned green" highlight
  let prevRunId = null;
  let legacyHost, controlForm;

  // ---------- Static descriptions ----------

  // Operations the backend can run. Exactly one is active per server start.
  const OPERATIONS = [
    {
      id: "migration", title: "Migration", iconName: "migration",
      pipelines: ["fixtures", "verify", "live", "simulation", "static_only"],
      text: "Python 2.7 → 3.12. Records golden behavior, migrates modules, verifies them in Docker and scans the result.",
      env: "PROOFPORT_PIPELINE=fixtures | verify | simulation",
    },
    {
      id: "audit", title: "Security Audit", iconName: "security",
      pipelines: ["audit"],
      text: "Static Bandit scan of the project in Docker. No code changes, no project execution.",
      env: "PROOFPORT_PIPELINE=audit",
    },
    {
      id: "compatibility", title: "Compatibility Check", iconName: "compatibility",
      pipelines: ["compatibility", "analyze"],
      text: "Checks syntax, existing tests and recorded behavior on a target Python version. Code is not translated.",
      env: "PROOFPORT_PIPELINE=compatibility (+ PROOFPORT_TARGET_VERSION)",
    },
  ];

  // Demo projects that exist in this repository (paths relative to the repo root).
  const PROJECTS = [
    { path: "samples/legacy_shop", name: "legacy_shop", lang: "Python 2.7",
      text: "Small legacy shop package with 10 existing unittest tests and 90 golden cases.",
      fits: ["Migration", "Security Audit"] },
    { path: "tests/fixtures/universal_py3", name: "universal_py3", lang: "Python 3",
      text: "Deterministic arithmetic module with 2 tests and recorded cases.",
      fits: ["Compatibility Check"] },
    { path: "tests/fixtures/security_subject", name: "security_subject", lang: "Python 3",
      text: "Command-execution module used to demonstrate verified security hardening.",
      fits: ["Security fixtures"] },
  ];

  // Codes that mean "the server is not configured for this", not "your project is broken".
  const CONFIG_ERRORS = {
    pipeline_unavailable: {
      title: "The server is not configured for this run",
      what: "The backend's current pipeline needs inputs that are not set. In the default verify pipeline that means golden cases (PROOFPORT_CASES_FILE) and a live translator; with LLM_MODE=mock nothing is translated.",
      fix: ["For an offline demo set PROOFPORT_PIPELINE=simulation (no Docker work) or fixtures with the legacy_shop cases and patches files.", "Restart the backend after changing .env."],
    },
    docker_unavailable: {
      title: "Docker is not available to the backend",
      what: "Real verification runs only inside Docker. There is no host-execution fallback.",
      fix: ["Start Docker Desktop.", "Restart the backend so it re-detects Docker."],
    },
    model_unavailable: {
      title: "The Meta model is not configured",
      what: "The live pipeline needs a Meta API key and model. No demonstration result is substituted.",
      fix: ["Use an offline pipeline (simulation or fixtures) for demos.", "Live mode can send paid requests; enable it deliberately."],
    },
    offline_only: {
      title: "Security fixtures need the offline fixtures pipeline",
      what: "PROOFPORT_SECURITY_FIXTURES works only with PROOFPORT_PIPELINE=fixtures and LLM_MODE=mock.",
      fix: ["Remove PROOFPORT_SECURITY_FIXTURES or switch to the fixtures pipeline, then restart."],
    },
    unsupported_migration_pair: {
      title: "Unsupported migration pair",
      what: "This pair is not supported for the selected language and operation.",
      fix: ["Select versions offered by backend capabilities, then check readiness again."],
    },
    runtime_unavailable: {
      title: "Required runtime image is missing",
      what: "The Docker image for the selected language/version is not installed. Images are never pulled automatically.",
      fix: ["An operator must install the image and restart."],
    },
    unverified_version: {
      title: "Runtime not verified",
      what: "The image exists but has not passed the backend's runtime self-tests.",
      fix: ["Ask the operator to follow the selected language's explicit verification guide, then refresh capabilities."],
    },
    source_version_ambiguous: {
      title: "Source Python version is ambiguous",
      what: "The backend could not determine one source version for this project.",
      fix: ["Set PROOFPORT_SOURCE_VERSION on the server and restart."],
    },
    invalid_settings: {
      title: "Invalid server settings",
      what: "A server setting (for example SANDBOX_TIMEOUT_SECONDS) is out of range.",
      fix: ["Fix the value in .env and restart."],
    },
  };

  // Six visual steps. Backend phases are free-form strings; "Verify" has no
  // phase of its own and is marked only by real test events.
  const STEPS = [
    { id: "analyze", label: "Analyze", phase: "analyzing", events: ["run_started", "hashes_recorded"], desc: "Inventory, hashes, static analysis" },
    { id: "record", label: "Record", phase: "recording", events: ["golden_recorded"], desc: "Golden behavior on the source Python" },
    { id: "migrate", label: "Migrate", phase: "migrating", events: ["patch_applied", "model_call"], desc: "Candidate code for the target" },
    { id: "verify", label: "Verify", phase: null, events: ["test_result"], desc: "Compile, tests, golden comparison" },
    { id: "security", label: "Security", phase: "security", events: ["security_finding", "security_fix", "fix_reverted"], desc: "Scanner warnings and fix decisions" },
    { id: "report", label: "Report", phase: "reporting", events: ["run_finished"], desc: "Hashes rechecked, report written" },
  ];

  function stepsFor(run) {
    if (L.language(run) !== "php") return STEPS;
    const p = L.parameters(run);
    const operation = p.operation || (p.mode || "").replace(/^php_/, "");
    return STEPS.filter((s) => operation === "audit" ? ["analyze", "security", "report"].includes(s.id)
      : operation === "compatibility" ? s.id !== "migrate" && s.id !== "security" && (s.id !== "record" || p.verification_level === "behavior") : true)
      .map((s) => Object.assign({}, s, {
        label: { analyze: "PHP files", record: "Golden cases", migrate: "Fixture migration", verify: "Verification", security: "Security findings", report: "Evidence" }[s.id],
        desc: { analyze: "PHP inventory, hashes and analysis", record: "Actual results on source PHP", migrate: "Authored patches · not Meta AI",
          verify: "Syntax, tests and selected behavior checks", security: "Limited PHP rules and patch decisions", report: "Report and evidence chain" }[s.id],
        phase: s.id === "verify" ? "testing" : s.phase,
        events: s.events.concat(s.id === "analyze" ? ["language_analysis"] : s.id === "security" ? ["security_scan"] : []),
      }));
  }

  /** Server pipeline as far as it is known: final report > operator declaration > unknown. */
  function knownPipeline(run) {
    if (run && run.control) return run.control.execution.effective === "offline" ? run.control.parameters.operation : run.control.execution.effective;
    if (run && run.report) return run.report.simulation ? "simulation" : (run.report.settings && run.report.settings.pipeline) || null;
    return (PP.config.deployment && PP.config.deployment.pipeline) || null;
  }

  // ---------- Start area (mounted once) ----------

  function selectProject(path) {
    sourceInput.value = path;
    sourceInput.removeAttribute("aria-invalid");
    renderProjects();
  }

  function renderProjects() {
    const current = sourceInput.value.trim();
    projectsHost.replaceChildren(...PROJECTS.map((p) => {
      const selected = current === p.path;
      return h("button", { class: "project-card", type: "button", "aria-pressed": String(selected), onclick: () => selectProject(p.path) },
        h("div", { class: "row-between" },
          h("span", { class: "project-name" }, p.name),
          h("span", { class: "project-check", "aria-hidden": "true" }, selected ? icon("check") : null)),
        h("div", { class: "project-path" }, p.path),
        h("div", { class: "project-text" }, p.text),
        h("div", { class: "row", style: { gap: "6px" } }, PP.util.tag(p.lang, "muted"), p.fits.map((f) => PP.util.tag(f, "info"))));
    }), h("div", { class: "project-custom field-hint" },
      PROJECTS.some((p) => p.path === current) ? "Or enter another server-local path in Advanced settings."
        : current ? h("span", null, "Custom path: ", h("code", null, current)) : "No project selected."));
  }

  function renderOperations(state) {
    const pipeline = knownPipeline(state.run);
    const active = OPERATIONS.find((op) => pipeline && op.pipelines.includes(pipeline));
    opsHost.replaceChildren(...OPERATIONS.map((op) => {
      const isActive = active === op;
      const qualifier = { simulation: " · simulation", static_only: " · not configured" }[pipeline];
      const status = isActive
        ? badge("Active on server" + (qualifier || ""), qualifier ? "warn" : "ok")
        : active ? badge("Not active on this server", "muted") : badge("Set by server", "muted");
      return h("div", { class: "op-card", dataset: { active: String(isActive), dim: String(!!active && !isActive) } },
        h("div", { class: "row-between" }, h("span", { class: "row", style: { gap: "8px" } }, icon(op.iconName, "op-icon"), h("strong", null, op.title)), status),
        h("p", { class: "op-text" }, op.text),
        h("code", { class: "op-env" }, op.env));
    }));
  }

  function renderReadiness(state) {
    const health = state.health;
    const data = health.data;
    const pipeline = knownPipeline(state.run);
    const llm = L.llmMode(data && data.llm_mode);
    const row = (label, value, note) => h("div", { class: "ready-row" },
      h("span", { class: "muted" }, label), h("span", { class: "row", style: { gap: "6px", justifyContent: "flex-end" } }, value), note ? h("div", { class: "field-hint ready-note" }, note) : null);

    let opText;
    if (pipeline === "static_only") {
      opText = badge("Migration · not configured", "warn");
    } else if (pipeline) {
      const p = L.provenance({ report: { simulation: pipeline === "simulation", settings: { pipeline }, verification: {}, state: {} } });
      opText = badge(p.label.replace(/^Saved report · /, ""), p.tone);
    } else {
      opText = badge("Unknown until the first report", "muted");
    }
    readinessHost.replaceChildren(
      row("Backend", health.status === "online" ? badge("Online", "ok") : health.status === "offline" ? badge("Offline", "err") : badge("Checking", "muted")),
      row("Docker", !data ? badge("Unknown", "muted") : data.docker ? badge("Available", "ok") : badge("Unavailable", "err"),
        data && !data.docker ? "Only static inventory can run; verification will fail." : null),
      row("AI mode", data ? badge(llm.label, llm.tone) : badge("Unknown", "muted"),
        data && data.llm_mode === "mock" ? "No Meta AI calls. Migration uses simulation or offline fixtures." : data && data.llm_mode === "live" ? "Key and model are not checked until a run." : null),
      row("Operation", opText,
        pipeline ? "From the latest report on this page (or config.js). It can change when the server restarts." : "The API reveals the pipeline only in a finished report."));
  }

  function buildStart() {
    sourceInput = h("input", {
      class: "input mono", id: "source-path", name: "source_path", type: "text", required: true,
      autocomplete: "off", spellcheck: "false", placeholder: "samples/legacy_shop",
      value: (PP.store.recall() || {}).source || "samples/legacy_shop",
      "aria-describedby": "source-hint", oninput: () => renderProjects(),
    });
    iterInput = h("input", { class: "input num", id: "max-iter", name: "max_iterations", type: "number", min: "1", step: "1", value: "5", "aria-describedby": "iter-hint" });
    startBtn = h("button", { class: "btn btn--primary btn--lg", type: "submit" }, icon("play"), "Start run");
    formStatus = h("div", { class: "form-status", role: "status" });
    projectsHost = h("div", { class: "project-grid" });
    opsHost = h("div", { class: "op-grid" });
    readinessHost = h("div", { class: "ready-list" });

    const advanced = h("details", { class: "disclosure", dataset: { key: "advanced-settings" } },
      h("summary", null, icon("cpu", "dim"), h("strong", null, "Advanced settings"), h("span", { class: "dim", style: { fontSize: "12.5px" } }, "custom path, iterations, API and server variables")),
      h("div", { class: "disclosure-body stack" },
        h("div", { class: "grid grid-2" },
          h("label", { class: "field" },
            h("span", { class: "field-label" }, "Source path (on the backend machine)"),
            sourceInput,
            h("span", { class: "field-hint", id: "source-hint" }, "Relative to the repository root or absolute. Not a browser upload or Git URL.")),
          h("label", { class: "field" },
            h("span", { class: "field-label" }, "Max iterations"),
            iterInput,
            h("span", { class: "field-hint", id: "iter-hint" }, "Migration repair loop limit (integer ≥ 1). Ignored by audit and compatibility."))),
        h("div", { class: "field" },
          h("span", { class: "field-label" }, "Target Python version"),
          h("input", { class: "input", type: "text", readonly: true, value: "Set on the server — not selectable via the API" }),
          h("span", { class: "field-hint" }, "Migration is 2.7 → 3.12. Compatibility targets come from PROOFPORT_TARGET_VERSION.")),
        h("div", null,
          h("div", { class: "section-label", style: { marginBottom: "6px" } }, "Request sent by Start run"),
          h("pre", { class: "code" }, 'POST /api/runs\n{"source_path": "<path>", "max_iterations": <n>}\n\nAny other field (mode, target_version, api_key…) is rejected with 422.')),
        h("div", null,
          h("div", { class: "section-label", style: { marginBottom: "6px" } }, "Server variables (.env, read at startup)"),
          h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", null, h("tr", null, h("th", null, "Variable"), h("th", null, "Purpose"))),
            h("tbody", null, [
              ["LLM_MODE", "mock (no Meta calls) · live · replay (not implemented)"],
              ["PROOFPORT_PIPELINE", "verify (default) · fixtures · simulation · analyze · audit · compatibility"],
              ["PROOFPORT_CASES_FILE", "Golden input cases, e.g. tests/fixtures/legacy_shop/cases.json"],
              ["PROOFPORT_FIXTURE_FILE", "Pre-written patches for the fixtures pipeline"],
              ["PROOFPORT_SECURITY_FIXTURES", "Optional security proposals (fixtures + mock only)"],
              ["PROOFPORT_SOURCE_VERSION / PROOFPORT_TARGET_VERSION", "Python versions for P3 operations"],
            ].map(([k, v]) => h("tr", null, h("td", null, h("code", null, k)), h("td", { class: "muted" }, v))))))),
        h("p", { class: "field-hint" }, "Full operator guide: backend/FRONTEND_HANDOFF.md §2 and backend/UNIVERSAL.md.")));

    const form = h("form", { class: "stack", novalidate: true, onsubmit: onSubmit },
      h("div", { class: "start-layout" },
        h("div", { class: "stack" },
          h("div", null,
            h("div", { class: "step-title" }, h("span", { class: "step-num" }, "1"), "Choose a project"),
            h("p", { class: "muted step-desc" }, "Demo projects that ship with this repository. The path is read on the backend machine.")),
          projectsHost),
        h("div", { class: "stack" },
          h("div", null,
            h("div", { class: "step-title" }, h("span", { class: "step-num" }, "2"), "Run on this server"),
            h("p", { class: "muted step-desc" }, "The server decides the operation and AI mode at startup. This page cannot change them.")),
          h("div", { class: "ready-card" }, readinessHost, h("div", { class: "ready-action" }, startBtn), formStatus))),
      advanced);

    renderProjects();
    return card({ title: "Start a run", sub: "Pick a project and start. Results appear below as the backend reports them." }, form);
  }

  function buildOperations() {
    return card({ title: "Operations", sub: "One operation is active per server start. Choosing another from this page would need a backend API that does not exist yet." }, opsHost);
  }

  function replayCard() {
    return h("div", { class: "card replay-card" },
      h("div", { class: "replay-icon" }, icon("file")),
      h("div", { class: "replay-body" },
        h("div", { class: "card-title" }, "Explore saved results safely"),
        h("p", { class: "muted" }, "Open a report JSON downloaded earlier (Evidence → Download JSON). It is read in your browser only: nothing is executed, nothing is sent to the backend, and no AI is called. The evidence chain is re-verified locally.")),
      S.replayButton("Replay saved report"));
  }

  function onSubmit(event) {
    event.preventDefault();
    const source = sourceInput.value.trim();
    const iterations = Number(iterInput.value);
    let invalid = false;
    if (!source) { sourceInput.setAttribute("aria-invalid", "true"); invalid = true; } else sourceInput.removeAttribute("aria-invalid");
    if (!Number.isInteger(iterations) || iterations < 1) { iterInput.setAttribute("aria-invalid", "true"); invalid = true; } else iterInput.removeAttribute("aria-invalid");
    if (invalid) {
      formStatus.textContent = "Choose a project (or a valid path) and an integer number of iterations ≥ 1 in Advanced settings.";
      return;
    }
    PP.store.startRun(source, iterations);
  }

  function updateStart(state) {
    const run = state.run;
    const active = run && run.origin === "live" && !run.finalized && !run.lost;
    const offline = state.health.status !== "online";
    startBtn.disabled = !!(state.starting || active || offline);
    startBtn.replaceChildren(state.starting ? h("span", { class: "spinner" }) : icon("play"), state.starting ? "Starting…" : active ? "Run in progress" : "Start run");
    renderReadiness(state);
    renderOperations(state);
    if (state.startError) {
      formStatus.replaceChildren(errorView(state.startError, `Run not started (HTTP ${state.startError.status || "—"})`));
    } else {
      formStatus.textContent = offline ? "Backend offline — a run cannot be started." : active ? "The backend runs one job at a time. Follow it below." : "";
    }
  }

  // ---------- Errors ----------

  /** Configuration errors get an explanation and operator steps; others the generic callout. */
  function errorView(error, title) {
    const cfg = error && CONFIG_ERRORS[error.code];
    if (!cfg) return S.errorCallout(error, title);
    return h("div", { class: "config-error", role: "alert" },
      h("div", { class: "config-error-head" },
        h("span", { class: "config-error-icon" }, icon("server")),
        h("div", null,
          h("div", { class: "config-error-title" }, cfg.title),
          h("div", { class: "muted" }, "Server configuration — not a problem in your project. ", h("code", { class: "dim" }, error.code)))),
      h("p", null, cfg.what),
      h("div", null, h("div", { class: "section-label" }, "What the operator can do"), h("ol", { class: "list-steps" }, cfg.fix.map((f) => h("li", null, f)))),
      h("details", { class: "disclosure" }, h("summary", null, "Backend message"), h("div", { class: "disclosure-body muted break" }, error.message || "—")),
      h("div", { class: "row" }, h("span", { class: "muted" }, "Meanwhile you can"), S.replayButton("replay a saved report")));
  }

  // ---------- Pipeline ----------

  function stepStates(run) {
    const steps = stepsFor(run);
    const st = run.state;
    const terminal = st && PP.store.TERMINAL.has(st.status);
    const counts = {};
    for (const s of steps) counts[s.id] = run.events.filter((e) => s.events.includes(e.type)).length;
    const modules = st ? st.modules : [];
    const testing = modules.some((m) => m.status === "testing");

    // Which step is running right now (only while the run is not terminal).
    let current = null;
    if (st && !terminal) {
      if (st.phase === "migrating") current = testing ? "verify" : "migrate";
      else if (st.phase === "fixing") current = "migrate";
      else current = (steps.find((s) => s.phase === st.phase) || {}).id || null;
    }
    // The step where a failed run stopped.
    let failedAt = null;
    if (terminal && st.status === "failed") {
      failedAt = st.phase === "migrating" ? (testing || counts.verify ? "verify" : "migrate")
        : (steps.find((s) => s.phase === st.phase && s.id !== "report") || {}).id || null;
    }
    return steps.map((s) => {
      const reached = counts[s.id] > 0 || (s.phase && run.phasesSeen.includes(s.phase));
      let state = "pending";
      let text = "Waiting";
      if (s.id === current) { state = "active"; text = "In progress"; }
      else if (failedAt === s.id) { state = "failed"; text = "Failed here"; }
      else if (reached) { state = "observed"; text = s.id === "report" && st && st.status === "failed" ? "Failure recorded" : "Activity recorded"; }
      else if (terminal) { state = "skipped"; text = "Not observed"; }
      return Object.assign({}, s, { state, text, count: counts[s.id] });
    });
  }

  function pipelineCard(run) {
    const st = run.state;
    const terminal = st && PP.store.TERMINAL.has(st.status);
    const items = stepStates(run).map((s, i) => h("div", { class: "step", dataset: { state: s.state } },
      h("div", { class: "row-between" },
        h("span", { class: "step-index" }, String(i + 1).padStart(2, "0")),
        s.count ? h("span", { class: "step-count", title: "Evidence events recorded for this step" }, s.count + " ev") : null),
      h("div", { class: "step-name" }, s.label),
      h("div", { class: "flow-desc" }, s.desc),
      h("div", { class: "step-state" }, s.state === "active" ? h("span", { class: "spinner", style: { width: "10px", height: "10px" } }) : null, s.text)));

    const recent = run.events.slice(-6).reverse();
    return card({ title: "Pipeline", sub: "Steps light up only from the backend's reported phase and recorded evidence events — no estimated progress.",
      actions: st ? [S.statusBadge(st.status, true), S.provenanceBadge(run)] : null },
    h("div", { class: "stack" },
      h("div", { class: "row" }, badge(L.languageName(L.language(run)), "info"), L.parameters(run).source_version ? badge(L.parameters(run).source_version + (L.parameters(run).target_version ? " → " + L.parameters(run).target_version : " · source label"), "outline") : null),
      h("div", { class: "stepper stepper--flow", style: { "--steps": String(items.length) } }, items),
      st && !terminal ? h("div", { class: "row muted", style: { fontSize: "12.5px" } },
        h("span", { class: "spinner" }), "Backend phase: ", h("code", null, String(st.phase || "—")), h("span", { class: "dim" }, `· ${fmt.seconds(st.metrics.seconds)} elapsed`)) : null,
      st && !terminal ? indeterminate("Run in progress") : null,
      recent.length ? h("div", null,
        h("div", { class: "row-between", style: { marginBottom: "6px" } },
          h("span", { class: "section-label" }, "Latest events"),
          h("a", { href: "#/evidence", class: "field-hint" }, "Full timeline →")),
        h("ul", { class: "list-plain event-feed" }, recent.map((e) => {
          const t = L.eventType(e.type);
          return h("li", { class: "event-line" },
            h("span", { class: "tl-type", dataset: { tone: t.tone } }, h("span", { class: "tl-dot" }), h("code", null, String(e.type))),
            e.module ? h("span", { class: "mono dim nowrap" }, String(e.module)) : null,
            h("span", { class: "muted event-detail" }, String(e.detail || "")));
        }))) : null,
      h("p", { class: "dim", style: { fontSize: "12px" } }, run.origin === "replay"
        ? "Replay: steps are inferred from the final phase and recorded events."
        : "Short phases can finish between polls; activity is marked from actual phases and evidence events. It does not by itself prove a passed check or a verified evidence chain.")));
  }

  // ---------- Modules ----------

  function modulesCard(run) {
    const st = run.state;
    const modules = st ? st.modules : [];
    if (run.id !== prevRunId) { prevModuleStatus.clear(); prevRunId = run.id; }
    const counts = {};
    for (const m of modules) counts[m.status] = (counts[m.status] || 0) + 1;
    const simulated = L.isSimulated(run);
    const phpAudit = L.language(run) === "php" && (L.parameters(run).operation === "audit" || L.parameters(run).mode === "php_audit");
    const moduleStatus = (status) => phpAudit && status === "green" ? { label: "Audited", tone: "info" } : L.moduleStatus(status);

    const rows = modules.map((m) => {
      const s = moduleStatus(m.status);
      const before = prevModuleStatus.get(m.name);
      const turnedGreen = before && before !== "green" && m.status === "green";
      prevModuleStatus.set(m.name, m.status);
      const busy = m.status === "translating" || m.status === "testing" || m.status === "fixing";
      return h("tr", { class: turnedGreen ? "flash-ok" : null, dataset: { status: m.status } },
        h("td", null, h("span", { class: "mod-name" }, m.name)),
        h("td", null, h("span", { class: "row", style: { gap: "6px" } }, busy ? h("span", { class: "spinner", style: { width: "10px", height: "10px" } }) : null, badge(s.label, s.tone))),
        h("td", { class: "col-num" }, fmt.int(m.iterations)),
        h("td", null, m.tests_total > 0
          ? h("div", { class: "mod-cases" },
            progress(m.tests_passed, m.tests_total, m.status === "failed" ? "err" : m.tests_passed === m.tests_total ? "ok" : null, true, "mod-" + run.id + "-" + m.name),
            h("span", { class: "num nowrap" }, `${m.tests_passed}/${m.tests_total}`))
          : h("span", { class: "dim" }, "no cases")));
    });

    return card({ title: "Modules", titleExtra: simulated ? PP.util.tag("Simulated") : null, flush: true,
      sub: phpAudit ? "Audit completed does not mean syntax, tests, behavior or security were verified." : "Per-module golden cases (tests_passed / tests_total). Green follows the worker's rules — read provenance before concluding.",
      actions: h("div", { class: "row" }, Object.keys(counts).map((k) => badge(counts[k] + " " + moduleStatus(k).label.toLowerCase(), moduleStatus(k).tone))) },
    modules.length
      ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", null, h("tr", null, h("th", null, "Module"), h("th", null, "Status"), h("th", { class: "col-num" }, "Iterations"), h("th", null, "Golden cases"))),
        h("tbody", null, rows)))
      : PP.util.empty("box", "No modules", st ? "The run reported no modules." : "Waiting for the first state snapshot…"));
  }

  // ---------- Golden cases & checks ----------

  function casesCard(run) {
    const st = run.state;
    const v = run.report ? run.report.verification || {} : null;
    const modules = st ? st.modules : [];
    const casesPassed = modules.reduce((n, m) => n + m.tests_passed, 0);
    const casesTotal = modules.reduce((n, m) => n + m.tests_total, 0);
    const m = st ? st.metrics : null;
    const failed = st && st.status === "failed";
    const php = L.language(run) === "php";

    const line = (label, passed, total, note, key) => h("div", { class: "stack", style: { gap: "6px" } },
      h("div", { class: "row-between" }, h("span", null, label), h("span", { class: "num" }, total ? `${fmt.int(passed)} / ${fmt.int(total)}` : "—")),
      progress(passed, total, failed ? "err" : total && passed === total ? "ok" : null, false, key),
      note ? h("div", { class: "field-hint" }, note) : null);

    return card({ title: "Verification progress", titleExtra: S.simTag(run), sub: "Counts can reset during repair loops; denominators may change." },
      h("div", { class: "stack" },
        line("Golden cases (sum over modules)", casesPassed, casesTotal, "Recorded inputs replayed on the target and compared with the original output.", "cases-" + run.id),
        m ? line(php ? "Golden comparisons (metrics)" : "All checks (metrics)", m.tests_passed, m.tests_total, php ? "Existing PHP tests are reported separately below; these counts cover golden comparisons only." : "Golden comparisons + existing tests where those stages ran. Not added to the line above.", "checks-" + run.id) : null,
        v ? PP.util.kv([
          ["Golden cases recorded", v.golden_case_count !== undefined ? fmt.int(v.golden_case_count) : undefined],
          ["Legacy tests (source)", v.legacy_tests ? `${fmt.int(v.legacy_tests.tests_run)} ran on Python ${fmt.pyVersion(v.legacy_tests.python)}` : undefined],
          ["Source tests", v.source_tests ? `${fmt.int(v.source_tests.tests_run)} ran on ${L.runtimeLabel(v.source_tests)}` : undefined],
          ["Target syntax", v.syntax_passed !== undefined ? badge(L.tri(v.syntax_passed).label, L.tri(v.syntax_passed).tone) : undefined],
          ["Target compiles", v.target_compiles !== undefined ? badge(L.tri(v.target_compiles).label, L.tri(v.target_compiles).tone) : undefined],
          ["Target tests", v.target_tests ? `${fmt.int(v.target_tests.tests_run)} ran on ${L.runtimeLabel(v.target_tests)}` : undefined],
          ["Lines migrated", m && (m.lines_migrated || v.mode === "fixtures" || v.mode === "live") ? fmt.int(m.lines_migrated) + " (accepted green modules)" : undefined],
          ["AI migration", v.ai_migration !== undefined ? (v.ai_migration ? badge("Yes · verified", "ok") : badge("No", "muted")) : undefined],
        ]) : S.reportPending(run, "Golden case counts, legacy/target test runs and comparisons arrive with the final report")));
  }

  // ---------- Errors & limitations ----------

  function issuesCard(run) {
    const st = run.state;
    const v = run.report ? run.report.verification || {} : {};
    const mismatches = Array.isArray(v.comparisons) ? v.comparisons.filter((c) => c.matches === false) : [];
    const failedTests = v.target_tests && Array.isArray(v.target_tests.outcomes) ? v.target_tests.outcomes.filter((o) => o.status === "failed" || o.status === "error") : [];
    const limits = v.limitations;
    const blocks = [];
    if (st && st.error) blocks.push(errorView(st.error));
    if (st && st.status === "done" && run.report && st.hashes && st.hashes.unchanged !== true) {
      blocks.push(h("div", { class: "callout callout--warn" }, "Originals unchanged is not confirmed — no success verdict."));
    }
    if (mismatches.length) {
      blocks.push(h("div", { class: "stack" },
        h("div", { class: "card-title" }, `Behavior mismatches (${mismatches.length})`),
        mismatches.slice(0, 50).map((c) => h("details", { class: "disclosure" },
          h("summary", null, h("code", null, c.id), h("span", { class: "dim" }, c.module)),
          L.language(run) === "php" ? h("div", { class: "disclosure-body" }, PP.util.kv([
            ["Mismatch reason", c.reason || "Recorded PHP outcomes differ"],
            ["Source outcome SHA-256", c.expected_sha256 || "Not reported"],
            ["Target outcome SHA-256", c.observed_sha256 || "Not reported"],
            ["Raw outcomes", "Not included in the API comparison; inspect the retained local recordings."],
          ])) : h("div", { class: "disclosure-body grid grid-2" },
            h("div", null, h("div", { class: "section-label" }, "Expected (source)"), h("pre", { class: "code code--wrap" }, JSON.stringify(c.expected, null, 2))),
            h("div", null, h("div", { class: "section-label" }, "Actual (target)"), h("pre", { class: "code code--wrap" }, JSON.stringify(c.actual, null, 2))))))));
    }
    if (failedTests.length) {
      blocks.push(h("div", { class: "stack" },
        h("div", { class: "card-title" }, `Failed target tests (${failedTests.length})`),
        h("ul", { class: "list-dots" }, failedTests.map((o) => h("li", null, h("code", null, o.id), " — ", o.status, o.reason ? ": " + o.reason : "")))));
    }
    if (Array.isArray(limits) && limits.length) {
      blocks.push(h("div", { class: "stack", style: { gap: "6px" } }, h("div", { class: "section-label" }, "Limitations stated by the backend"), S.limitations(limits)));
    }
    const allowed = run.report && Array.isArray(run.report.allowed_differences) ? run.report.allowed_differences : [];
    if (allowed.length) {
      blocks.push(h("details", { class: "disclosure" },
        h("summary", null, "Documented allowed differences", badge(String(allowed.length), "muted")),
        h("div", { class: "disclosure-body" }, h("ul", { class: "list-dots" }, allowed.slice(0, 200).map((d) => h("li", null, h("code", null, d.case), " · ", d.rule || "", d.path ? h("span", { class: "dim" }, "  (" + d.path + ")") : null))))));
    }
    if (!blocks.length) {
      blocks.push(run.report
        ? h("div", { class: "muted" }, "No verification errors were reported.")
        : h("div", { class: "muted" }, st && st.status === "running" ? "No errors so far. Detailed check results arrive with the final report." : "No errors reported."));
    }
    return card({ title: "Verification errors & limitations" }, h("div", { class: "stack" }, blocks));
  }

  // ---------- Empty state ----------

  function emptyState() {
    const step = (n, title, text) => h("div", { class: "how-step" },
      h("span", { class: "step-num" }, String(n)),
      h("div", null, h("div", { class: "how-title" }, title), h("div", { class: "muted" }, text)));
    return card({ class: "empty-run" },
      h("div", { class: "empty-run-head" },
        icon("migration", "empty-run-icon"),
        h("div", null,
          h("div", { class: "empty-title" }, "No run yet"),
          h("p", { class: "muted" }, "Nothing has been started from this browser. Here is what happens when you press Start run:"))),
      h("div", { class: "how-grid" },
        step(1, "You choose a project", "A folder that exists on the backend machine, e.g. samples/legacy_shop."),
        step(2, "The server picks the operation", "Migration, audit or compatibility — and Mock or Live AI — from its startup configuration."),
        step(3, "Work runs in Docker", "Originals are hashed and never modified. Every step is written to a hash-chained evidence log."),
        step(4, "You get a report", "Phases, modules, findings and evidence appear here; HTML/JSON exports in Evidence.")),
      h("div", { class: "row", style: { marginTop: "4px" } },
        h("span", { class: "muted" }, "No server set up for runs?"), S.replayButton("Replay a saved report instead")));
  }

  function render(state) {
    const legacy = state.control.mode === "legacy";
    legacyHost.hidden = !legacy;
    controlForm.update(state);
    if (legacy) updateStart(state);
    const run = state.run;
    if (!run) {
      dynamic.replaceChildren(emptyState());
      return;
    }
    dynamic.replaceChildren(
      S.pollErrorCallout(run) || document.createComment(""),
      pipelineCard(run),
      h("div", { class: "grid grid-2" }, casesCard(run), issuesCard(run)),
      modulesCard(run));
  }

  PP.views.migration = {
    title: "Migration",
    sub: "Choose an operation, check readiness and follow recorded results",
    mount(el) {
      root = el;
      dynamic = h("div", { class: "stack-lg" });
      // Order: start → live run (or empty state) → operations → replay.
      const controlHost = h("div");
      controlForm = PP.controlForm.mount(controlHost);
      legacyHost = h("div", { class: "stack-lg" }, buildStart(), buildOperations());
      root.replaceChildren(h("div", { class: "stack-lg" }, controlHost, legacyHost, dynamic, replayCard()));
    },
    update: render,
  };
})(window.PP);
