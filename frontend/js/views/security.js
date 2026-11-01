/*
 * Security: findings before/after, severity, Bandit confidence, CWE,
 * location, status, needs-review, fix attempts and rescans.
 *
 * RunState carries only {before, after, findings}. CWE/confidence/scope/
 * recommendation come from the final report (`verification.security_details`
 * and `verification.security_fix.decisions`), joined by finding id
 * (handoff §6). No Apply/Approve buttons: the backend has no such endpoint.
 */
(function (PP) {
  "use strict";

  const { h, icon, fmt, badge, card } = PP.util;
  const L = PP.labels;
  const S = PP.views.shared;

  let root;
  const filter = { status: "all", severity: "all" };
  const expanded = new Set();

  const SEV_ORDER = { HIGH: 0, MEDIUM: 1, LOW: 2 };

  function detailsIndex(report) {
    const index = new Map();
    if (!report) return index;
    const v = report.verification || {};
    const add = (list) => { if (Array.isArray(list)) for (const d of list) if (d && d.id && !index.has(d.id)) index.set(d.id, d); };
    add(v.security_fix && v.security_fix.decisions);
    add(v.security_details);
    add(v.security_fix && v.security_fix.findings_before);
    return index;
  }

  function cweText(cwe) {
    if (!cwe || cwe.id === undefined || cwe.id === null) return null;
    return "CWE-" + cwe.id;
  }

  // ---------- Summary ----------
  function summary(run) {
    const sec = run.state ? run.state.security : null;
    const findings = sec ? sec.findings || [] : [];
    const count = (s) => findings.filter((f) => f.status === s).length;
    const simulated = L.isSimulated(run); // simulated statuses get no success/warning color
    const kpi = (label, value, tone, foot, iconName) => card({ class: "kpi" },
      h("div", { class: "kpi-label" }, icon(iconName), label, S.simTag(run)),
      h("div", { class: "kpi-value", style: tone ? { color: `var(--${tone})` } : null }, value),
      h("div", { class: "kpi-foot" }, foot));
    return h("div", { class: "grid grid-4" },
      kpi("Before", sec ? fmt.int(sec.before) : "—", null, "Scanner warnings in the baseline scan", "security"),
      kpi("After", sec ? fmt.int(sec.after) : "—", null, "Warnings after migration / accepted fixes. Not a count of fixes.", "refresh"),
      kpi("Needs review", fmt.int(count("needs_review")), count("needs_review") && !simulated ? "warning" : null, "Manual decision required — not an accepted fix", "alert"),
      kpi("Fixed", fmt.int(count("fixed")), count("fixed") && !simulated ? "success" : null, simulated ? "Simulated status — no code was changed" : "Explicit fixed status only (never before − after)", "check"));
  }

  function contextNote(run) {
    const p = L.provenance(run);
    if (!p) return null;
    const notes = {
      simulation: "Simulated findings come from a text heuristic, not Bandit. Simulated “fixed” statuses changed nothing.",
      compatibility: "Compatibility mode does not run a security scan. Zero findings mean “not scanned”, not “secure”.",
      analyze: "Analyze mode does not run a security scan. Zero findings mean “not scanned”.",
      static_only: "Dynamic verification and scanning did not run. Zero findings mean “not scanned”.",
      audit: "Audit-only: static Bandit scan, no fixes, project not executed. Findings are potential risks.",
      fixtures: "Bandit 1.8.6 on Python 3.12. Python 2 files it cannot parse are skipped, so coverage may be partial.",
    };
    const text = notes[p.id];
    return text ? h("div", { class: "callout" }, icon("info", "icon-inline"), " ", text) : null;
  }

  // ---------- Findings table ----------
  function findingsCard(run) {
    const sec = run.state ? run.state.security : null;
    const all = sec ? (sec.findings || []).slice() : [];
    const index = detailsIndex(run.report);
    all.sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9) || String(a.file).localeCompare(String(b.file)) || a.line - b.line);

    const statuses = ["all", ...Array.from(new Set(all.map((f) => f.status)))];
    const severities = ["all", ...["HIGH", "MEDIUM", "LOW"].filter((s) => all.some((f) => f.severity === s))];
    if (!statuses.includes(filter.status)) filter.status = "all";
    if (!severities.includes(filter.severity)) filter.severity = "all";
    const shown = all.filter((f) => (filter.status === "all" || f.status === filter.status) && (filter.severity === "all" || f.severity === filter.severity));

    const chip = (group, value, label, n) => h("button", {
      class: "chip-btn", type: "button", "aria-pressed": String(filter[group] === value),
      onclick: () => { filter[group] = value; PP.app.refresh(); },
    }, label, n !== undefined ? h("span", { class: "count" }, String(n)) : null);

    const filters = all.length ? h("div", { class: "stack", style: { gap: "8px", padding: "0 20px 16px" } },
      h("div", { class: "filters" }, statuses.map((s) => chip("status", s, s === "all" ? "All statuses" : L.findingStatus(s).label, s === "all" ? all.length : all.filter((f) => f.status === s).length))),
      h("div", { class: "filters" }, severities.map((s) => chip("severity", s, s === "all" ? "All severities" : s, s === "all" ? undefined : all.filter((f) => f.severity === s).length)))) : null;

    const rows = [];
    for (const f of shown) {
      const d = index.get(f.id) || {};
      const st = L.findingStatus(f.status);
      const isOpen = expanded.has(f.id);
      const toggle = () => { if (expanded.has(f.id)) expanded.delete(f.id); else expanded.add(f.id); PP.app.refresh(); };
      rows.push(h("tr", { class: "is-clickable", tabindex: "0", "aria-expanded": String(isOpen), onclick: toggle,
        onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } } },
      h("td", null, h("span", { class: `sev sev--${f.severity}` }, f.severity)),
      h("td", null, d.confidence ? h("span", { class: "muted" }, d.confidence) : h("span", { class: "dim" }, run.report ? "—" : "…")),
      h("td", { class: "nowrap" }, cweText(d.cwe) ? h("code", null, cweText(d.cwe)) : h("span", { class: "dim" }, run.report ? "Unknown" : "…")),
      h("td", null, h("span", { class: "mono break" }, f.file), h("span", { class: "dim" }, ":" + f.line)),
      h("td", null, d.scanner_test ? h("code", { class: "muted" }, d.scanner_test) : h("span", { class: "dim" }, "—")),
      h("td", null, badge(st.label, st.tone)),
      h("td", { class: "break muted" }, d.description || f.note)));
      if (isOpen) {
        rows.push(h("tr", { class: "detail-row" }, h("td", { colspan: "7" },
          h("div", { class: "finding-detail" },
            PP.util.kv([
              ["Finding ID", h("code", null, f.id)],
              ["Status", h("span", null, badge(st.label, st.tone), " ", h("span", { class: "muted" }, st.desc))],
              ["Scope", d.scope ? h("code", null, d.scope) : undefined],
              ["Column", d.column !== undefined ? String(d.column) : undefined],
              ["Scanner", d.scanner ? `${d.scanner} ${d.scanner_test || ""}` : undefined],
              ["Verification", d.verification_status ? d.verification_status.replace(/_/g, " ") : undefined],
            ]),
            h("div", { class: "stack", style: { gap: "8px" } },
              h("div", null, h("div", { class: "section-label" }, "Note"), h("div", { class: "muted break" }, f.note)),
              d.proposed_fix ? h("div", null, h("div", { class: "section-label" }, "Recommendation (text, not a patch)"), h("div", { class: "break" }, d.proposed_fix)) : null,
              f.status === "needs_review" ? h("div", { class: "callout callout--warn" }, "Approve / reject actions are not available: the backend exposes no endpoint for security decisions.") : null)))));
      }
    }

    return card({ title: "Findings", flush: true, sub: run.report ? "Click a row for details. Confidence = Bandit confidence (HIGH/MEDIUM/LOW)." : "Confidence, CWE and recommendations appear with the final report.",
      actions: all.length ? badge(`${shown.length} of ${all.length}`, "muted") : null },
    filters,
    all.length
      ? (shown.length
        ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", null, h("tr", null, ["Severity", "Confidence", "CWE", "Location", "Test", "Status", "Issue"].map((t) => h("th", null, t)))),
          h("tbody", null, rows)))
        : PP.util.empty("security", "No findings match the filters", null))
      : PP.util.empty("security", "No findings", run.state
        ? (L.provenance(run) && ["compatibility", "analyze", "static_only"].includes(L.provenance(run).id) ? "The scanner did not run in this mode." : "The scanner reported no potential warnings so far. This is not proof of security.")
        : "Waiting for run state…"));
  }

  // ---------- Security Fix Engine ----------
  function checkMini(label, check) {
    let value;
    let tone;
    if (!check || check.ran === false) { value = "Not run"; tone = "muted"; }
    else if (check.passed === true) { value = "Passed"; tone = "ok"; }
    else if (check.passed === false) { value = "Failed"; tone = "err"; }
    else { value = "Unknown"; tone = "muted"; }
    return h("div", { class: "mini-check" }, h("span", { class: "label" }, label), badge(value, tone));
  }

  function attemptView(a) {
    const statusTone = a.applied && !a.rolled_back ? "ok" : a.rolled_back ? "err" : "warn";
    const checks = a.checks || {};
    return h("details", { class: "disclosure", dataset: { key: "attempt-" + a.id } },
      h("summary", null,
        h("div", { class: "attempt-head" },
          h("code", null, a.finding_id || "—"),
          h("span", { class: "mono dim" }, a.file || ""),
          badge(String(a.status || "unknown").replace(/_/g, " "), statusTone),
          a.rolled_back ? badge("Rolled back", "err") : null,
          a.applied && !a.rolled_back ? badge("Applied to working copy", "ok") : null,
          a.mode ? PP.util.tag(a.mode, "muted") : null)),
      h("div", { class: "disclosure-body stack" },
        a.explanation ? h("p", { class: "muted" }, a.explanation) : null,
        h("div", { class: "attempt-checks" },
          checkMini("Syntax", checks.syntax),
          checkMini("Golden cases", checks.golden),
          checkMini("Existing tests", checks.existing_tests),
          checkMini("Rescan", a.rescan)),
        PP.util.kv([
          ["Behavior impact", a.behavior_impact || undefined],
          ["Proposal confidence", typeof a.confidence === "number" ? a.confidence.toFixed(2) + " (provider-declared, 0–1; not Bandit confidence)" : undefined],
          ["Review areas", Array.isArray(a.review_areas) && a.review_areas.length ? a.review_areas.join(", ") : undefined],
          ["Rescan findings", a.rescan && Array.isArray(a.rescan.findings) ? String(a.rescan.findings.length) + (a.rescan.errors && a.rescan.errors.length ? ` · ${a.rescan.errors.length} parse errors` : "") : undefined],
          ["Originals unchanged", a.original_unchanged !== undefined ? badge(L.tri(a.original_unchanged).label, L.tri(a.original_unchanged).tone) : undefined],
        ]),
        Array.isArray(a.reasons) && a.reasons.length ? h("div", null, h("div", { class: "section-label" }, "Decision reasons"), S.limitations(a.reasons)) : null,
        a.diff ? h("div", null, h("div", { class: "section-label" }, "Proposed diff (redacted, shown as text)"), PP.util.diffBlock(a.diff)) : null));
  }

  function fixEngineCard(run) {
    const fix = run.report && run.report.verification ? run.report.verification.security_fix : null;
    if (!fix) return null;
    const attempts = Array.isArray(fix.attempts) ? fix.attempts : [];
    const len = (x) => (Array.isArray(x) ? x.length : 0);
    return card({ title: "Security Fix Engine", sub: "Finding → offline proposal → staged copy → syntax → golden → existing tests → Bandit rescan → policy decision",
      actions: [badge(fix.ai_generated ? "AI generated" : "Offline fixture · not AI", fix.ai_generated ? "info" : "muted"), badge("Status: " + (fix.status || "unknown"), fix.status === "verified" ? "ok" : "err")] },
    h("div", { class: "stack" },
      h("div", { class: "grid grid-4" },
        h("div", null, h("div", { class: "section-label" }, "Fixed"), h("div", { class: "kpi-value", style: { fontSize: "22px" } }, fmt.int(len(fix.fixed)))),
        h("div", null, h("div", { class: "section-label" }, "Needs review"), h("div", { class: "kpi-value", style: { fontSize: "22px" } }, fmt.int(len(fix.needs_review)))),
        h("div", null, h("div", { class: "section-label" }, "Rejected attempts"), h("div", { class: "kpi-value", style: { fontSize: "22px" } }, fmt.int(len(fix.rejected)))),
        h("div", null, h("div", { class: "section-label" }, "Findings before → after"), h("div", { class: "kpi-value", style: { fontSize: "22px" } }, `${len(fix.findings_before)} → ${len(fix.findings_after)}`))),
      h("div", { class: "row" },
        badge("Originals unchanged: " + L.tri(fix.original_unchanged).label, L.tri(fix.original_unchanged).tone),
        badge("Evidence chain: " + L.tri(fix.evidence_chain_intact).label, L.tri(fix.evidence_chain_intact).tone),
        fix.isolation ? badge("Isolation: " + fix.isolation, "muted") : null),
      h("p", { class: "dim", style: { fontSize: "12px" } },
        "“Needs review” and “rejected” can overlap: a proposal requiring review is also rejected when its changes were rolled back. “Verified” means the accepted project passed the recorded checks, not that every proposal was accepted."),
      attempts.length ? h("div", null, attempts.map(attemptView)) : h("div", { class: "muted" }, "No fix attempts were recorded.")));
  }

  // ---------- Rescan / scan coverage ----------
  function scanCard(run) {
    const v = run.report ? run.report.verification || {} : run.control && run.control.result.security_audit
      ? { security_audit: run.control.result.security_audit } : null;
    if (!v) return card({ title: "Scans & rescans" }, S.reportPending(run, "Scanner coverage, parse errors and rescan results arrive with the final report"));
    const scanRow = (label, scan) => scan ? [label, h("span", null,
      `${fmt.int(Array.isArray(scan.results) ? scan.results.length : 0)} warnings`,
      Array.isArray(scan.errors) && scan.errors.length ? h("span", { class: "dim" }, ` · ${scan.errors.length} parse errors (partial coverage)`) : h("span", { class: "dim" }, " · no parse errors"))] : [label, undefined];
    const audit = v.security_audit;
    const fix = v.security_fix;
    const rows = [
      scanRow("Baseline scan", v.security_before),
      scanRow("Target scan", v.security_after),
      scanRow("Accepted-copy rescan", fix && fix.scan_after),
      scanRow("Audit scan", audit && audit.scan),
      ["Audit coverage", audit ? badge(audit.coverage === "partial" ? "Partial (scanner errors)" : "Parsed files only", audit.coverage === "partial" ? "warn" : "muted") : undefined],
      ["Scanner Python", audit && audit.scanner_python ? audit.scanner_python : undefined],
      ["Project executed", audit ? String(!!audit.project_executed) : undefined],
      ["Fixes applied", audit ? String(!!audit.fixes_applied) : undefined],
    ];
    const any = rows.some((r) => r[1] !== undefined);
    return card({ title: "Scans & rescans", sub: "Bandit 1.8.6 static analysis. Results are potential risks; a clean scan is not proof of security." },
      any ? PP.util.kv(rows) : h("div", { class: "muted" }, "No security scan ran in this run."));
  }

  function render(state) {
    const run = state.run;
    if (!run) { root.replaceChildren(S.noRun()); return; }
    root.replaceChildren(h("div", { class: "stack-lg" },
      summary(run),
      contextNote(run),
      findingsCard(run),
      h("div", { class: "grid grid-2" }, scanCard(run), card({ title: "About these results" },
        h("ul", { class: "list-dots" },
          h("li", null, "Severity and confidence come from Bandit; findings are potential warnings, not proven exploits."),
          h("li", null, "Before/after count scanner warnings; the difference is not a number of fixes."),
          h("li", null, "Fixed means a verified patch was accepted in a working copy; originals are never edited."),
          h("li", null, "Security fixes are offline fixtures in this stage. Model-generated fixes are disabled in the backend.")))),
      fixEngineCard(run)));
  }

  PP.views.security = {
    title: "Security",
    sub: "Potential warnings, review decisions and verified fix attempts",
    mount(el) { root = el; },
    update: render,
  };
})(window.PP);
