/*
 * Building blocks shared by several views.
 */
(function (PP) {
  "use strict";

  const { h, icon, badge, empty } = PP.util;
  const L = PP.labels;

  PP.views = PP.views || {};

  const shared = {
    /** Empty state shown when no run is attached. */
    noRun(text) {
      return PP.util.card({},
        empty("play", "No run yet", text || "Start a run from the Migration section or open a saved report JSON to replay it.",
          h("div", { class: "row", style: { marginTop: "8px", justifyContent: "center" } },
            h("a", { class: "btn btn--primary", href: "#/migration" }, icon("play"), "Go to Migration"),
            shared.replayButton())));
    },

    /** Button + hidden file input that loads a saved report JSON (Replay). */
    replayButton(label) {
      const input = h("input", { type: "file", accept: ".json,application/json", hidden: true,
        onchange: async (e) => {
          const file = e.target.files && e.target.files[0];
          if (file) await PP.store.loadReplay(file);
          e.target.value = "";
        } });
      return h("span", null,
        h("button", { class: "btn", type: "button", title: "Open a report JSON previously downloaded from Proofport", onclick: () => input.click() },
          icon("upload"), label || "Open saved report"),
        input);
    },

    /** Callout for a failed run / API error with an actionable hint. */
    errorCallout(error, title) {
      if (!error) return null;
      const hint = L.errorHint(error.code);
      return h("div", { class: "callout callout--err", role: "alert" },
        h("div", { class: "callout-title" }, icon("alert"), title || "Run failed", h("code", { class: "dim" }, error.code || "error")),
        h("div", { class: "break" }, error.message || "No message provided."),
        hint ? h("div", { class: "muted", style: { marginTop: "4px" } }, hint) : null);
    },

    /** Non-fatal API/polling error (with backoff info). */
    pollErrorCallout(run) {
      if (!run || !run.pollError || run.lost) return null;
      const err = run.pollError;
      return h("div", { class: "callout callout--warn", role: "status" },
        h("div", { class: "callout-title" }, icon("refresh"), "Connection problem — retrying"),
        h("div", null, err.message, " ", h("code", { class: "dim" }, err.code)),
        h("div", { class: "muted" }, "If the server is still running, the run continues there. Polling resumes automatically with backoff."));
    },

    /** Notice that details arrive only with the final report. */
    reportPending(run, what) {
      if (!run) return null;
      if (run.reportStatus === "loading") {
        return h("div", { class: "callout row" }, h("span", { class: "spinner" }), "Fetching the final report…");
      }
      if (run.reportStatus === "error") {
        return h("div", { class: "callout callout--warn" },
          h("div", { class: "callout-title" }, icon("alert"), "Report unavailable"),
          h("div", null, run.reportError ? run.reportError.message : "Unknown error"),
          h("button", { class: "btn btn--sm", type: "button", style: { marginTop: "8px" }, onclick: () => PP.store.retryReport() }, icon("refresh"), "Retry"));
      }
      if (!run.report) {
        return h("div", { class: "callout" }, icon("info", "icon-inline"), " ",
          what || "Detailed results are published in the final report", " after the run finishes (API limitation: RunState carries only summary fields).");
      }
      return null;
    },

    statusBadge(status, live) {
      const s = L.runStatus(status);
      return badge(s.label, s.tone, live && (status === "running" || status === "queued") ? "badge--live" : "");
    },

    provenanceBadge(run) {
      const p = L.provenance(run);
      if (!p) return null;
      const el = badge(p.label, p.tone);
      el.title = p.desc || "";
      return el;
    },

    /** "SIMULATED" tag for values that must not be presented as real. */
    simTag(run) {
      return L.isSimulated(run) ? PP.util.tag("Simulated") : null;
    },

    triCheck(title, value, desc) {
      const t = L.tri(value);
      return h("div", { class: `check check--${t.tone}` },
        h("span", { class: "check-icon" }, icon(t.icon)),
        h("div", { class: "check-body" },
          h("div", { class: "row-between" }, h("span", { class: "check-title" }, title), badge(t.label, t.tone)),
          desc ? h("div", { class: "check-desc" }, desc) : null));
    },

    /** Test outcome list (unittest ids + status). Skipped is never shown as passed. */
    outcomes(tests, title) {
      if (!tests || !Array.isArray(tests.outcomes)) return null;
      const counts = { passed: 0, failed: 0, error: 0, skipped: 0 };
      for (const o of tests.outcomes) counts[o.status] = (counts[o.status] || 0) + 1;
      const tone = { passed: "ok", failed: "err", error: "err", skipped: "muted" };
      return h("div", { class: "stack" },
        h("div", { class: "row-between" },
          h("div", { class: "card-title" }, title, tests.python ? h("span", { class: "dim" }, "  · Python " + PP.util.fmt.pyVersion(tests.python)) : null),
          h("div", { class: "row" },
            badge(counts.passed + " passed", "ok"),
            counts.failed ? badge(counts.failed + " failed", "err") : null,
            counts.error ? badge(counts.error + " errors", "err") : null,
            counts.skipped ? badge(counts.skipped + " skipped", "muted") : null)),
        tests.outcomes.length
          ? h("div", { class: "table-wrap outcome-list" }, h("table", { class: "table" },
            h("tbody", null, tests.outcomes.map((o) => h("tr", null,
              h("td", { class: "mono break" }, o.id),
              h("td", { class: "col-num" }, badge(o.status, tone[o.status] || "muted")),
              o.reason ? h("td", { class: "muted break" }, o.reason) : h("td", null))))))
          : h("div", { class: "muted" }, "No tests ran (an empty suite is not a pass)."),
        tests.output ? h("details", { class: "disclosure" }, h("summary", null, "Raw test output"), h("div", { class: "disclosure-body" }, h("pre", { class: "code code--wrap" }, tests.output))) : null);
    },

    /** Report root `limitations` / `verification.limitations` list. */
    limitations(list) {
      if (!Array.isArray(list) || !list.length) return null;
      return h("ul", { class: "list-dots" }, list.map((t) => h("li", null, t)));
    },
  };

  PP.views.shared = shared;
})(window.PP);
