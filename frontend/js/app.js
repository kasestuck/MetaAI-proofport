/*
 * Shell: hash router, top bar (mode switch, run chip), persistent banners,
 * sidebar connection indicator. Views live in js/views/*.js and register
 * themselves on PP.views as { title, sub, mount(root), update(state) }.
 */
(function (PP) {
  "use strict";

  const { h, icon, fmt } = PP.util;
  const L = PP.labels;
  const store = PP.store;
  const ROUTES = ["overview", "migration", "security", "compatibility", "evidence"];

  let current = null;
  const mounted = new Set();

  function routeFromHash() {
    const name = (location.hash || "").replace(/^#\/?/, "").split(/[/?]/)[0];
    return ROUTES.includes(name) ? name : "overview";
  }

  function navigate() {
    const route = routeFromHash();
    if (route === current) return;
    current = route;
    for (const section of document.querySelectorAll(".view")) {
      const active = section.dataset.view === route;
      section.hidden = !active;
      if (active) {
        // Restart the enter animation on every visit.
        section.style.animation = "none";
        void section.offsetWidth;
        section.style.animation = "";
      }
    }
    for (const link of document.querySelectorAll(".nav-item")) {
      if (link.dataset.route === route) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    const view = PP.views[route];
    document.getElementById("view-title").textContent = view.title;
    document.getElementById("view-sub").textContent = view.sub;
    document.title = view.title + " · Proofport Console";
    const root = document.querySelector(`.view[data-view="${route}"]`);
    if (!mounted.has(route)) {
      view.mount(root);
      mounted.add(route);
    }
    updateView(route, true);
  }

  // Views re-render from data. To keep the UI stable while polling we
  // (1) skip renders when the relevant data did not change and
  // (2) keep <details> open/closed state and scroll offsets across renders.
  const lastSignature = {};

  function signature(state) {
    const r = state.run;
    return JSON.stringify([
      state.health.status, state.health.data, state.starting, state.startError && state.startError.code,
      r && [r.id, r.origin, r.state, r.events.length, r.reportStatus, r.chain && r.chain.status, r.finalized, r.lost, r.pollError && r.pollError.code, !!r.report],
    ]);
  }

  function updateView(route, force) {
    const view = PP.views[route];
    const root = document.querySelector(`.view[data-view="${route}"]`);
    const sig = signature(store.state);
    if (!force && lastSignature[route] === sig) return;
    lastSignature[route] = sig;

    const keyOf = (d) => d.dataset.key || (d.querySelector("summary") || d).textContent.trim();
    const open = new Set();
    const closed = new Set();
    for (const d of root.querySelectorAll("details")) (d.open ? open : closed).add(keyOf(d));
    const scrolls = new Map();
    for (const el of root.querySelectorAll("[data-scroll]")) scrolls.set(el.dataset.scroll, el.scrollTop);

    view.update(store.state);

    for (const d of root.querySelectorAll("details")) {
      const key = keyOf(d);
      if (open.has(key)) d.open = true;
      else if (closed.has(key)) d.open = false;
    }
    for (const el of root.querySelectorAll("[data-scroll]")) {
      if (scrolls.has(el.dataset.scroll)) el.scrollTop = scrolls.get(el.dataset.scroll);
    }
  }

  /** For views with local UI state (filters): re-render now, preserving disclosures. */
  function refresh() {
    if (current) updateView(current, true);
  }

  // ---------- Top bar ----------
  function renderModeSwitch(state) {
    const run = state.run;
    const health = state.health.data;
    let active = null;
    if (run && run.origin === "replay") active = "replay";
    else if (health) active = health.llm_mode;
    const llm = L.llmMode(health && health.llm_mode);
    const titles = {
      live: "Live — real Meta AI calls. " + (active === "live" ? llm.desc : "Not active."),
      mock: "Mock — no Meta AI calls. " + (active === "mock" ? llm.desc : "Not active."),
      replay: "Replay — viewing a saved run report. " + (active === "replay" ? "Loaded from a local file; nothing re-executed." : (health && health.llm_mode === "replay" ? llm.desc : "Not active.")),
    };
    for (const seg of document.querySelectorAll(".mode-seg")) {
      seg.dataset.active = String(seg.dataset.mode === active);
      seg.title = titles[seg.dataset.mode];
    }
  }

  function renderRunChip(state) {
    const chip = document.getElementById("run-chip");
    const run = state.run;
    if (!run) { chip.hidden = true; return; }
    chip.hidden = false;
    const status = run.state ? L.runStatus(run.state.status) : { label: run.lost ? "Lost" : "Connecting", tone: run.lost ? "err" : "muted" };
    const live = run.state && (run.state.status === "running" || run.state.status === "queued");
    chip.replaceChildren(
      h("span", { class: "dim" }, run.origin === "replay" ? "Saved" : "Run"),
      h("span", { class: "mono" }, fmt.shortId(run.id)),
      PP.util.badge(status.label, status.tone, live ? "badge--live" : ""),
    );
  }

  function renderConn(state) {
    const conn = document.getElementById("conn");
    const text = document.getElementById("conn-text");
    conn.dataset.state = state.health.status;
    text.textContent = state.health.status === "online" ? "Backend online" : state.health.status === "offline" ? "Backend offline" : "Connecting…";
    conn.title = text.textContent;
  }

  function renderNavCount(state) {
    const el = document.getElementById("nav-security-count");
    const findings = state.run && state.run.state && state.run.state.security ? state.run.state.security.findings || [] : [];
    const review = findings.filter((f) => f.status === "needs_review").length;
    el.hidden = review === 0;
    el.textContent = String(review);
    el.title = review + " finding(s) need review";
  }

  // ---------- Banners (persistent, honest context) ----------
  function banner(tone, iconName, title, text, actions) {
    return h("div", { class: `banner banner--${tone}` }, icon(iconName),
      h("div", { class: "banner-body" }, h("strong", null, title), text ? [" ", text] : null),
      actions ? h("div", { class: "banner-actions" }, actions) : null);
  }

  function renderBanners(state) {
    const host = document.getElementById("banners");
    const list = [];
    const health = state.health;
    const run = state.run;

    if (health.status === "offline") {
      list.push(banner("err", "offline", "Backend offline.",
        "Cannot reach " + (PP.config.apiBase || location.origin) + "/api/health. Retrying every " + Math.round(PP.config.healthIntervalMs / 1000) + " s. Start the server with start.bat or `python -m backend.launcher`."));
    }
    if (health.data) {
      const mode = health.data.llm_mode;
      if (mode === "mock") {
        list.push(banner("warn", "info", "Meta AI is not connected.",
          "LLM_MODE=mock: this deployment makes no Meta AI calls. Results come from simulation, offline fixtures or offline checks and are labelled as such."));
      } else if (mode === "replay") {
        list.push(banner("warn", "info", "Backend replay is not implemented.",
          "LLM_MODE=replay is configured, but the backend has no working replay path for migration or security generation."));
      } else if (mode === "live") {
        list.push(banner("info", "info", "Live mode configured.",
          "The health endpoint does not verify the Meta key, model or availability. AI results are claimed only after a run's report confirms recorded model calls and passing checks."));
      }
      if (health.data.docker === false) {
        list.push(banner("err", "box", "Docker unavailable.",
          "Docker was not available when the backend started. Dynamic verification cannot run and there is no host-execution fallback. Start Docker and restart the backend."));
      }
    }
    if (run && run.origin === "replay") {
      list.push(banner("info", "file", "Replay of a saved report.",
        `Viewing "${run.fileName}" from your computer. Nothing is re-executed; data is exactly what the report recorded.`,
        [h("button", { class: "btn btn--sm", type: "button", onclick: () => store.leaveReplay() }, "Exit replay")]));
    }
    if (run && L.isSimulated(run)) {
      list.push(banner("warn", "flask", "Simulation.",
        "Migration, tests, security fixes, tokens and cost in this run are simulated. Only file hashes and the evidence chain are real."));
    }
    if (run && run.chain && run.chain.status === "broken") {
      list.push(banner("err", "hash", "Evidence integrity failed.",
        `Browser re-verification of the evidence chain failed at seq ${run.chain.brokenAt}. Treat every result of this run as untrusted.`));
    }
    if (run && run.lost) {
      list.push(banner("err", "alert", "Run no longer available.",
        `Run ${fmt.shortId(run.id)} was not found on the server. Runs live in backend memory and are lost when it restarts.`,
        [h("button", { class: "btn btn--sm", type: "button", onclick: () => store.clearRun() }, "Dismiss")]));
    }
    host.replaceChildren(...list);
  }

  function renderShell(state) {
    renderConn(state);
    renderModeSwitch(state);
    renderRunChip(state);
    renderNavCount(state);
    renderBanners(state);
    if (current) updateView(current, current === "overview"); // overview shows the health check time
  }

  PP.app = { refresh };

  function init() {
    for (const el of document.querySelectorAll("[data-icon]")) el.replaceChildren(icon(el.dataset.icon));
    window.addEventListener("hashchange", navigate);
    store.subscribe(renderShell);
    navigate();
    renderShell(store.state);
    store.init();
  }

  window.addEventListener("error", (event) => console.error("[proofport] uncaught", event.error || event.message));
  window.addEventListener("unhandledrejection", (event) => console.error("[proofport] unhandled rejection", event.reason));

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})(window.PP);
