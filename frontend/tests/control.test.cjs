const { test } = require("node:test");
const assert = require("node:assert/strict");
const { harness, response, deferred, flush, until, defaultReply } = require("./harness.cjs");
const F = require("./contract-fixtures.cjs");

function setup(t, handler = defaultReply, storage) {
  const h = harness(handler, storage); t.after(h.cleanup); return h;
}
async function ready(h) { await h.PP.control.refresh(); assert.equal(h.PP.control.state.mode, "v1"); }
const plain = (v) => JSON.parse(JSON.stringify(v));
const errorReply = (code, status, field) => response({ error: { code, message: code + " explanation", field } }, status);

test("only capabilities 404 selects legacy; legacy POST, state, events and report remain intact", async (t) => {
  const h = setup(t, (call) => {
    if (call.url === "/api/v1/capabilities") return response({}, 404, "text/html");
    if (call.url === "/api/runs" && call.method === "POST") return response({ run_id: "legacy-one" });
    if (call.url === "/api/runs/legacy-one") return response(F.state());
    return defaultReply(call);
  });
  await h.PP.control.refresh();
  assert.equal(h.PP.control.state.mode, "legacy");
  await h.PP.api.health();
  await h.PP.store.startRun("samples/legacy_shop", 2);
  await until(() => h.PP.store.state.run.reportStatus === "ready");
  assert.deepEqual(h.calls.find((c) => c.method === "POST").payload, { source_path: "samples/legacy_shop", max_iterations: 2 });
  assert.equal(h.PP.api.reportUrl("legacy-one", "html"), "/api/runs/legacy-one/report?format=html");
  assert.equal(h.PP.store.state.run.backendFinalized, true);
  assert.equal(h.calls.some((c) => c.url === "/api/v1/projects"), false);
});

for (const failure of ["503", "timeout", "invalid_json", "shape", "projects404"]) {
  test("discovery " + failure + " does not downgrade to legacy", async (t) => {
    const h = setup(t, (call) => {
      if (failure === "projects404" && call.url === "/api/v1/projects") return errorReply("not_found", 404);
      if (call.url === "/api/v1/capabilities") {
        if (failure === "503") return errorReply("preflight_unavailable", 503);
        if (failure === "timeout") throw Object.assign(new Error("timeout"), { name: "AbortError" });
        if (failure === "invalid_json") return { ...response({}), json: async () => { throw new Error("bad JSON"); } };
        if (failure === "shape") return response({});
      }
      return defaultReply(call);
    });
    await h.PP.control.refresh();
    assert.equal(h.PP.control.state.mode, "error");
    assert.ok(h.PP.control.state.error);
    await h.PP.control.submit(false);
    assert.equal(h.calls.some((c) => c.method === "POST"), false);
  });
}

test("version pairs and profiles come from capabilities/catalog, not installed-image presence", async (t) => {
  const caps = F.copy(F.capabilities);
  caps.runtimes.find((r) => r.version === "3.14").verified = true;
  const h = setup(t, (call) => call.url === "/api/v1/capabilities" ? response(caps) : defaultReply(call));
  await ready(h);
  assert.deepEqual(plain(h.PP.control.pairs("migration")), [["2.7", "3.12"]]);
  assert.deepEqual(plain(h.PP.control.sources("audit")), ["2.7", "3.12", "3.13"]);
  assert.deepEqual(plain(h.PP.control.pairs("compatibility")), [["3.12", "3.12"], ["3.12", "3.13"], ["3.13", "3.12"]]);
  caps.runtimes.find((r) => r.version === "3.13").available = null;
  await h.PP.control.refresh();
  assert.deepEqual(plain(h.PP.control.pairs("compatibility")), [["3.12", "3.12"]]);
  assert.equal(h.PP.control.choices().some((o) => o.mode === "live"), false);
});

test("Docker unavailable disables real operations but permits explicitly offered simulation", async (t) => {
  const caps = F.copy(F.capabilities); caps.docker.available = false;
  const h = setup(t, (call) => call.url === "/api/v1/capabilities" ? response(caps) : defaultReply(call));
  await ready(h);
  assert.equal(h.PP.control.choices().filter((o) => !o.reason).length, 1);
  assert.deepEqual(plain(h.PP.control.payload()), { operation: "migration", project_id: "legacy_shop", execution_mode: "simulation" });
  await h.PP.control.preflight(); assert.equal(h.PP.control.canStart(), true);
});

