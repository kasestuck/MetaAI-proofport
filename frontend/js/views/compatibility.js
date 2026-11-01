/*
 * Compatibility: Python versions and compatibility checks.
 *
 * V1 run details expose partial compatibility results. The final report adds:
 *   - P3 compatibility/analyze/audit: verification.compatibility, version_detection, registry
 *   - migration (fixtures/live): verification.source_python, target_tests, target_compiles
 * An older server supplies results only through its final report. Tri-state rule:
 * true = confirmed, false = failed, null/missing = not confirmed (handoff §5).
 */
(function (PP) {
  "use strict";

  const { h, icon, fmt, badge, card } = PP.util;
  const L = PP.labels;
  const S = PP.views.shared;

  let root;

  function levelHero(run, v) {
    const c = v.compatibility || {};
    const failed = run.state && run.state.status === "failed";
    const level = L.compatLevel(c.level);
    // A failed run never gets a green verdict, even if individual checks passed.
    const tone = failed ? "err" : level.tone;
    return card({ title: "Compatibility verdict", sub: "Strongest completed check; it does not replace run status, errors or individual checks" },
      h("div", { class: "stack" },
        h("div", { class: "row" },
          h("span", { class: "status-big", style: { color: tone === "ok" ? "var(--success)" : tone === "err" ? "var(--danger)" : "var(--text)" } },
            failed ? "Run failed — no compatibility verdict" : level.label),
          c.level ? h("code", { class: "dim" }, c.level) : null),
        PP.util.kv([
          ["Language", badge(v.language === "php" ? "PHP" : "Python", "info")],
          ["Operation", v.mode ? badge(v.mode, "info") : null],
          ["Source version", v.source_version || h("span", { class: "dim" }, "not determined")],
          ["Analysis interpreter", v.analysis_interpreter || undefined],
          ["Target version", v.target_version || (v.mode === "compatibility" ? null : h("span", { class: "dim" }, "not applicable"))],
          ["Actual target patch", c.existing_tests && c.existing_tests.python ? "Python " + fmt.pyVersion(c.existing_tests.python) : c.syntax && c.syntax.python ? "Python " + fmt.pyVersion(c.syntax.python) : undefined],
          ["Actual source PHP", v.language === "php" ? (v.source_tests && v.source_tests.php || v.source_syntax && v.source_syntax.php) : undefined],
          ["Actual target PHP", v.language === "php" && v.target_tests ? v.target_tests.php : undefined],
          ["Code translated", v.migration_performed === false ? "No — compatibility checks do not migrate code" : undefined],
          ["Project executed", v.project_executed !== undefined ? String(!!v.project_executed) : undefined],
        ]),
        failed && run.state.error ? S.errorCallout(run.state.error) : null));
  }

  function checksCard(v) {
    const c = v.compatibility || {};
    if (v.language === "php") return card({ title: "PHP checks", sub: "Separate results; null or missing means not verified" },
      S.triCheck("Syntax verified", c.syntax_passed, "PHP lint ran in the selected target Docker interpreter. Syntax alone does not prove compatibility.", "Not verified"),
      S.triCheck("Tests passed", c.tests_passed, "A nonempty supported local PHP test suite passed on the target. No dependencies are installed automatically.", "Not verified"),
      S.triCheck("Behavior verified", c.behavior_verified, "Recorded function inputs matched on source and target. This is finite coverage, not universal equivalence.", "Not verified"));
    const coverage = c.covered_modules || c.uncovered_modules
      ? `Covered modules: ${(c.covered_modules || []).length}; uncovered: ${(c.uncovered_modules || []).length}.`
      : null;
    return card({ title: "Checks", sub: "Each check is reported separately" },
      S.triCheck("Syntax compatible", c.syntax_compatible, "Source compiles under the selected interpreter." + (c.syntax && Array.isArray(c.syntax.errors) && c.syntax.errors.length ? ` ${c.syntax.errors.length} syntax error(s).` : "")),
      S.triCheck("Existing tests passed", c.tests_passed, "Non-empty unittest suite under tests/ passed on the target. Not golden equivalence."),
      S.triCheck("Recorded cases match", c.recorded_cases_match, "Golden outputs recorded on the source match on the target."),
      S.triCheck("Behavior verified", c.behavior_verified, "Requires matching cases for every analyzed module and full parser coverage. " + (coverage || "") + " Still not universal equivalence."),
      c.target_metadata_compatible !== undefined ? S.triCheck("Project metadata allows target", c.target_metadata_compatible, "python_requires constraints vs the actual target runtime.") : null);
  }

  function coverageCard(v) {
    const c = v.compatibility || {};
    const comps = Array.isArray(c.comparisons) ? c.comparisons : Array.isArray(v.comparisons) ? v.comparisons : [];
    if (!c.covered_modules && !comps.length) return null;
    const matched = comps.filter((x) => x.matches).length;
    return card({ title: "Golden coverage", sub: "Recorded behavior compared between source and target interpreters" },
      h("div", { class: "stack" },
        comps.length ? h("div", { class: "row-between" }, h("span", null, "Cases matched"), h("span", { class: "num" }, `${matched} / ${comps.length}`)) : null,
        comps.length ? PP.util.progress(matched, comps.length, matched === comps.length ? "ok" : "err", false, "compat-cases") : null,
        PP.util.kv([
          ["Covered modules", Array.isArray(c.covered_modules) ? (c.covered_modules.length ? c.covered_modules.join(", ") : "none") : undefined],
          ["Uncovered modules", Array.isArray(c.uncovered_modules) ? (c.uncovered_modules.length ? h("span", { style: { color: "var(--warning)" } }, c.uncovered_modules.join(", ")) : "none") : undefined],
        ])));
  }

  function detectionCard(v) {
    const d = v.version_detection;
    if (!d) return null;
    const ev = Array.isArray(d.evidence) ? d.evidence : [];
    return card({ title: "Static version detection", sub: "Possible versions and signals — not proof of the interpreter or compatibility" },
      h("div", { class: "stack" },
        PP.util.kv([
          ["Status", badge(d.status || "unknown", d.status === "conflict" ? "err" : "muted")],
          ["Possible versions", Array.isArray(d.possible_versions) && d.possible_versions.length ? h("span", { class: "row", style: { gap: "4px" } }, d.possible_versions.map((x) => badge(x, "outline", "no-dot"))) : null],
          ["Declared by operator", d.user_version || null],
          ["Syntax minimum", d.syntax_minimum || null],
          ["python_requires", Array.isArray(d.python_requires) && d.python_requires.length ? d.python_requires.join(", ") : "none declared"],
          ["Dependencies resolved", String(!!d.dependencies_resolved)],
        ]),
        ev.length ? h("details", { class: "disclosure" }, h("summary", null, "Detection signals", badge(String(ev.length), "muted")),
          h("div", { class: "disclosure-body" }, h("ul", { class: "list-dots" }, ev.slice(0, 100).map((e) => h("li", null, h("code", null, e.kind || "signal"), " ", h("span", { class: "dim" }, (e.file || "") + (e.line ? ":" + e.line : ""))))))) : null,
        S.limitations(d.limitations)));
  }

  function registryCard(v, current, language) {
    const reg = Array.isArray(v.registry) ? v.registry : null;
    if (!reg) return null;
    const yes = (x) => x === true ? badge("yes", "ok") : x === false ? badge("no", "muted") : badge("unknown", "muted");
    return card({ title: (language === "php" ? "PHP" : "Python") + " runtime registry", flush: true, sub: (current ? "Latest capabilities snapshot" : "Snapshot recorded in this report") + " — configured ≠ available ≠ verified" },
      h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", null, h("tr", null, ["Version", "Image", "Configured", "Available", "Verified", "Roles"].map((t) => h("th", null, t)))),
        h("tbody", null, reg.map((r) => h("tr", null,
          h("td", null, h("strong", null, r.version)),
          h("td", { class: "mono muted break" }, r.image || "—"),
          h("td", null, yes(r.configured)),
          h("td", null, yes(r.available)),
          h("td", null, yes(r.verified)),
          h("td", { class: "muted" }, [r.source ? "source" : null, r.target ? "target" : null].filter(Boolean).join(", ") || "—")))))));
  }

  function migrationRuntimeCard(run, v) {
    return card({ title: "Migration runtimes", sub: "Interpreters actually used by this migration run (Docker)" },
      h("div", { class: "stack" },
        h("div", { class: "row", style: { fontSize: "20px", fontWeight: "600" } },
          "Python " + fmt.pyVersion(v.source_python || (v.legacy_tests && v.legacy_tests.python)),
          h("span", { class: "dim" }, "→"),
          "Python " + fmt.pyVersion(v.target_tests && v.target_tests.python)),
        S.triCheck("Target compiles", v.target_compiles, "Migrated candidates compile on the target interpreter."),
        S.triCheck("Behavior matches on recorded cases",
          Array.isArray(v.comparisons) && v.comparisons.length ? v.comparisons.every((c) => c.matches) : null,
          Array.isArray(v.comparisons) ? `${v.comparisons.filter((c) => c.matches).length} / ${v.comparisons.length} cases matched` : "No comparisons recorded"),
        v.images ? h("details", { class: "disclosure" }, h("summary", null, "Docker images"),
          h("div", { class: "disclosure-body" }, PP.util.kv(Object.keys(v.images).map((k) => [k, h("span", { class: "hash" }, String(v.images[k]))])))) : null));
  }

  function referenceCard() {
    const run = PP.store.state.run;
    const language = run ? L.language(run) : PP.control.state.draft.language || "python";
    const caps = PP.store.state.control.capabilities;
    if (PP.store.state.control.mode === "v1") return card({ title: "Current runtime capabilities", sub: "Available images and verified support are separate checks" },
      h("div", { class: "stack" }, registryCard({ registry: language === "php" ? caps.languages && caps.languages.php && caps.languages.php.runtimes || [] : caps.runtimes }, true, language),
        h("a", { class: "btn", href: "#/migration" }, "Configure a compatibility check")));
    if (PP.store.state.control.mode !== "legacy") return card({ title: "Runtime capabilities unavailable" },
      h("p", { class: "muted" }, "Wait for discovery or refresh capabilities in Run control. No runtime support is inferred from an unavailable response."),
      h("a", { class: "btn", href: "#/migration" }, "Open run control"));
    return card({ title: "Runtime reference", sub: "From backend/FRONTEND_HANDOFF.md (audit 2026-10-29) — documentation, not live runtime discovery" },
      h("div", { class: "stack" },
        PP.util.kv([
          ["Verified in the last P3 run", h("span", { class: "row", style: { gap: "4px" } }, ["2.7.18", "3.12.16", "3.13.18"].map((x) => badge(x, "outline", "no-dot")))],
          ["Configured only", h("span", { class: "row", style: { gap: "4px" } }, ["3.8", "3.10", "3.14"].map((x) => badge(x, "outline", "no-dot")))],
          ["Real migration pair", "Python 2.7 → 3.12 only"],
          ["Selecting versions", "Server settings PROOFPORT_SOURCE_VERSION / PROOFPORT_TARGET_VERSION; not selectable via the API"],
        ]),
        h("p", { class: "dim", style: { fontSize: "12px" } }, "The API has no runtime-registry or capabilities endpoint. A registry snapshot appears above only when a P3 report includes one.")));
  }

  function render(state) {
    const run = state.run;
    const control = run && run.control;
    const partial = control && control.result.compatibility ? Object.assign({}, control.parameters, {
      mode: control.parameters.operation, compatibility: control.result.compatibility, limitations: control.result.limitations, target_tests: control.result.target_tests,
    }) : null;
    const v = run && run.report ? run.report.verification || {} : partial;
    const blocks = [];
    if (!run) {
      blocks.push(card({}, PP.util.empty("compatibility", "No compatibility data",
        "Configure a compatibility operation in Run control. Syntax, existing tests and recorded behavior are separate checks; detailed analysis arrives with the final report.",
        h("div", { class: "row", style: { justifyContent: "center", marginTop: "8px" } }, S.replayButton()))));
    } else if (!v) {
      blocks.push(card({ title: "Waiting for the report" }, S.reportPending(run, "Compatibility checks, version detection and the runtime registry are published in the final report")));
    } else if (v.compatibility) {
      blocks.push(h("div", { class: "grid grid-2" }, levelHero(run, v), checksCard(v)));
      const cov = coverageCard(v);
      const existing = v.compatibility.existing_tests || v.target_tests;
      const tests = existing ? card({}, S.outcomes(existing, "Existing tests on target")) : null;
      if (cov || tests) blocks.push(h("div", { class: "grid grid-2" }, cov || h("div"), tests || h("div")));
      const det = detectionCard(v);
      if (det) blocks.push(det);
      const reg = registryCard(v);
      if (reg) blocks.push(reg);
      if (Array.isArray(v.limitations) && v.limitations.length) blocks.push(card({ title: "Limitations" }, S.limitations(v.limitations)));
    } else if (v.source_python || v.target_tests || v.legacy_tests) {
      blocks.push(h("div", { class: "grid grid-2" }, migrationRuntimeCard(run, v),
        v.target_tests ? card({}, S.outcomes(v.target_tests, "Existing tests on target")) : card({ title: "Existing tests on target" }, h("div", { class: "muted" }, "Target tests did not run."))));
    } else {
      blocks.push(card({ title: "No compatibility checks in this run" }, h("p", { class: "muted" },
        L.isSimulated(run) ? "Simulation does not execute any interpreter, so there is nothing to report about versions."
          : "This run's report contains no compatibility or runtime data (the run may have stopped before those stages).")));
    }
    blocks.push(referenceCard());
    root.replaceChildren(h("div", { class: "stack-lg" }, blocks));
  }

  PP.views.compatibility = {
    title: "Compatibility",
    sub: "Python and PHP versions, syntax, tests and recorded-behavior checks",
    mount(el) { root = el; },
    update: render,
  };
})(window.PP);
