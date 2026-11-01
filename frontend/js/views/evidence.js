/*
 * Evidence: SHA-256 of sources, originals-unchanged check, evidence chain
 * integrity (server + independent browser re-verification), event timeline,
 * test results and HTML/JSON export.
 *
 * The timeline is append-only in the DOM: new events animate in without
 * re-rendering older ones, and the scroll position is preserved.
 */
(function (PP) {
  "use strict";

  const { h, icon, fmt, badge, card } = PP.util;
  const L = PP.labels;
  const S = PP.views.shared;

  let root, top, hashesBody, hashesMeta, hashFilterInput, tlFilters, tlList, tlCount, tlCard, hashesCard, testsHost, noRunHost;
  let renderedRun = null;
  const renderedSeqs = new Set();
  let typeFilter = "all";

  // ---------- Integrity + export ----------
  function integrityItem(tone, iconName, title, desc) {
    return h("div", { class: "integrity-item", dataset: { tone } },
      h("span", { class: "integrity-icon" }, icon(iconName)),
      h("div", null, h("div", { class: "integrity-title" }, title), h("div", { class: "integrity-desc" }, desc)));
  }

  function integrityCard(run) {
    const st = run.state;
    const unchanged = st && st.hashes ? st.hashes.unchanged : null;
    const chain = run.chain;
    const server = st ? st.chain_intact : null;
    return card({ title: "Integrity", sub: "Local consistency checks — not an external signature or certification" },
      h("div", { class: "integrity" },
        integrityItem(unchanged === true ? "ok" : unchanged === false ? "err" : "muted", "lock", "Original sources",
          unchanged === true ? "Re-hashed after the run: unchanged." : unchanged === false ? "Original files changed or could not be re-hashed." : "Not confirmed yet (rechecked when the run ends)."),
        integrityItem(server === true ? "ok" : server === false ? "err" : "muted", "server", "Evidence chain (server)",
          server === true ? "Backend reports chain_intact = true." : server === false ? "Backend reports the chain is broken." : "No state yet."),
        integrityItem(!chain ? "muted" : chain.status === "ok" ? "ok" : chain.status === "broken" ? "err" : "warn", "hash", "Evidence chain (browser)",
          !chain ? "Waiting for events…"
            : chain.status === "ok" ? `Recomputed SHA-256 links for all ${chain.count} received events.`
              : chain.status === "broken" ? `Broken at seq ${chain.brokenAt}: ${chain.reason}`
                : chain.reason || "No events.")));
  }

  function exportCard(run) {
    const terminal = run.state && PP.store.TERMINAL.has(run.state.status);
    let body;
    if (run.origin === "replay") {
      body = h("div", { class: "stack" },
        h("p", { class: "muted" }, "This is a saved report loaded from your computer. Server exports are available only for runs that still exist on the backend."),
        h("div", { class: "row" }, h("button", { class: "btn", type: "button", onclick: () => downloadJson(run.report, run.fileName) }, icon("download"), "Save JSON copy")));
    } else if (run.lost) {
      body = h("p", { class: "muted" }, "The run no longer exists on the server; its report cannot be downloaded through the API.");
    } else {
      const link = (fmtName, label) => h("a", {
        class: "btn" + (fmtName === "html" ? " btn--primary" : ""),
        href: terminal ? PP.api.reportUrl(run.id, fmtName) : "#",
        download: `proofport-${run.id}.${fmtName}`,
        "aria-disabled": String(!terminal),
        onclick: terminal ? null : (e) => e.preventDefault(),
      }, icon("download"), label);
      body = h("div", { class: "stack" },
        h("div", { class: "row" }, link("html", "Download HTML report"), link("json", "Download JSON report")),
        h("p", { class: "field-hint" }, terminal
          ? "Exports are also available for failed runs. Open the HTML file locally; it is self-contained."
          : "Reports are available after the run finishes (the API returns 409 run_not_finished before that)."));
    }
    return card({ title: "Export", sub: "GET /api/runs/{id}/report?format=html|json" }, body);
  }

  function downloadJson(data, name) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = h("a", { href: URL.createObjectURL(blob), download: name || "proofport-report.json" });
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }

  // ---------- Hashes ----------
  function renderHashes(run) {
    const hashes = run.state && run.state.hashes ? run.state.hashes : {};
    const files = Object.keys(hashes).filter((k) => k !== "unchanged" && typeof hashes[k] === "string").sort();
    const q = hashFilterInput.value.trim().toLowerCase();
    const shown = q ? files.filter((f) => f.toLowerCase().includes(q) || hashes[f].includes(q)) : files;
    hashesMeta.replaceChildren(badge(`${files.length} files`, "muted"));
    hashesBody.replaceChildren(...(shown.length
      ? shown.map((f) => h("tr", null, h("td", { class: "file-cell" }, f), h("td", { class: "hash-cell" }, hashes[f])))
      : [h("tr", null, h("td", { colspan: "2", class: "muted" }, files.length ? "No files match the filter." : "No hashes recorded yet."))]));
  }

  // ---------- Timeline ----------
  function eventRow(event, isNew) {
    const t = L.eventType(event.type);
    return h("div", { class: "tl-item" + (isNew ? " is-new" : ""), dataset: { type: String(event.type) }, role: "listitem" },
      h("span", { class: "tl-seq" }, "#" + event.seq),
      h("span", { class: "tl-time", title: String(event.ts) + " (UTC)" }, fmt.time(event.ts)),
      h("span", { class: "tl-type", dataset: { tone: t.tone } }, h("span", { class: "tl-dot" }), h("code", null, String(event.type))),
      h("div", { class: "tl-detail" },
        event.module ? h("span", { class: "tl-module" }, String(event.module)) : null,
        String(event.detail === undefined ? "" : event.detail),
        h("span", { class: "tl-hash", title: "entry_hash " + event.entry_hash + "\nprev_hash " + event.prev_hash }, "↳ " + fmt.shortHash(event.entry_hash, 16))));
  }

  function applyTypeFilter() {
    for (const el of tlList.children) {
      if (el.dataset && el.dataset.type) el.hidden = typeFilter !== "all" && el.dataset.type !== typeFilter;
    }
  }

  function renderTimeline(run) {
    if (renderedRun !== run) {
      renderedRun = run;
      renderedSeqs.clear();
      tlList.replaceChildren();
      typeFilter = "all";
    }
    const initial = renderedSeqs.size === 0;
    for (const event of run.events) {
      if (renderedSeqs.has(event.seq)) continue;
      renderedSeqs.add(event.seq);
      // Events arrive in seq order; insert defensively if one fills a gap.
      const row = eventRow(event, !initial && run.origin !== "replay");
      const next = Array.from(tlList.children).find((el) => Number(el.dataset.seq) > event.seq);
      row.dataset.seq = String(event.seq);
      if (next) tlList.insertBefore(row, next); else tlList.appendChild(row);
    }
    if (!run.events.length) {
      if (!tlList.querySelector(".empty")) tlList.replaceChildren(PP.util.empty("evidence", "No events yet", "Events appear here as the backend appends them (polled every second)."));
    } else {
      const placeholder = tlList.querySelector(".empty");
      if (placeholder) placeholder.remove();
    }
    tlCount.replaceChildren(badge(`${run.events.length} events`, "muted"));

    const types = Array.from(new Set(run.events.map((e) => String(e.type))));
    if (typeFilter !== "all" && !types.includes(typeFilter)) typeFilter = "all";
    const chip = (value, label, n) => h("button", {
      class: "chip-btn", type: "button", "aria-pressed": String(typeFilter === value),
      onclick: () => { typeFilter = value; renderTimeline(run); },
    }, label, n !== undefined ? h("span", { class: "count" }, String(n)) : null);
    tlFilters.replaceChildren(chip("all", "All"), ...types.map((t) => chip(t, L.eventType(t).label, run.events.filter((e) => String(e.type) === t).length)));
    applyTypeFilter();
  }

  // ---------- Tests ----------
  function renderTests(run) {
    const v = run.report ? run.report.verification || {} : null;
    if (!v) {
      testsHost.replaceChildren(card({ title: "Test results" }, S.reportPending(run, "Individual test outcomes are published in the final report")));
      return;
    }
    const blocks = [];
    if (v.legacy_tests) blocks.push(card({}, S.outcomes(v.legacy_tests, "Existing tests on source")));
    if (v.source_tests) blocks.push(card({}, S.outcomes(v.source_tests, "Existing tests on source")));
    if (v.target_tests) blocks.push(card({}, S.outcomes(v.target_tests, "Existing tests on target")));
    if (v.compatibility && v.compatibility.existing_tests) blocks.push(card({}, S.outcomes(v.compatibility.existing_tests, "Existing tests on target")));
    if (Array.isArray(v.comparisons) && v.comparisons.length) {
      const matched = v.comparisons.filter((c) => c.matches).length;
      blocks.push(card({ title: "Golden comparisons", sub: "Recorded source behavior vs target" },
        h("div", { class: "stack" },
          h("div", { class: "row-between" }, h("span", null, "Cases matched"), h("span", { class: "num" }, `${matched} / ${v.comparisons.length}`)),
          PP.util.progress(matched, v.comparisons.length, matched === v.comparisons.length ? "ok" : "err", false, "ev-cases-" + run.id))));
    }
    if (!blocks.length) {
      blocks.push(card({ title: "Test results" }, h("div", { class: "muted" },
        L.isSimulated(run) ? "Simulation: no tests were executed." : "No test results were recorded in this run.")));
    }
    testsHost.replaceChildren(h("div", { class: "grid grid-2" }, blocks));
  }

  function render(state) {
    const run = state.run;
    const hasRun = !!run;
    noRunHost.hidden = hasRun;
    for (const el of [top, hashesCard, tlCard, testsHost]) el.hidden = !hasRun;
    if (!run) {
      noRunHost.replaceChildren(S.noRun("Evidence (hashes, events, integrity) is produced by a run. Start one in Migration or open a saved report."));
      renderedRun = null;
      return;
    }
    top.replaceChildren(h("div", { class: "grid grid-2" }, integrityCard(run), exportCard(run)));
    renderHashes(run);
    renderTimeline(run);
    renderTests(run);
  }

  PP.views.evidence = {
    title: "Evidence",
    sub: "Source hashes, hash-chained event log, tests and exports",
    mount(el) {
      root = el;
      noRunHost = h("div");
      top = h("div");
      hashFilterInput = h("input", { class: "input", type: "search", placeholder: "Filter files or hashes…", "aria-label": "Filter hashes", style: { width: "260px" },
        oninput: () => PP.store.state.run && renderHashes(PP.store.state.run) });
      hashesBody = h("tbody");
      hashesMeta = h("span");
      hashesCard = card({ title: "Source SHA-256", flush: true, sub: "Hashes of the actual source bytes recorded at run start", actions: [hashesMeta, hashFilterInput] },
        h("div", { class: "table-wrap", style: { maxHeight: "420px", overflowY: "auto" }, dataset: { scroll: "hashes" } },
          h("table", { class: "table hash-table" }, h("thead", null, h("tr", null, h("th", null, "File"), h("th", null, "SHA-256"))), hashesBody)));
      tlFilters = h("div", { class: "filters" });
      tlCount = h("span");
      tlList = h("div", { class: "timeline", role: "list", "aria-live": "polite" });
      tlCard = card({ title: "Event timeline", flush: true, sub: "seq order · local time (hover for UTC) · `patch_applied` means a staged candidate, not an accepted fix", actions: tlCount },
        h("div", { style: { padding: "0 20px 12px" } }, tlFilters),
        h("div", { class: "tl-scroll", dataset: { scroll: "timeline" } }, tlList));
      testsHost = h("div");
      root.replaceChildren(h("div", { class: "stack-lg" }, noRunHost, top, hashesCard, tlCard, testsHost));
    },
    update: render,
  };
})(window.PP);