test("missing or cross-project profiles block migration without fabricated readiness", async (t) => {
  const projects = F.copy(F.projects); projects.fixture_profiles[0].available = false;
  const h = setup(t, (call) => call.url === "/api/v1/projects" ? response(projects) : defaultReply(call));
  await ready(h); await h.PP.control.preflight();
  assert.equal(h.PP.control.state.preflight.result.errors[0].code, "profile_unavailable");
  assert.equal(h.PP.control.canStart(), false);
  assert.equal(h.calls.some((c) => c.url.endsWith("/preflight")), false);
  h.PP.control.edit({ project_id: "universal_py3", fixture_profile_id: "legacy_shop_py27_py312" });
  assert.equal(h.PP.control.state.draft.fixture_profile_id, "");
});

test("audit and compatibility whitelist operation-specific fields; simulation omits runtime claims", async (t) => {
  const h = setup(t); await ready(h);
  h.PP.control.edit({ choice: "audit:offline", source_version: "3.13", docker_command: "forbidden" });
  assert.deepEqual(plain(h.PP.control.payload()), { operation: "audit", project_id: "legacy_shop", execution_mode: "offline", source_version: "3.13" });
  h.PP.control.edit({ choice: "compatibility:offline", project_id: "universal_py3", source_version: "3.12", target_version: "3.13", verification_level: "behavior" });
  assert.deepEqual(plain(h.PP.control.payload()), { operation: "compatibility", project_id: "universal_py3", execution_mode: "offline",
    source_version: "3.12", target_version: "3.13", verification_level: "behavior", cases_profile_id: "universal_py3_golden" });
  h.PP.control.edit({ verification_level: "syntax" });
  assert.equal("cases_profile_id" in h.PP.control.payload(), false);
  h.PP.control.edit({ choice: "migration:simulation" });
  assert.deepEqual(plain(h.PP.control.payload()), { operation: "migration", project_id: "universal_py3", execution_mode: "simulation" });
});

test("HTTP 200 blocked preflight preserves specific error and field, prevents creation", async (t) => {
  const h = setup(t, (call) => call.url.endsWith("/preflight") ? response({ can_start: false, parameters: call.payload,
    errors: [{ code: "docker_unavailable", message: "Start Docker Desktop", field: null }] }) : defaultReply(call));
  await ready(h); await h.PP.control.preflight(); await h.PP.control.submit(false);
  assert.equal(h.PP.control.state.preflight.result.can_start, false);
  assert.equal(h.PP.control.state.preflight.result.errors[0].message, "Start Docker Desktop");
  assert.equal(h.calls.some((c) => c.url === "/api/v1/runs"), false);
});

test("late preflight cannot approve changed configuration", async (t) => {
  const gate = deferred();
  const h = setup(t, (call) => call.url.endsWith("/preflight") ? gate.promise : defaultReply(call));
  await ready(h);
  const check = h.PP.control.preflight(); await flush();
  h.PP.control.edit({ choice: "audit:offline" });
  gate.resolve(response({ can_start: true, parameters: F.parameters, errors: [] })); await check;
  assert.equal(h.PP.control.state.preflight, null);
  assert.equal(h.PP.control.canStart(), false);
});

test("HTTP 202 starts a v1 run; duplicate clicks submit once with Idempotency-Key", async (t) => {
  const gate = deferred();
  const h = setup(t, (call) => call.url === "/api/v1/runs" ? gate.promise : defaultReply(call));
  await ready(h); await h.PP.control.preflight();
  const body = plain(h.PP.control.state.preflight.body);
  const first = h.PP.control.submit(false); await flush(); await h.PP.control.submit(false);
  gate.resolve(response({ run_id: "run-one" }, 202)); await first; await flush();
  const posts = h.calls.filter((c) => c.url === "/api/v1/runs");
  assert.equal(posts.length, 1); assert.match(posts[0].headers["Idempotency-Key"], /^[a-z0-9-]{36}$/i);
  assert.deepEqual(posts[0].payload, body);
  assert.equal(h.PP.store.state.run.apiMode, "v1");
  assert.equal(h.PP.control.state.pending, null);
  assert.ok(h.calls.some((c) => c.url === "/api/v1/runs/run-one"));
  assert.ok(h.calls.some((c) => c.url === "/api/runs/run-one/events?since=0"));
  assert.equal(h.calls.some((c) => c.url === "/api/runs"), false);
});

