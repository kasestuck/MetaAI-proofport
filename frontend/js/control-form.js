/* Mounted once: form values/focus survive polling and asynchronous readiness updates. */
(function (PP) {
  "use strict";
  const { h, card, badge, icon } = PP.util;
  const C = PP.control;
  function mount(host) {
    const operationHost = h("div", { class: "op-grid" });
    const languageStatus = h("div", { class: "field-hint", role: "status", "aria-live": "polite" });
    const fields = {};
    const wrappers = {};
    function select(name, label) {
      const el = fields[name] = h("select", { class: "input", id: "control-" + name,
        onchange: () => C.edit({ [name]: el.value }) });
      wrappers[name] = h("label", { class: "field" }, h("span", { class: "field-label" }, label), el);
      return wrappers[name];
    }
    const iterations = fields.max_iterations = h("input", { class: "input num", id: "control-max_iterations", type: "number", min: "1", max: "5", step: "1", value: "5",
      oninput: () => C.edit({ max_iterations: iterations.value }) });
    wrappers.max_iterations = h("label", { class: "field" }, h("span", { class: "field-label" }, "Migration iterations (1–5)"), iterations);
    const path = h("input", { class: "input mono", type: "text", placeholder: "samples/my_project", autocomplete: "off", spellcheck: false });
    const resolve = h("button", { class: "btn", type: "button", onclick: () => C.resolve(path.value.trim()) }, "Resolve project");
    const resolveStatus = h("div", { role: "status" });
    const readiness = h("div", { class: "ready-list", role: "status", "aria-live": "polite" });
    const errors = h("div", { class: "stack", role: "alert" });
    const preflight = h("button", { class: "btn", type: "button", onclick: () => C.preflight() }, "Check readiness");
    const start = h("button", { class: "btn btn--primary btn--lg", type: "submit" }, icon("play"), "Start run");
    const retry = h("button", { class: "btn", type: "button", onclick: () => C.submit(true) }, "Retry identical submission");
    const discard = h("button", { class: "btn", type: "button", onclick: () => {
      if (window.confirm("The previous request may have started a run. Forget its retry key? Check the existing run before creating another.")) C.discardPending();
    } }, "Forget uncertain submission…");
    const pending = h("div", { class: "stack" });
    const status = h("div", { class: "stack" });
    const form = h("form", { class: "stack", novalidate: true, onsubmit: (e) => { e.preventDefault(); C.submit(false); } },
      select("language", "Project language"), languageStatus, operationHost,
      h("div", { class: "grid grid-2" },
        select("project_id", "Registered project"),
        select("source_version", "Source Python (verified runtime)"),
        select("target_version", "Target Python (verified runtime)"),
        select("verification_level", "Compatibility verification"),
        select("fixture_profile_id", "Offline fixture profile"),
        select("cases_profile_id", "Golden cases profile"),
        select("security_fix_profile_id", "Optional security fixture checks · not AI"), wrappers.max_iterations),
      h("details", { class: "disclosure", dataset: { key: "control-custom-project" } },
        h("summary", null, "Register another workspace project"),
        h("div", { class: "disclosure-body stack" },
          h("label", { class: "field" }, h("span", { class: "field-label" }, "Workspace-relative path"), path,
            h("span", { class: "field-hint" }, "No upload or Git clone. The backend validates the path and returns a project ID. Custom projects do not acquire migration or golden profiles automatically.")),
          resolve, resolveStatus)),
      h("div", { class: "ready-card" }, readiness, errors, pending,
        h("div", { class: "row ready-action" }, preflight, start)),
      status);
    const refresh = h("button", { class: "btn btn--sm", type: "button", onclick: () => C.refresh() }, icon("refresh"), "Refresh capabilities");
    const discovery = h("div", { role: "status" });
    host.replaceChildren(card({ title: "Run control", sub: "Choose a registered project and an available operation. No .env changes or Meta API calls.", actions: refresh },
      h("div", { class: "stack" }, discovery, form)));
    let operationSignature, optionsSignature;
    const errorNode = (err) => h("div", { class: "callout callout--err" },
      h("strong", null, String(err.code || "error")), err.field ? h("code", null, " · " + err.field) : null,
      h("p", null, String(err.message || "Unknown error")));
    function options(name, entries, value) {
      const el = fields[name];
      el.replaceChildren(...(entries.length ? entries : [{ value: "", label: "None available", disabled: true }]).map((e) => h("option", {
        value: e.value, disabled: !!e.disabled,
      }, e.label)));
      el.value = value || "";
    }
    function update(state) {
      const c = state.control;
      const d = c.draft;
      const v1 = c.mode === "v1";
      refresh.disabled = c.loading || state.starting || c.resolving;
      form.hidden = !v1;
      discovery.replaceChildren(...(c.loading ? [h("span", { class: "spinner" }), " Loading backend capabilities…"]
        : c.error ? [errorNode(c.error)]
        : c.mode === "legacy" ? ["Legacy backend: operation selection is unavailable. The existing form below uses the five legacy endpoints."]
        : [badge("Control API v1", "info"), h("span", { class: "field-hint" }, " Readiness is checked again when a run is created.")]));
      if (!v1) return;
      const choices = C.choices();
      const php = d.language === "php";
      const language = php ? "PHP" : "Python";
      const languageReason = C.languageReason();
      const policy = C.languageCaps();
      const phpEntry = c.capabilities.languages && c.capabilities.languages.php;
      languageStatus.textContent = languageReason || (php ? "PHP readiness is based on the local backend proof. Static audit does not execute project code."
        : phpEntry && !phpEntry.readiness.can_start ? "PHP unavailable: " + (phpEntry.readiness.reason || "No verified operations") : "Operations and versions come from backend capabilities.");
      const current = choices.find((o) => o.id === d.choice);
      const simulation = current && current.mode === "simulation";
      const migration = current && current.operation === "migration" && !simulation;
      const compatibility = current && current.operation === "compatibility";
      const opSig = JSON.stringify([choices, d.choice, d.language, c.loading, state.starting]);
      if (operationSignature !== opSig) {
        operationSignature = opSig;
        operationHost.replaceChildren(...choices.map((o) => h("button", { class: "op-card", type: "button",
          "aria-pressed": String(o.id === d.choice), disabled: !!o.reason || c.loading || state.starting,
          dataset: { active: String(o.id === d.choice), dim: String(!!o.reason) }, onclick: () => C.edit({ choice: o.id }) },
        h("strong", null, o.label), h("p", { class: "op-text" }, o.reason || (o.mode === "simulation"
          ? "Demo only: simulated tests, migration and metrics."
          : o.mode === "offline_fixtures" ? "Pre-written patches verified in Docker; not AI migration."
            : php && o.operation === "audit" ? "Limited PHP static rules; no project execution, Docker or AI required."
              : "Offline checks in Docker; no AI or code translation.")))));
      }
      const sig = JSON.stringify([d, c.projects, policy, c.loading, state.starting]);
      if (optionsSignature !== sig) {
        optionsSignature = sig;
        options("language", [{ value: "python", label: "Python" }, { value: "php", label: "PHP" + (!phpEntry || !phpEntry.readiness.can_start ? " · unavailable" : "") }], d.language);
        options("project_id", C.projectChoices().map((p) => ({ value: p.project_id,
          label: p.project_id + " · " + p.relative_path + (p.available ? "" : " · " + (p.reason || "unavailable")), disabled: !p.available })), d.project_id);
        options("source_version", C.sources(current && current.operation).map((v) => ({ value: v, label: language + " " + v })), d.source_version);
        options("target_version", C.pairs(current && current.operation).filter(([s]) => s === d.source_version).map(([, v]) => ({ value: v, label: language + " " + v })), d.target_version);
        options("verification_level", C.levels().map((v) => ({ value: v, label: { syntax: "Syntax only (no behavior claim)", tests: "Existing tests", behavior: "Tests + recorded behavior" }[v] })), d.verification_level);
        for (const type of ["cases", "fixture"]) options(type + "_profile_id", C.profiles(type, d.project_id).map((p) => ({ value: p.id, label: p.id })), d[type + "_profile_id"]);
        options("security_fix_profile_id", [{ value: "", label: "None · migration only" }, ...C.profiles("security_fix", d.project_id).map((p) => ({ value: p.id, label: p.id + " · offline fixture" }))], d.security_fix_profile_id);
        iterations.value = String(d.max_iterations);
      }
      wrappers.source_version.hidden = !!simulation;
      wrappers.target_version.hidden = !migration && !compatibility;
      wrappers.verification_level.hidden = !compatibility;
      wrappers.fixture_profile_id.hidden = !migration;
      wrappers.cases_profile_id.hidden = !migration && !(compatibility && d.verification_level === "behavior");
      wrappers.max_iterations.hidden = !migration;
      wrappers.security_fix_profile_id.hidden = !php || !migration || !C.profiles("security_fix", d.project_id).length;
      wrappers.source_version.querySelector(".field-label").textContent = "Source " + language + (php && current && current.operation === "audit" ? " (operator label · static audit)" : " (verified runtime)");
      wrappers.target_version.querySelector(".field-label").textContent = "Target " + language + " (verified runtime)";
      for (const el of Object.values(fields)) el.disabled = c.loading || state.starting || c.resolving;
      path.disabled = state.starting || c.resolving || c.loading;
      resolve.disabled = path.disabled;
      resolve.textContent = c.resolving ? "Resolving…" : "Resolve project";
      resolveStatus.replaceChildren(c.resolveError ? errorNode(c.resolveError) : document.createComment(""));
      const pf = c.preflight;
      readiness.replaceChildren(
        h("div", { class: "ready-row" }, "Language", badge(language, "info")),
        h("div", { class: "ready-row" }, "Docker", badge(c.capabilities.docker.available ? "Available" : "Unavailable", c.capabilities.docker.available ? "ok" : "err")),
        h("div", { class: "ready-row" }, "Meta AI", badge("Disabled · " + (c.capabilities.live.reason || "not authorized"), "muted")),
        h("div", { class: "ready-row" }, "Preflight", badge(c.checking ? "Checking…" : pf ? pf.result.can_start ? "Ready for this configuration" : "Blocked" : "Not checked", pf ? pf.result.can_start ? "ok" : "err" : "muted")),
        h("p", { class: "field-hint" }, "A successful preflight does not reserve the worker slot. " + (php ? "PHP lexical warnings" : "Bandit warnings") + " are potential risks; a clean scan does not prove security."));
      errors.replaceChildren(...(languageReason ? [h("div", { class: "callout callout--warn" }, languageReason)] : []), ...(pf && pf.result.errors || []).map(errorNode), ...(state.startError ? [errorNode(state.startError)] : []));
      const active = state.run && state.run.origin !== "replay" && !state.run.backendFinalized && !state.run.lost;
      preflight.disabled = c.loading || c.checking || c.resolving || state.starting || !!languageReason || !current;
      preflight.textContent = c.checking ? "Checking readiness…" : "Check readiness";
      start.disabled = !C.canStart() || state.starting || !!active;
      start.replaceChildren(state.starting ? h("span", { class: "spinner" }) : icon("play"), state.starting ? "Starting…" : active ? "Run in progress" : "Start run");
      pending.replaceChildren(...(c.pending ? [h("p", { class: "field-hint" }, "Original submission: " + PP.labels.languageName(c.pending.body.language) + " · " + c.pending.body.operation + " · " + c.pending.body.project_id), h("p", { class: "field-hint" }, c.pending.stale
        ? "Backend instance changed. The old request will not be repeated. Review any saved run before starting another."
        : "Submission outcome is uncertain. Retry uses the original configuration and key, even if the form has changed."), retry, discard] : []));
      retry.disabled = !c.pending || c.pending.stale || state.starting || c.loading;
      discard.disabled = state.starting;
      const run = state.run;
      status.replaceChildren(...(run ? [h("div", { class: "ready-list" },
        h("div", { class: "ready-row" }, "Backend task", badge(run.origin === "replay" ? "Saved report replay" : run.lost ? "Not on this instance" : run.control ? run.control.lifecycle : run.state ? run.state.status : "Connecting", "info")),
        h("div", { class: "ready-row" }, "Final report", badge(run.reportStatus, run.reportStatus === "ready" ? "ok" : "muted")),
        h("div", { class: "ready-row" }, "Evidence chain (browser)", badge(run.chain ? run.chain.status : "Not checked", run.chain && run.chain.status === "ok" ? "ok" : "muted")),
        run.reportError ? errorNode(run.reportError) : null,
        run.reportStatus === "error" && !run.lost ? h("button", { class: "btn", type: "button", onclick: () => PP.store.retryReport() }, "Retry report retrieval") : null)] : []));
    }
    return { update };
  }
  PP.controlForm = { mount };
})(window.PP);
