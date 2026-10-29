/*
 * Migration: start a run (POST /api/runs), pipeline phases, modules,
 * golden-case progress and verification errors.
 *
 * The form is mounted once (so typing is never interrupted); everything
 * below it re-renders on each store update.
 */
(function (PP) {
  "use strict";

  const { h, icon, fmt, badge, card, progress, indeterminate } = PP.util;
  const L = PP.labels;
  const S = PP.views.shared;

  let root, dynamic, form, sourceInput, iterInput, startBtn, formStatus;
  const prevModuleStatus = new Map(); // module name -> last status, for the "turned green" highlight
  let prevRunId = null;

  // ---------- Form ----------
  function buildForm() {
    sourceInput = h("input", {
      class: "input mono", id: "source-path", name: "source_path", type: "text", required: true,
      autocomplete: "off", spellcheck: "false", placeholder: "samples/legacy_shop",
      value: (PP.store.recall() || {}).source || "samples/legacy_shop",
      "aria-describedby": "source-hint",
    });
    iterInput = h("input", { class: "input num", id: "max-iter", name: "max_iterations", type: "number", min: "1", step: "1", value: "5", "aria-describedby": "iter-hint" });
    startBtn = h("button", { class: "btn btn--primary", type: "submit" }, icon("play"), "Start run");
    formStatus = h("div", { class: "field-hint", role: "status" });

    form = h("form", { class: "stack", novalidate: true, onsubmit: onSubmit },
      h("div", { class: "run-form" },
        h("label", { class: "field" },
          h("span", { class: "field-label" }, "Source project path (on the backend machine)"),
          sourceInput),
        h("label", { class: "field" },
          h("span", { class: "field-label" }, "Max iterations"),
          iterInput),
        startBtn),
      h("div", { class: "presets" },
        h("span", { class: "field-hint" }, "Repository paths:"),
        PP.config.sourcePresets.map((p) => h("button", {
          class: "chip-btn", type: "button", title: p.path,
          onclick: () => { sourceInput.value = p.path; sourceInput.removeAttribute("aria-invalid"); sourceInput.focus(); },
        }, p.label))),
      h("div", { class: "grid grid-2" },
        h("div", { class: "field" },
          h("span", { class: "field-label" }, "Target Python version"),
          h("input", { class: "input", type: "text", readonly: true, value: "Configured on the server", "aria-describedby": "target-hint" }),
          h("span", { class: "field-hint", id: "target-hint" },
            "The API does not accept a target version. Migration is 2.7 → 3.12; compatibility targets are set via PROOFPORT_TARGET_VERSION by the operator.")),
        h("div", { class: "field" },
          h("span", { class: "field-label" }, "Notes"),
          h("span", { class: "field-hint", id: "source-hint" },
            "A server-local path, relative to the repository root or absolute — not a browser upload or Git URL. The backend runs one job at a time."),
          h("span", { class: "field-hint", id: "iter-hint" },
            "max_iterations controls the migration repair loop (integer ≥ 1); P3 analyze/audit/compatibility ignore it."))),
      formStatus);

    return card({ title: "Start a run", sub: "POST /api/runs · pipeline and LLM mode are fixed by the server configuration",
      actions: S.replayButton("Replay saved report") }, form);
  }

  function onSubmit(event) {
    event.preventDefault();
    const source = sourceInput.value.trim();
    const iterations = Number(iterInput.value);
    let invalid = false;
    if (!source) { sourceInput.setAttribute("aria-invalid", "true"); invalid = true; } else sourceInput.removeAttribute("aria-invalid");
    if (!Number.isInteger(iterations) || iterations < 1) { iterInput.setAttribute("aria-invalid", "true"); invalid = true; } else iterInput.removeAttribute("aria-invalid");
    if (invalid) {
      formStatus.textContent = "Enter a source path and an integer number of iterations ≥ 1.";
      return;
    }
    PP.store.startRun(source, iterations);
  }

  function updateForm(state) {
    const run = state.run;
    const active = run && run.origin === "live" && !run.finalized && !run.lost;
    const offline = state.health.status !== "online";
    startBtn.disabled = !!(state.starting || active || offline);
    startBtn.replaceChildren(state.starting ? h("span", { class: "spinner" }) : icon("play"), state.starting ? "Starting…" : "Start run");
    let msg = "";
    if (offline) msg = "Backend offline — the run cannot be started.";
    else if (active) msg = "A run is in progress. The backend accepts one run at a time; wait for it to finish.";
    if (!state.startError) formStatus.textContent = msg;
    else {
      formStatus.replaceChildren(S.errorCallout({ code: state.startError.code, message: state.startError.message }, `Run not started (HTTP ${state.startError.status || "—"})`));
    }
  }

  // ---------- Pipeline ----------
  // Phases can be shorter than the poll interval, so evidence events also
  // mark a phase as reached.
  const PHASE_BY_EVENT = { run_started: "analyzing", golden_recorded: "recording", patch_applied: "migrating", security_finding: "security", security_fix: "security", fix_reverted: "security" };

  function pipelineCard(run) {
    const st = run.state;
    const seen = run.phasesSeen.slice();
    for (const e of run.events) {
      const phase = PHASE_BY_EVENT[e.type];
      if (phase && !seen.includes(phase)) seen.push(phase);
    }
    const terminal = st && PP.store.TERMINAL.has(st.status);
    const steps = L.PHASES.slice();
    if (st && st.phase && !steps.some((p) => p.id === st.phase)) steps.push({ id: st.phase, label: st.phase }); // unknown phase: neutral
    const items = steps.map((p, i) => {
      let s = "pending";
      let text = "Not reached";
      if (st && st.phase === p.id && !terminal) { s = "active"; text = "In progress"; }
      else if (seen.includes(p.id)) { s = "done"; text = "Reached"; }
      if (terminal && st.phase === p.id) {
        s = st.status === "failed" ? "failed" : "done";
        text = st.status === "failed" ? "Run failed here" : "Completed";
      } else if (terminal && !seen.includes(p.id)) { s = "skipped"; text = "Not observed"; }
      return h("div", { class: "step", dataset: { state: s } },
        h("div", { class: "step-index" }, String(i + 1).padStart(2, "0")),
        h("div", { class: "step-name" }, p.label),
        h("div", { class: "step-state" }, s === "active" ? h("span", { class: "spinner", style: { width: "10px", height: "10px" } }) : null, text));
    });
    const running = st && !terminal;
    return card({ title: "Pipeline", sub: "Phase is a free-form backend string; order varies by pipeline. Progress is not time-based.",
      actions: st ? [S.statusBadge(st.status, true), S.provenanceBadge(run)] : null },
      h("div", { class: "stack" },
        h("div", { class: "stepper", style: { "--steps": String(steps.length) } }, items),
        running ? indeterminate("Run in progress") : null,
        h("p", { class: "dim", style: { fontSize: "12px" } }, run.origin === "replay"
          ? "Replay: phases are inferred from the final phase and recorded events."
          : "Reached phases come from polled snapshots and evidence events; very short phases may be “not observed”.")));
  }

  // ---------- Modules ----------
  function modulesCard(run) {
    const st = run.state;
    const modules = st ? st.modules : [];
    if (run.id !== prevRunId) { prevModuleStatus.clear(); prevRunId = run.id; }
    const counts = {};
    for (const m of modules) counts[m.status] = (counts[m.status] || 0) + 1;
    const simulated = L.isSimulated(run);

    const rows = modules.map((m) => {
      const s = L.moduleStatus(m.status);
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
      sub: "Per-module golden cases (tests_passed / tests_total). Green follows the worker's rules — read provenance before concluding.",
      actions: h("div", { class: "row" }, Object.keys(counts).map((k) => badge(counts[k] + " " + L.moduleStatus(k).label.toLowerCase(), L.moduleStatus(k).tone))) },
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

    const line = (label, passed, total, note, key) => h("div", { class: "stack", style: { gap: "6px" } },
      h("div", { class: "row-between" }, h("span", null, label), h("span", { class: "num" }, total ? `${fmt.int(passed)} / ${fmt.int(total)}` : "—")),
      progress(passed, total, failed ? "err" : total && passed === total ? "ok" : null, false, key),
      note ? h("div", { class: "field-hint" }, note) : null);

    return card({ title: "Verification progress", titleExtra: S.simTag(run), sub: "Counts can reset during repair loops; denominators may change." },
      h("div", { class: "stack" },
        line("Golden cases (sum over modules)", casesPassed, casesTotal, "Recorded inputs replayed on the target and compared with the original output.", "cases-" + run.id),
        m ? line("All checks (metrics)", m.tests_passed, m.tests_total, "Golden comparisons + existing tests where those stages ran. Not added to the line above.", "checks-" + run.id) : null,
        v ? PP.util.kv([
          ["Golden cases recorded", v.golden_case_count !== undefined ? fmt.int(v.golden_case_count) : undefined],
          ["Legacy tests (source)", v.legacy_tests ? `${fmt.int(v.legacy_tests.tests_run)} ran on Python ${fmt.pyVersion(v.legacy_tests.python)}` : undefined],
          ["Target compiles", v.target_compiles !== undefined ? badge(L.tri(v.target_compiles).label, L.tri(v.target_compiles).tone) : undefined],
          ["Target tests", v.target_tests ? `${fmt.int(v.target_tests.tests_run)} ran on Python ${fmt.pyVersion(v.target_tests.python)}` : undefined],
          ["Lines migrated", m && (m.lines_migrated || v.mode === "fixtures" || v.mode === "live") ? fmt.int(m.lines_migrated) + " (accepted green modules)" : undefined],
          ["AI migration", v.ai_migration !== undefined ? (v.ai_migration ? badge("Yes · verified", "ok") : badge("No", "muted")) : undefined],
        ]) : S.reportPending(run, "Golden case counts, legacy/target test runs and comparisons arrive with the final report")));
  }

  // ---------- Errors ----------
  function issuesCard(run) {
    const st = run.state;
    const v = run.report ? run.report.verification || {} : {};
    const mismatches = Array.isArray(v.comparisons) ? v.comparisons.filter((c) => c.matches === false) : [];
    const failedTests = v.target_tests && Array.isArray(v.target_tests.outcomes) ? v.target_tests.outcomes.filter((o) => o.status === "failed" || o.status === "error") : [];
    const limits = v.limitations;
    const blocks = [];
    if (st && st.error) blocks.push(S.errorCallout(st.error));
    if (st && st.status === "done" && run.report && st.hashes && st.hashes.unchanged !== true) {
      blocks.push(h("div", { class: "callout callout--warn" }, "Originals unchanged is not confirmed — no success verdict."));
    }
    if (mismatches.length) {
      blocks.push(h("div", { class: "stack" },
        h("div", { class: "card-title" }, `Behavior mismatches (${mismatches.length})`),
        mismatches.slice(0, 50).map((c) => h("details", { class: "disclosure" },
          h("summary", null, h("code", null, c.id), h("span", { class: "dim" }, c.module)),
          h("div", { class: "disclosure-body grid grid-2" },
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

  function render(state) {
    updateForm(state);
    const run = state.run;
    if (!run) {
      dynamic.replaceChildren(card({}, PP.util.empty("migration", "No run yet",
        "Enter a server-local source path above and start a run. What the run does (simulation, offline fixtures, live verification or a P3 check) depends on the server configuration.")));
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
    sub: "Run the server-configured pipeline and follow modules, iterations and golden cases",
    mount(el) {
      root = el;
      dynamic = h("div", { class: "stack-lg" });
      root.replaceChildren(h("div", { class: "stack-lg" }, buildForm(), dynamic));
    },
    update: render,
  };
})(window.PP);