test("uncertain response retry preserves exact original key and payload after edits", async (t) => {
  let posts = 0;
  const h = setup(t, (call) => {
    if (call.url === "/api/v1/runs" && ++posts === 1) throw new Error("connection lost after acceptance");
    return defaultReply(call);
  });
  await ready(h); await h.PP.control.preflight(); await h.PP.control.submit(false);
  const intent = plain(h.PP.control.state.pending);
  assert.ok(intent);
  h.PP.control.edit({ choice: "audit:offline", source_version: "3.13" });
  await h.PP.control.preflight(); assert.equal(h.PP.control.canStart(), false);
  await h.PP.control.submit(true);
  const requests = h.calls.filter((c) => c.url === "/api/v1/runs");
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[0].payload, requests[1].payload);
  assert.equal(requests[0].body, requests[1].body);
  assert.equal(requests[0].headers["Idempotency-Key"], requests[1].headers["Idempotency-Key"]);
  assert.equal("verification_level" in requests[1].payload, false); // Do not replace by normalized preflight parameters.
});

test("new run intent receives a fresh key", async (t) => {
  const h = setup(t); await ready(h); await h.PP.control.preflight(); await h.PP.control.submit(false);
  h.PP.store.clearRun();
  await h.PP.control.preflight(); await h.PP.control.submit(false);
  const posts = h.calls.filter((c) => c.url === "/api/v1/runs");
  assert.notEqual(posts[0].headers["Idempotency-Key"], posts[1].headers["Idempotency-Key"]);
});

test("run_busy after successful preflight remains an error; no automatic retry or fallback", async (t) => {
  const h = setup(t, (call) => call.url === "/api/v1/runs" ? errorReply("run_busy", 409, null) : defaultReply(call));
  await ready(h); await h.PP.control.preflight(); await h.PP.control.submit(false);
  assert.equal(h.PP.store.state.startError.code, "run_busy");
  assert.equal(h.PP.control.state.preflight, null);
  assert.equal(h.PP.control.state.pending, null);
  assert.equal(h.PP.store.state.run, null);
  assert.equal(h.calls.filter((c) => c.url === "/api/v1/runs").length, 1);
});

test("instance change blocks uncertain retry and marks the intent stale", async (t) => {
  let changed = false;
  const h = setup(t, (call) => {
    if (changed && call.url === "/api/v1/capabilities") return response({ ...F.capabilities, instance_id: "instance-two" });
    if (call.url === "/api/v1/runs") throw new Error("uncertain");
    return defaultReply(call);
  });
  await ready(h); await h.PP.control.preflight(); await h.PP.control.submit(false);
  changed = true;
  await h.PP.control.submit(true);
  assert.equal(h.PP.control.state.pending.stale, true);
  assert.equal(h.PP.store.state.startError.code, "instance_changed");
  assert.equal(h.calls.filter((c) => c.url === "/api/v1/runs").length, 1);
});

test("instance change detected during polling cannot attach an old id to a new instance", async (t) => {
  const h = setup(t, (call) => call.url === "/api/v1/runs/run-one" ? response(F.details("running", { instance_id: "instance-two" })) : defaultReply(call));
  await ready(h); h.PP.store.attach("run-one", { apiMode: "v1", instanceId: "instance-one" });
  await until(() => h.PP.store.state.run.lost);
  assert.equal(h.PP.store.state.run.pollError.code, "instance_changed");
  assert.equal(h.calls.some((c) => c.url.includes("/report?")), false);
});

