/*
 * Side columns that are visible on every tab:
 *   left  – runs opened in this browser (live ids + replayed reports)
 *   right – system status, current run, module/finding bars, integrity
 * Both read only PP.store.state; nothing here calls the API.
 */
(function (PP) {
  "use strict";

  const { h, icon, fmt, badge } = PP.util;
  const L = PP.labels;
  const S = PP.views.shared;

  // ---------- Left: run list ----------

  function entryLook(entry) {
    if (entry.origin === "replay") return { iconName: "file", tone: "info", label: "Saved report" };
    switch (entry.status) {
      case "done": return { iconName: "check", tone: "ok", label: "Done" };
      case "failed": return { iconName: "x", tone: "err", label: "Failed" };
      case "running": case "queued": return { iconName: "play", tone: "info", label: entry.status === "running" ? "Running" : "Queued" };
      case "lost": return { iconName: "alert", tone: "warn", label: "Not on server" };
      default: return { iconName: "refresh", tone: "muted", label: "Connecting" };
    }
  }

  function pipelineName(p) {
    if (!p) return null;
    return { simulation: "simulation", fixtures: "fixtures", live: "live", static_only: "not verified", analyze: "analyze", audit: "audit", compatibility: "compatibility" }[p] || p;
  }

  function currentKey(run) {
    return run ? (run.origin === "replay" ? "replay:" + run.fileName : run.id) : null;
  }

  let leftSignature = null;

  function renderLeft(state) {
    const host = document.getElementById("run-list");
    const active = currentKey(state.run);
    // Re-render only when the list changes, so an open file dialog keeps its input.
    const sig = JSON.stringify([active, state.history.map((e) => [e.key, e.status, e.events, e.pipeline])]);
    if (sig === leftSignature) return;
    leftSignature = sig;
    const rows = state.history.map((entry) => {
      const look = entryLook(entry);
      const sub = [entry.origin === "replay" ? "replay" : entry.source || "server run", look.label.toLowerCase(), pipelineName(entry.pipeline)].filter(Boolean).join(" · ");
      return h("button", {
        class: "list-row" + (entry.key === active ? " active" : ""), type: "button",
        title: entry.origin === "replay" ? entry.fileName : "Run " + entry.id,
        onclick: () => PP.store.openHistory(entry.key),
      },
      h("span", { class: "avatar", dataset: { tone: look.tone } }, icon(look.iconName)),
      h("span", { class: "meta" },
        h("span", { class: "name", style: { display: "block" } }, entry.origin === "replay" ? entry.fileName.replace(/\.json$/, "") : fmt.shortId(entry.id)),
        h("span", { class: "sub", style: { display: "block" } }, sub)),
      h("span", { class: "count", title: "Evidence events" }, fmt.int(entry.events || 0)));
    });

    host.replaceChildren(
      ...(rows.length ? rows : [h("div", { class: "empty", style: { padding: "24px 8px" } }, h("div", { class: "empty-title" }, "No runs yet"), h("p", null, "Start one with New run or replay a saved report."))]),
      h("div", { style: { marginTop: "12px" } }, S.replayButton("Replay saved report")),
      h("p", { class: "list-note" }, "Runs opened in this browser. The backend keeps runs in memory only, so older ids may be gone after a server restart."));
  }

  // ---------- Right: context ----------

  function block(title, ...body) {
    return h("div", { class: "panel-block" }, h("div", { class: "section-label" }, title), body);
  }

  function row(k, v) {
    return h("div", { class: "panel-row" }, h("span", { class: "k" }, k), h("span", { class: "v" }, v));
  }

  function bar(label, n, total, tone) {
    return h("div", { class: "bar-row" },
      h("div", { class: "bar-head" }, h("span", null, label), h("span", { class: "n" }, fmt.int(n))),
      h("div", { class: "bar-track" }, h("div", { class: "bar-fill" + (tone ? " bar-fill--" + tone : ""), style: { width: (total > 0 ? (n / total) * 100 : 0) + "%" } })));
  }

  function systemBlock(state) {
    const data = state.health.data;
    const online = state.health.status === "online";
    const llm = L.llmMode(data && data.llm_mode);
    const llmBadge = badge(llm.label, llm.tone);
    llmBadge.title = llm.desc;
    return block("System", h("div", { class: "panel-card" },
      row("Backend", online ? badge("Online", "ok") : state.health.status === "offline" ? badge("Offline", "err") : badge("Checking", "muted")),
      row("Docker", !data ? badge("Unknown", "muted") : data.docker ? badge("Available", "ok") : badge("Unavailable", "err")),
      row("AI mode", data ? llmBadge : badge("Unknown", "muted")),
      row("Meta AI", !data ? badge("Unknown", "muted") : data.llm_mode === "live" ? badge("Configured · unverified", "warn") : badge("Not connected", "muted"))));
  }

  function runBlock(run) {
    if (!run) {
      return block("Current run", h("div", { class: "panel-card" },
        h("div", { class: "muted", style: { fontSize: "12.5px" } }, "No run selected."),
        h("a", { class: "btn btn--primary btn--sm", href: "#/migration", style: { marginTop: "10px" } }, icon("play"), "New run")));
    }
    const st = run.state;
    const p = L.provenance(run);
    const provBadge = p ? badge(p.label, p.tone) : null;
    if (provBadge) provBadge.title = p.desc || "";
    return block("Current run", h("div", { class: "panel-card" },
      h("div", { class: "row-between", style: { marginBottom: "6px" } },
        h("span", { class: "big-number" }, st ? L.runStatus(st.status).label : run.lost ? "Lost" : "…"),
        st && (st.status === "running" || st.status === "queued") ? h("span", { class: "spinner" }) : null),
      row("Run", h("code", { title: run.id }, fmt.shortId(run.id))),
      row("Phase", st ? L.phaseLabel(st.phase) : "—"),
      row("Elapsed", st ? fmt.seconds(st.metrics.seconds) : "—"),
      row("Isolation", st ? (st.isolation === "docker" ? "Docker" : "Reduced") : "—"),
      provBadge ? h("div", { style: { marginTop: "10px" } }, provBadge) : null));
  }

  function modulesBlock(run) {
    const modules = run && run.state ? run.state.modules : [];
    if (!modules.length) return null;
    const total = modules.length;
    const count = (list) => modules.filter((m) => list.includes(m.status)).length;
    return block("Modules · " + total,
      bar("Green", count(["green"]), total, "ok"),
      bar("In progress", count(["translating", "testing", "fixing"]), total),
      bar("Pending", count(["pending"]), total, "muted"),
      bar("Failed", count(["failed"]), total, "err"),
      L.isSimulated(run) ? h("div", { class: "list-note" }, "Simulated statuses.") : null);
  }

  function findingsBlock(run) {
    const sec = run && run.state ? run.state.security : null;
    const findings = sec ? sec.findings || [] : [];
    if (!findings.length) return null;
    const total = findings.length;
    const sev = (s) => findings.filter((f) => f.severity === s).length;
    const review = findings.filter((f) => f.status === "needs_review").length;
    return block("Findings · " + total,
      bar("High", sev("HIGH"), total, "err"),
      bar("Medium", sev("MEDIUM"), total, "warn"),
      bar("Low", sev("LOW"), total, "muted"),
      h("div", { class: "panel-card", style: { marginTop: "10px" } },
        row("Before → after", `${fmt.int(sec.before)} → ${fmt.int(sec.after)}`),
        row("Needs review", review ? badge(String(review), "warn") : "0")),
      L.isSimulated(run) ? h("div", { class: "list-note" }, "Simulated findings (text heuristic, not Bandit).") : null);
  }

  function integrityBlock(run) {
    if (!run || !run.state) return null;
    const st = run.state;
    const chain = run.chain;
    const tri = (v) => { const t = L.tri(v); return badge(t.label, t.tone); };
    return block("Integrity", h("div", { class: "panel-card" },
      row("Originals unchanged", tri(st.hashes ? st.hashes.unchanged : null)),
      row("Chain (server)", tri(st.chain_intact)),
      row("Chain (browser)", tri(chain ? (chain.status === "ok" ? true : chain.status === "broken" ? false : null) : null))));
  }

  function renderRight(state) {
    const run = state.run;
    document.getElementById("right").replaceChildren(
      systemBlock(state),
      runBlock(run),
      modulesBlock(run) || document.createComment(""),
      findingsBlock(run) || document.createComment(""),
      integrityBlock(run) || document.createComment(""));
  }

  PP.panels = {
    render(state) {
      renderLeft(state);
      renderRight(state);
    },
  };
})(window.PP);
