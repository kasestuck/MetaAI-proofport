/*
 * Overview: backend health, Docker, LLM mode, current run and headline metrics.
 * Data: GET /api/health + RunState; report adds provenance and model usage.
 */
(function (PP) {
  "use strict";

  const { h, icon, fmt, badge, card, progress, indeterminate } = PP.util;
  const L = PP.labels;
  const S = PP.views.shared;

  let root;

  function systemCard(state) {
    const health = state.health;
    const data = health.data;
    const online = health.status === "online";
    const llm = L.llmMode(online && data ? data.llm_mode : null);
    const item = (name, iconName, value, note) => h("div", { class: "sys-item" },
      h("span", { class: "row", style: { gap: "8px" } }, icon(iconName, "dim icon-inline"), h("span", { class: "sys-name" }, name)),
      h("span", { class: "row", style: { gap: "8px", justifyContent: "flex-end" } }, note ? h("span", { class: "dim", style: { fontSize: "12px" } }, note) : null, value));

    return card({ title: "System", sub: "From GET /api/health" },
      h("div", { class: "sys-list" },
        item("Backend", "server",
          health.status === "online" ? badge("Online", "ok") : health.status === "offline" ? badge("Offline", "err") : badge("Checking", "muted"),
          health.checkedAt ? "checked " + new Date(health.checkedAt).toLocaleTimeString() : null),
        item("Docker", "box",
          !data ? badge("Unknown", "muted") : data.docker ? badge("Available", "ok") : badge("Unavailable", "err"),
          data ? "at server start" : null),
        item("LLM mode", "cpu", (() => { const b = badge(llm.label, llm.tone); b.title = llm.desc; return b; })(), data ? "configuration" : null),
        item("Meta AI", "link",
          !data ? badge("Unknown", "muted") : data.llm_mode === "live" ? badge("Configured · unverified", "warn") : badge("Not connected", "muted"))),
      h("p", { class: "dim", style: { fontSize: "12px", marginTop: "12px" } },
        "Health shows app availability, not readiness of a specific operation. Pipeline, Python versions and fixtures are chosen by the operator on the server."));
  }

  function runCard(state) {
    const run = state.run;
    if (!run) {
      return card({ title: "Current run" },
        PP.util.empty("play", "No run attached",
          "Runs are started from the Migration section. The backend keeps runs in memory only; there is no server-side run history.",
          h("div", { class: "row", style: { justifyContent: "center", marginTop: "8px" } },
            h("a", { class: "btn btn--primary", href: "#/migration" }, icon("play"), "Start a run"), S.replayButton())));
    }
    const st = run.state;
    const running = st && (st.status === "running" || st.status === "queued");
    const prov = L.provenance(run);
    const report = run.report;

    return card({ title: "Current run", actions: run.origin === "replay" ? null : (run.finalized || run.lost)
      ? h("button", { class: "btn btn--sm btn--ghost", type: "button", onclick: () => PP.store.clearRun(), title: "Detach this run from the console" }, "Clear")
      : null },
      h("div", { class: "stack" },
        h("div", { class: "run-headline" },
          h("span", { class: "run-id", title: run.id }, run.id),
          st ? S.statusBadge(st.status, true) : (run.lost ? badge("Not found", "err") : h("span", { class: "row muted" }, h("span", { class: "spinner" }), "Connecting…")),
          S.provenanceBadge(run),
          run.restored ? PP.util.tag("Restored", "muted") : null),
        running ? indeterminate("Run in progress") : null,
        PP.util.kv([
          ["Phase", st ? L.phaseLabel(st.phase) : null],
          ["Source", run.source ? h("span", { class: "mono" }, run.source) : (run.origin === "replay" ? run.fileName : null)],
          ["Isolation", st ? (st.isolation === "docker" ? badge("Docker", "ok") : badge("Reduced · no container checks", "muted")) : null],
          ["Started", run.origin === "replay" ? undefined : fmt.dateTime(run.startedAt)],
          ["Provenance", prov ? h("span", { class: "muted" }, prov.desc) : null],
        ]),
        st && st.error ? S.errorCallout(st.error) : null,
        S.pollErrorCallout(run),
        report && report.notice ? h("details", { class: "disclosure" }, h("summary", null, "Report notice"), h("div", { class: "disclosure-body muted" }, report.notice)) : null));
  }

  function moduleKpi(run) {
    const modules = run && run.state ? run.state.modules : [];
    const counts = {};
    for (const m of modules) counts[m.status] = (counts[m.status] || 0) + 1;
    const colors = { green: "var(--success)", failed: "var(--danger)", translating: "var(--accent)", testing: "var(--accent)", fixing: "var(--warning)", pending: "var(--text-3)" };
    const order = ["green", "translating", "testing", "fixing", "failed", "pending"];
    const total = modules.length;
    return card({ class: "kpi" },
      h("div", { class: "kpi-label" }, icon("box"), "Modules"),
      h("div", { class: "kpi-value" }, total ? fmt.int(total) : "—"),
      total ? h("div", { class: "module-dist", "aria-hidden": "true" },
        order.filter((s) => counts[s]).map((s) => h("span", { style: { width: (counts[s] / total) * 100 + "%", background: colors[s] } }))) : null,
      h("div", { class: "kpi-foot legend" }, total
        ? order.filter((s) => counts[s]).map((s) => h("span", null, h("i", { style: { background: colors[s] } }), counts[s] + " " + L.moduleStatus(s).label.toLowerCase()))
        : "No modules yet"));
  }

  function testsKpi(run) {
    const m = run && run.state ? run.state.metrics : null;
    const passed = m ? m.tests_passed : 0;
    const total = m ? m.tests_total : 0;
    const failedRun = run && run.state && run.state.status === "failed";
    return card({ class: "kpi" },
      h("div", { class: "kpi-label" }, icon("check"), "Checks passed", S.simTag(run)),
      h("div", { class: "kpi-value" }, m ? fmt.int(passed) : "—", m ? h("small", null, "/ " + fmt.int(total)) : null),
      m ? progress(passed, total, failedRun ? "err" : passed === total && total > 0 ? "ok" : null, false, "ov-tests") : null,
      h("div", { class: "kpi-foot" }, L.isSimulated(run)
        ? "Simulated counts — no tests were executed"
        : total
          ? fmt.pct(passed, total) + "% of recorded golden cases + existing tests"
          : "No checks recorded (not run is not passed)"));
  }

  function securityKpi(run) {
    const sec = run && run.state ? run.state.security : null;
    const findings = sec ? sec.findings || [] : [];
    const review = findings.filter((f) => f.status === "needs_review").length;
    const prov = L.provenance(run);
    const notScanned = prov && (prov.id === "compatibility" || prov.id === "analyze" || prov.id === "static_only");
    return card({ class: "kpi" },
      h("div", { class: "kpi-label" }, icon("security"), "Security findings", S.simTag(run)),
      h("div", { class: "kpi-value delta" },
        sec ? fmt.int(sec.before) : "—",
        sec ? h("span", { class: "delta-arrow", style: { fontSize: "18px" } }, "→") : null,
        sec ? fmt.int(sec.after) : null,
        sec ? h("small", null, "before → after") : null),
      h("div", { class: "kpi-foot row" },
        notScanned ? h("span", null, "Not scanned in this mode — zero is not “secure”")
          : review ? badge(review + " need review", "warn")
            : sec ? h("span", null, "Potential warnings from the scanner") : "No data"));
  }

  function timeKpi(run) {
    const m = run && run.state ? run.state.metrics : null;
    const running = run && run.state && (run.state.status === "running" || run.state.status === "queued");
    return card({ class: "kpi" },
      h("div", { class: "kpi-label" }, icon("clock"), "Elapsed time"),
      h("div", { class: "kpi-value" }, m ? fmt.seconds(m.seconds) : "—"),
      h("div", { class: "kpi-foot" }, running ? "Elapsed so far — the API provides no ETA" : m ? "Total wall-clock time on the server" : "No run"));
  }

  function usageCard(run) {
    const m = run && run.state ? run.state.metrics : null;
    const v = run && run.report ? run.report.verification || {} : null;
    const simulated = L.isSimulated(run);
    let note;
    if (!m) note = "No run.";
    else if (simulated) note = "Simulated estimate for the demo — no model was called and nothing was billed.";
    else if (v && Number(v.model_calls) === 0) note = "No model usage recorded. Fixtures and offline checks never call Meta AI.";
    else if (v) note = `${fmt.int(Number(v.model_calls) || 0)} recorded model call(s). Cost uses server PRICE settings, not a billing balance.`;
    else note = "Recorded LLM usage; provenance is confirmed in the final report.";
    return card({ title: "AI usage", titleExtra: S.simTag(run), sub: "metrics.tokens_in / tokens_out / cost_usd" },
      h("div", { class: "grid grid-3" },
        h("div", null, h("div", { class: "section-label" }, "Cost"), h("div", { class: "kpi-value", style: { fontSize: "22px" } }, m ? fmt.usd(m.cost_usd) : "—")),
        h("div", null, h("div", { class: "section-label" }, "Tokens in"), h("div", { class: "kpi-value", style: { fontSize: "22px" } }, m ? fmt.int(m.tokens_in) : "—")),
        h("div", null, h("div", { class: "section-label" }, "Tokens out"), h("div", { class: "kpi-value", style: { fontSize: "22px" } }, m ? fmt.int(m.tokens_out) : "—"))),
      h("p", { class: "muted", style: { fontSize: "12.5px", marginTop: "12px" } }, note));
  }

  function integrityCard(run) {
    const st = run && run.state;
    const unchanged = st ? st.hashes && st.hashes.unchanged : undefined;
    const chain = run && run.chain;
    return card({ title: "Integrity", sub: "Local checks — not an external certification", actions: h("a", { class: "btn btn--sm btn--ghost", href: "#/evidence" }, "Evidence →") },
      h("div", null,
        S.triCheck("Evidence chain (server)", st ? st.chain_intact : null, "chain_intact reported by the backend"),
        S.triCheck("Evidence chain (re-verified in browser)", chain ? (chain.status === "ok" ? true : chain.status === "broken" ? false : null) : null,
          chain ? (chain.status === "ok" ? `SHA-256 recomputed for ${chain.count} events` : chain.reason || "No events yet") : "Waiting for events"),
        S.triCheck("Original sources unchanged", st ? unchanged : null, unchanged === null || unchanged === undefined ? "Not confirmed yet (rechecked at the end of the run)" : "SHA-256 of originals re-hashed after the run")));
  }

  function render(state) {
    const run = state.run;
    root.replaceChildren(
      h("div", { class: "stack-lg" },
        h("div", { class: "ov-hero" }, runCard(state), systemCard(state)),
        h("div", { class: "grid grid-4" }, moduleKpi(run), testsKpi(run), securityKpi(run), timeKpi(run)),
        h("div", { class: "grid grid-2" }, usageCard(run), integrityCard(run))));
  }

  PP.views.overview = {
    title: "Overview",
    sub: "System status and the current run",
    mount(el) { root = el; },
    update: render,
  };
})(window.PP);