test("finalizing continues polling; backend completion, report, chain are independent", async (t) => {
  let finished = false;
  const gate = deferred();
  const h = setup(t, (call) => {
    if (call.url === "/api/v1/runs/run-one") return response(F.details(finished ? "done" : "finalizing"));
    if (call.url.endsWith("/report?format=json")) return gate.promise;
    return defaultReply(call);
  });
  await ready(h); h.PP.store.attach("run-one", { apiMode: "v1", instanceId: "instance-one" });
  await until(() => h.PP.store.state.run.control);
  assert.equal(h.PP.store.state.run.control.lifecycle, "finalizing");
  assert.equal(h.PP.store.state.run.backendFinalized, false);
  assert.equal(h.PP.store.state.run.reportStatus, "idle");
  assert.equal(h.calls.some((c) => c.url.includes("/report?")), false);
  finished = true; await h.tick();
  assert.equal(h.PP.store.state.run.backendFinalized, true);
  assert.equal(h.PP.store.state.run.reportStatus, "loading");
  assert.equal(h.PP.store.state.run.chain, null);
  gate.resolve(response(F.report()));
  await until(() => h.PP.store.state.run.reportStatus === "ready");
  await flush(); assert.equal(h.PP.store.state.run.chain.status, "empty");
});

test("resolved relative project uses returned id; arbitrary paths/commands never enter run payload", async (t) => {
  const h = setup(t, (call) => call.url === "/api/v1/projects/resolve"
    ? response({ project_id: "custom-123", relative_path: "samples/custom.py", kind: "file" }) : defaultReply(call));
  await ready(h); await h.PP.control.resolve("C:/secrets");
  assert.equal(h.PP.control.state.resolveError.code, "unsafe_project_path");
  assert.equal(h.calls.some((c) => c.url.endsWith("/resolve")), false);
  await h.PP.control.resolve("samples/custom.py");
  h.PP.control.edit({ choice: "audit:offline", source_version: "3.12" });
  assert.equal(h.PP.control.payload().project_id, "custom-123");
  assert.deepEqual(h.calls.find((c) => c.url.endsWith("/resolve")).payload, { root_id: "workspace", relative_path: "samples/custom.py" });
  assert.equal("source_path" in h.PP.control.payload(), false);
});

test("old saved reports remain read-only replay with no API calls", async (t) => {
  const h = setup(t, () => { throw new Error("Replay must not fetch"); });
  const report = F.report(); delete report.verification.control;
  const accepted = await h.PP.store.loadReplay({ name: "old-report.json", size: 1000, text: async () => JSON.stringify(report) });
  assert.equal(accepted, true); assert.equal(h.PP.store.state.run.origin, "replay");
  assert.match(h.PP.labels.provenance(h.PP.store.state.run).label, /^Saved report · Offline fixtures/);
  assert.equal(h.calls.length, 0);
});

test("per-run provenance overrides health and deployment; fixtures and simulation are not AI", async (t) => {
  const h = setup(t); h.PP.config.deployment.pipeline = "live";
  const run = { control: F.details(), origin: "live" };
  assert.equal(h.PP.labels.provenance(run).id, "fixtures");
  run.control.execution.effective = "simulation";
  assert.equal(h.PP.labels.isSimulated(run), true);
  run.origin = "replay"; assert.match(h.PP.labels.provenance(run).label, /^Saved report/);
  assert.equal(h.PP.labels.tri(null).label, "Not confirmed");
});

test("mounted form controls operate on actual draft and render blocked preflight details safely", async (t) => {
  const h = setup(t, (call) => call.url.endsWith("/preflight") ? response({ can_start: false, parameters: call.payload,
    errors: [{ code: "fixture_source_mismatch", message: "<script>untrusted</script>", field: "fixture_profile_id" }] }) : defaultReply(call));
  await ready(h);
  const root = h.document.createElement("div");
  const view = h.PP.controlForm.mount(root); view.update(h.PP.store.state);
  const buttons = root.querySelectorAll("button");
  buttons.find((b) => b.textContent.includes("Security Audit")).dispatch("click");
  view.update(h.PP.store.state);
  assert.equal(h.PP.control.state.draft.choice, "audit:offline");
  const version = root.querySelector("#control-source_version"); version.value = "3.13"; version.dispatch("change");
  view.update(h.PP.store.state);
  assert.equal(h.PP.control.payload().source_version, "3.13");
  root.querySelectorAll("button").find((b) => b.textContent === "Check readiness").dispatch("click");
  await flush(); view.update(h.PP.store.state);
  assert.match(root.textContent, /fixture_source_mismatch/);
  assert.match(root.textContent, /<script>untrusted<\/script>/); // Text only, never parsed as markup.
  assert.equal(root.querySelector("script"), null);
  assert.equal(root.querySelectorAll("button").find((b) => b.textContent.includes("Start run")).disabled, true);
});
