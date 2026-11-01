/* Local control-plane state. Only whitelisted request fields leave the browser.
 * Discovery falls back ONLY on capabilities 404. No paid/live request is offered.
 */
(function (PP) {
  "use strict";
  const { api, store } = PP;
  const c = store.state.control = {
    mode: "loading", capabilities: null, projects: null, error: null,
    loading: false, resolving: false, resolveError: null,
    draft: {}, revision: 0, preflight: null, checking: false, pending: null,
  };
  const pendingStorage = PP.config.storageKey + ".pending";
  let discovery = 0, preflightToken = 0, resolveToken = 0;
  const problem = (code, message, field) => new api.ApiError("control", 0, code, message, field);
  const failShape = () => { throw problem("unexpected_response", "The control API returned an invalid response. Legacy fallback is disabled."); };
  const object = (v) => v && typeof v === "object" && !Array.isArray(v);
  const strings = (v) => Array.isArray(v) && v.every((x) => typeof x === "string");

  function validateCapabilities(data) {
    if (!object(data) || data.api_version !== "1" || typeof data.instance_id !== "string" || !data.instance_id
      || !object(data.docker) || typeof data.docker.available !== "boolean" || !object(data.scanner)
      || !Array.isArray(data.runtimes) || !data.runtimes.every((r) => object(r) && typeof r.version === "string")
      || !object(data.operations) || !object(data.live)) failShape();
    for (const [op, entry] of Object.entries(data.operations)) {
      if (!object(entry) || !strings(entry.execution_modes)) failShape();
      if (op === "migration" || op === "compatibility") {
        if (!Array.isArray(entry.pairs) || !entry.pairs.every((p) => strings(p) && p.length === 2)) failShape();
      } else if (op === "audit" && !strings(entry.source_versions)) failShape();
    }
    return data;
  }
  function validateProjects(data) {
    if (!object(data) || data.root_id !== "workspace" || !Array.isArray(data.projects)
      || !data.projects.every((p) => object(p) && typeof p.project_id === "string" && typeof p.relative_path === "string" && typeof p.available === "boolean")
      || ![data.cases_profiles, data.fixture_profiles].every((a) => Array.isArray(a) && a.every((p) => object(p)
        && typeof p.id === "string" && typeof p.project_id === "string" && typeof p.available === "boolean"))) failShape();
    return data;
  }
  function invalidate() {
    c.revision++;
    preflightToken++;
    c.preflight = null;
    c.checking = false;
    store.state.startError = null;
  }
  function runtime(version, role) {
    return c.capabilities && c.capabilities.runtimes.some((r) => r.version === version && r[role] === true
      && r.configured === true && r.available === true && r.verified === true);
  }
  function pairs(operation) {
    const entry = c.capabilities && c.capabilities.operations[operation];
    return (entry && entry.pairs || []).filter(([source, target]) => runtime(source, "source") && runtime(target, "target"));
  }
  function sources(operation) {
    const entry = c.capabilities && c.capabilities.operations[operation];
    return operation === "audit" ? (entry && entry.source_versions || []).filter((v) => runtime(v, "source"))
      : [...new Set(pairs(operation).map((p) => p[0]))];
  }
  function profiles(type, projectId) {
    return (c.projects && c.projects[type + "_profiles"] || []).filter((p) => p.project_id === projectId && p.available === true);
  }
  function choices() {
    const result = [];
    const caps = c.capabilities;
    if (!caps) return result;
    for (const [operation, entry] of Object.entries(caps.operations)) {
      if (!["migration", "audit", "compatibility"].includes(operation)) continue;
      for (const mode of entry.execution_modes) {
        if (!(operation === "migration" && ["simulation", "offline_fixtures"].includes(mode)) && !(operation !== "migration" && mode === "offline")) continue;
        const reason = mode === "simulation" ? null : !caps.docker.available ? "Docker unavailable"
          : !sources(operation).length ? "No verified runtime combination"
          : ["audit", "migration"].includes(operation) && caps.scanner.available !== true ? "Bandit scanner unavailable" : null;
        result.push({ id: operation + ":" + mode, operation, mode, reason,
          label: mode === "simulation" ? "Simulation" : { migration: "Migration", audit: "Security Audit", compatibility: "Compatibility Check" }[operation] });
      }
    }
    return result;
  }
  function normalize() {
    const d = c.draft;
    const options = choices();
    if (!options.some((o) => o.id === d.choice)) d.choice = (options.find((o) => !o.reason) || options[0] || {}).id || "";
    const choice = options.find((o) => o.id === d.choice);
    const projects = c.projects && c.projects.projects || [];
    if (!projects.some((p) => p.project_id === d.project_id && p.available)) d.project_id = (projects.find((p) => p.available) || {}).project_id || "";
    if (choice && choice.mode !== "simulation") {
      const versions = sources(choice.operation);
      if (!versions.includes(d.source_version)) d.source_version = versions[0] || "";
      const targets = pairs(choice.operation).filter((p) => p[0] === d.source_version).map((p) => p[1]);
      if (!targets.includes(d.target_version)) d.target_version = targets[0] || "";
    }
    for (const type of ["cases", "fixture"]) {
      const entries = profiles(type, d.project_id);
      if (!entries.some((p) => p.id === d[type + "_profile_id"])) d[type + "_profile_id"] = (entries[0] || {}).id || "";
    }
    if (!["syntax", "tests", "behavior"].includes(d.verification_level)) d.verification_level = "tests";
    if (d.max_iterations === undefined) d.max_iterations = 5;
  }
  function edit(values) {
    Object.assign(c.draft, values);
    invalidate();
    normalize();
    store.emit();
  }
  function payload() {
    const d = c.draft;
    const choice = choices().find((o) => o.id === d.choice);
    if (!choice || choice.reason) throw problem("operation_unavailable", choice && choice.reason || "No operation available.", "operation");
    if (!(c.projects.projects || []).some((p) => p.project_id === d.project_id && p.available)) throw problem("project_not_found", "Select an available registered project.", "project_id");
    const body = { operation: choice.operation, project_id: d.project_id, execution_mode: choice.mode };
    if (choice.mode === "simulation") return body;
    body.source_version = d.source_version;
    if (!sources(choice.operation).includes(d.source_version)) throw problem("unverified_version", "Select a verified source runtime.", "source_version");
    if (choice.operation !== "audit") {
      if (!pairs(choice.operation).some(([s, t]) => s === d.source_version && t === d.target_version)) throw problem("unsupported_python_pair", "Select an allowed verified version pair.", "target_version");
      body.target_version = d.target_version;
    }
    if (choice.operation === "migration") {
      body.max_iterations = Number(d.max_iterations);
      if (!Number.isInteger(body.max_iterations) || body.max_iterations < 1 || body.max_iterations > 5) throw problem("invalid_request", "Iterations must be an integer from 1 to 5.", "max_iterations");
      body.fixture_profile_id = d.fixture_profile_id;
      body.cases_profile_id = d.cases_profile_id;
    } else if (choice.operation === "compatibility") {
      body.verification_level = d.verification_level;
      if (d.verification_level === "behavior") body.cases_profile_id = d.cases_profile_id;
    }
    for (const type of ["cases", "fixture"]) {
      const field = type + "_profile_id";
      if (field in body && !profiles(type, d.project_id).some((p) => p.id === body[field])) throw problem("profile_unavailable", "No available project-bound " + type + " profile. Choose another project or verification level explicitly.", field);
    }
    return body;
  }
  function savePending() {
    try {
      if (c.pending) localStorage.setItem(pendingStorage, JSON.stringify(c.pending));
      else localStorage.removeItem(pendingStorage);
    } catch (_) { /* Memory still permits same-request retries until reload. */ }
  }
  function observeInstance(id) {
    const previous = c.capabilities && c.capabilities.instance_id;
    if (previous && id !== previous) {
      invalidate();
      c.error = problem("instance_changed", "Backend instance changed. Refresh projects and review the configuration; an old submission will not be repeated.");
      c.mode = "error";
      const run = store.state.run;
      if (run && run.origin !== "replay" && run.instanceId && run.instanceId !== id) {
        run.lost = true;
        run.polling = false;
        run.pollError = c.error;
      }
    }
    if (c.pending && c.pending.instanceId !== id) { c.pending.stale = true; savePending(); }
    store.emit();
  }
  async function refresh() {
    const token = ++discovery;
    invalidate();
    c.loading = true;
    c.error = null;
    store.emit();
    try {
      let caps;
      try { caps = await api.capabilities(); }
      catch (err) {
        if (token !== discovery) return;
        if (err.kind === "http" && err.status === 404) {
          c.mode = "legacy"; c.capabilities = null; c.projects = null;
          return;
        }
        throw err;
      }
      validateCapabilities(caps);
      const projects = validateProjects(await api.projects());
      if (token !== discovery) return;
      observeInstance(caps.instance_id);
      // Custom registrations from a previous instance must not survive restart.
      c.capabilities = caps;
      c.projects = projects;
      c.mode = "v1";
      normalize();
    } catch (err) {
      if (token === discovery) { c.mode = "error"; c.error = err; }
    } finally {
      if (token === discovery) { c.loading = false; store.emit(); }
    }
  }
  async function resolve(relativePath) {
    const token = ++resolveToken;
    c.resolving = true; c.resolveError = null;
    invalidate(); store.emit();
    const instance = c.capabilities && c.capabilities.instance_id;
    try {
      // Server remains authoritative, including junction/link and secret policy.
      if (!relativePath || /(^[\\/]|:|(^|[\\/])\.\.([\\/]|$))/.test(relativePath)) throw problem("unsafe_project_path", "Use a workspace-relative path without traversal or a drive prefix.", "relative_path");
      const result = await api.resolveProject(relativePath);
      if (token !== resolveToken || !c.capabilities || instance !== c.capabilities.instance_id) return;
      if (!object(result) || typeof result.project_id !== "string" || typeof result.relative_path !== "string" || !["file", "directory"].includes(result.kind)) failShape();
      c.projects.projects = c.projects.projects.filter((p) => p.project_id !== result.project_id).concat(Object.assign({}, result, { available: true }));
      edit({ project_id: result.project_id });
    } catch (err) { if (token === resolveToken) c.resolveError = err; }
    finally { if (token === resolveToken) { c.resolving = false; store.emit(); } }
  }
  async function preflight() {
    const token = ++preflightToken, revision = c.revision;
    c.preflight = null; c.checking = true; store.emit();
    try {
      if (c.mode !== "v1" || c.loading) throw problem("control_unavailable", "Refresh control-plane readiness first.");
      const body = payload();
      const result = await api.preflight(body);
      if (token !== preflightToken || revision !== c.revision) return;
      if (!object(result) || typeof result.can_start !== "boolean" || !Array.isArray(result.errors)
        || !result.errors.every((e) => object(e) && typeof e.code === "string" && typeof e.message === "string")
        || (result.can_start && result.errors.length) || !object(result.parameters)) failShape();
      c.preflight = { revision, instanceId: c.capabilities.instance_id, body: Object.freeze(body), result };
    } catch (err) {
      if (token === preflightToken && revision === c.revision) c.preflight = { revision, result: { can_start: false, errors: [err] } };
    } finally { if (token === preflightToken) { c.checking = false; store.emit(); } }
  }
  function canStart() {
    return !!(c.mode === "v1" && !c.loading && !c.resolving && !c.checking && !c.pending && c.preflight
      && c.preflight.revision === c.revision && c.preflight.instanceId === c.capabilities.instance_id && c.preflight.result.can_start === true);
  }
  async function submit(retry) {
    if (store.state.starting) return;
    if (!retry && !canStart()) return;
    if (retry && (!c.pending || c.pending.stale)) return;
    store.state.starting = true; store.state.startError = null; store.emit();
    try {
      if (!retry) {
        c.pending = { key: crypto.randomUUID(), body: Object.freeze(JSON.parse(JSON.stringify(c.preflight.body))), instanceId: c.capabilities.instance_id };
        savePending();
      }
      const pending = c.pending;
      // Check instance even on explicit retry; never send an old key to a new server.
      const caps = validateCapabilities(await api.capabilities());
      observeInstance(caps.instance_id);
      if (pending.stale || caps.instance_id !== pending.instanceId) throw problem("instance_changed", "Backend restarted. The previous submission must be reviewed; it was not repeated.");
      const response = await api.createRun(pending.body, pending.key);
      if (!object(response) || typeof response.run_id !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(response.run_id)) failShape();
      store.attach(response.run_id, { source: pending.body.project_id, maxIterations: pending.body.max_iterations,
        apiMode: "v1", instanceId: pending.instanceId });
      c.pending = null; savePending(); invalidate();
    } catch (err) {
      store.state.startError = err;
      // Network/parse/server errors can hide an accepted request. Preserve the exact intent.
      if (err.kind === "http" && err.status >= 400 && err.status < 500) { c.pending = null; savePending(); }
      if (err.code !== "instance_changed") { c.preflight = null; }
    } finally { store.state.starting = false; store.emit(); }
  }
  function discardPending() {
    c.pending = null; savePending(); invalidate(); store.emit();
  }
  function init() {
    try {
      const p = JSON.parse(localStorage.getItem(pendingStorage) || "null");
      const allowed = ["operation", "project_id", "execution_mode", "source_version", "target_version", "max_iterations", "verification_level", "cases_profile_id", "fixture_profile_id"];
      if (p && typeof p.key === "string" && /^[A-Za-z0-9_-]{8,128}$/.test(p.key) && object(p.body)
        && ["migration", "audit", "compatibility"].includes(p.body.operation)
        && ["offline_fixtures", "offline", "simulation"].includes(p.body.execution_mode)
        && typeof p.body.project_id === "string" && typeof p.instanceId === "string"
        && Object.keys(p.body).every((key) => allowed.includes(key))) { p.body = Object.freeze(p.body); c.pending = p; }
    } catch (_) { /* Invalid local storage is ignored. */ }
    return refresh();
  }
  PP.control = { state: c, init, refresh, edit, resolve, preflight, canStart, submit, discardPending,
    choices, sources, pairs, profiles, payload, observeInstance, validateCapabilities, validateProjects };
})(window.PP);
