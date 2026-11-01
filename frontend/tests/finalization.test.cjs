const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const { harness, response, deferred, flush, until, defaultReply } = require("./harness.cjs");
const F = require("./contract-fixtures.cjs");

function setup(t, handler = defaultReply, storage) { const h = harness(handler, storage); t.after(h.cleanup); return h; }
function entry(h, detail) {
  const e = { seq: 1, prev_hash: "0".repeat(64), type: "run_finished", detail, ts: "2026-11-01T00:00:00Z", module: null };
  e.entry_hash = createHash("sha256").update(e.prev_hash + h.PP.integrity.canonical(e)).digest("hex");
  return e;
}

test("backend may finish while report export fails; report retrieval retries never create runs", async (t) => {
  let available = false;
  const h = setup(t, (call) => {
    if (call.url === "/api/v1/runs/run-one") return response(F.details());
    if (call.url.endsWith("/report?format=json") && !available) return response({ error: { code: "report_unavailable", message: "Report export failed" } }, 503);
    return defaultReply(call);
  });
  await h.PP.control.refresh(); h.PP.store.attach("run-one", { apiMode: "v1", instanceId: "instance-one" });
  await flush();
  for (let i = 0; i < 3; i++) await h.tick();
  await until(() => h.PP.store.state.run.reportStatus === "error");
  const run = h.PP.store.state.run;
  assert.equal(run.backendFinalized, true);
  assert.equal(run.report, null);
  assert.equal(run.reportError.code, "report_unavailable");
  available = true; h.PP.store.retryReport();
  await until(() => run.reportStatus === "ready");
  assert.equal(h.calls.some((c) => c.method === "POST"), false);
});

test("inconsistent report is never accepted as a completed export", async (t) => {
  const h = setup(t, (call) => {
    if (call.url === "/api/v1/runs/run-one") return response(F.details());
    if (call.url.endsWith("/report?format=json")) { const r = F.report(); r.state.status = "running"; return response(r); }
    return defaultReply(call);
  });
  await h.PP.control.refresh(); h.PP.store.attach("run-one", { apiMode: "v1", instanceId: "instance-one" });
  await flush(); for (let i = 0; i < 3; i++) await h.tick();
  await until(() => h.PP.store.state.run.reportStatus === "error");
  assert.equal(h.PP.store.state.run.reportError.code, "report_inconsistent");
  assert.equal(h.PP.store.state.run.report, null);
});

for (const corrupt of [false, true]) {
  test("report receipt is independent of " + (corrupt ? "broken" : "valid") + " evidence chain verification", async (t) => {
    let events = [];
    const h = setup(t, (call) => {
      if (call.url === "/api/v1/runs/run-one") return response(F.details());
      if (call.url.includes("/events?since=")) return response(call.url.endsWith("since=0") ? events : []);
      if (call.url.endsWith("/report?format=json")) return response(F.report(events));
      return defaultReply(call);
    });
    events = [entry(h, "Frontend hash-chain fixture")];
    if (corrupt) events[0].detail = "changed";
    await h.PP.control.refresh(); h.PP.store.attach("run-one", { apiMode: "v1", instanceId: "instance-one" });
    await until(() => h.PP.store.state.run.reportStatus === "ready");
    await until(() => ["ok", "broken"].includes(h.PP.store.state.run.chain.status));
    assert.equal(h.PP.store.state.run.chain.status, corrupt ? "broken" : "ok");
    assert.equal(h.PP.store.state.run.backendFinalized, true);
    assert.equal(h.PP.store.state.run.reportStatus, "ready");
    assert.ok(h.calls.some((c) => c.url.endsWith("/events?since=1")));
  });
}

test("stale polling cannot overwrite persistence of a newly attached run", async (t) => {
  const gate = deferred();
  const h = setup(t, (call) => call.url === "/api/v1/runs/run-one" ? gate.promise
    : call.url === "/api/v1/runs/run-two" ? response(F.details("running", { run_id: "run-two" })) : defaultReply(call));
  await h.PP.control.refresh(); h.PP.store.attach("run-one", { apiMode: "v1", instanceId: "instance-one" });
  await flush(); h.PP.store.attach("run-two", { apiMode: "v1", instanceId: "instance-one" });
  await flush(); gate.resolve(response(F.details())); await flush();
  assert.equal(h.PP.store.state.run.id, "run-two");
  assert.equal(JSON.parse(h.storage.get(h.PP.config.storageKey)).id, "run-two");
});

test("malformed run metadata does not poll legacy state as a fallback", async (t) => {
  const h = setup(t, (call) => call.url === "/api/v1/runs/run-one" ? response({ state: F.state() }) : defaultReply(call));
  await h.PP.control.refresh(); h.PP.store.attach("run-one", { apiMode: "v1", instanceId: "instance-one" });
  await until(() => h.PP.store.state.run.pollError);
  assert.equal(h.PP.store.state.run.pollError.code, "unexpected_response");
  assert.equal(h.calls.some((c) => c.url === "/api/runs/run-one"), false);
});

test("404 run lookup marks it lost and never initiates a new request", async (t) => {
  const h = setup(t, (call) => call.url === "/api/v1/runs/run-one" ? response({ error: { code: "run_not_found", message: "Gone" } }, 404) : defaultReply(call));
  await h.PP.control.refresh(); h.PP.store.attach("run-one", { apiMode: "v1", instanceId: "instance-one" });
  await until(() => h.PP.store.state.run.lost);
  assert.equal(h.PP.control.state.mode, "v1");
  assert.equal(h.calls.some((c) => c.method === "POST"), false);
});

test("same pending intent survives reload without automatically re-submitting", async (t) => {
  const first = setup(t, (call) => {
    if (call.url === "/api/v1/runs") throw new Error("Response lost");
    return defaultReply(call);
  });
  await first.PP.control.refresh(); await first.PP.control.preflight(); await first.PP.control.submit(false);
  const intent = JSON.parse(JSON.stringify(first.PP.control.state.pending));
  const second = setup(t, defaultReply, Object.fromEntries(first.storage));
  await second.PP.control.init();
  assert.equal(second.calls.some((c) => c.method === "POST"), false);
  assert.equal(second.PP.control.state.pending.key, intent.key);
  await second.PP.control.submit(true);
  const posted = second.calls.find((c) => c.url === "/api/v1/runs");
  assert.deepEqual(posted.payload, intent.body);
  assert.equal(posted.headers["Idempotency-Key"], intent.key);
});

test("pending intent from a previous instance is disabled on reload", async (t) => {
  const key = "proofport.console.lastRun.pending";
  const h = setup(t, defaultReply, { [key]: JSON.stringify({ key: "previous-key-123", instanceId: "previous-instance",
    body: { operation: "migration", execution_mode: "simulation", project_id: "legacy_shop" } }) });
  await h.PP.control.init();
  assert.equal(h.PP.control.state.pending.stale, true);
  await h.PP.control.submit(true);
  assert.equal(h.calls.some((c) => c.method === "POST"), false);
});

test("stored request with unsafe extra fields is never restored or sent", async (t) => {
  const h = setup(t, defaultReply, { "proofport.console.lastRun.pending": JSON.stringify({ key: "previous-key-123", instanceId: "instance-one",
    body: { operation: "migration", execution_mode: "simulation", project_id: "legacy_shop", docker_command: "forbidden" } }) });
  await h.PP.control.init(); await h.PP.control.submit(true);
  assert.equal(h.PP.control.state.pending, null);
  assert.equal(h.calls.some((c) => c.method === "POST"), false);
});

test("validation errors retain the backend field for the frontend", async (t) => {
  const h = setup(t, (call) => call.url.endsWith("/preflight") ? response({ error: {
    code: "incompatible_parameters", message: "Select another target", field: "target_version",
  } }, 422) : defaultReply(call));
  await h.PP.control.refresh(); await h.PP.control.preflight();
  const error = h.PP.control.state.preflight.result.errors[0];
  assert.equal(error.field, "target_version"); assert.equal(error.status, 422);
});

test("malformed preflight approval does not enable Start", async (t) => {
  const h = setup(t, (call) => call.url.endsWith("/preflight") ? response({ can_start: true, errors: [] }) : defaultReply(call));
  await h.PP.control.refresh(); await h.PP.control.preflight();
  assert.equal(h.PP.control.canStart(), false);
  assert.equal(h.PP.control.state.preflight.result.errors[0].code, "unexpected_response");
});

test("even malformed JSON on capabilities 404 selects the legacy API", async (t) => {
  const h = setup(t, () => ({ ...response({}, 404), json: async () => { throw new Error("bad JSON"); } }));
  await h.PP.control.refresh(); assert.equal(h.PP.control.state.mode, "legacy");
});

test("response body timeout stays a timeout, not legacy fallback", async (t) => {
  const h = setup(t, (call) => ({ ...response({}), json: () => new Promise((resolve, reject) => {
    call.signal.addEventListener("abort", () => reject(Object.assign(new Error("timeout"), { name: "AbortError" })));
  }) }));
  h.PP.config.requestTimeoutMs = 5;
  await h.PP.control.refresh();
  assert.equal(h.PP.control.state.error.code, "timeout");
  assert.equal(h.PP.control.state.mode, "error");
});

test("all dashboard views render v1 partial results, finalizing and old replay data", async (t) => {
  const h = setup(t); await h.PP.control.refresh();
  for (const view of ["shared", "overview", "migration", "security", "compatibility", "evidence"]) h.load("js/views/" + view + ".js");
  h.load("js/panels.js"); h.load("js/app.js"); // Shell registration only; DOMContentLoaded is not dispatched.
  for (const [key, id] of [["div", "run-list"], ["aside", "right"]]) {
    const el = h.document.createElement(key); el.setAttribute("id", id); h.document.appendChild(el);
  }
  const states = [F.details("finalizing"), F.details()];
  states[0].result.compatibility = { level: "syntax_compatible", syntax_compatible: true, tests_passed: null, behavior_verified: null };
  states[0].result.security_audit = { coverage: "partial", scan: { results: [], errors: [{ reason: "parse error" }] }, project_executed: false, fixes_applied: false };
  for (const details of states) {
    h.PP.store.state.run = { id: details.run_id, origin: "live", state: details.state, control: details, source: "legacy_shop", events: [],
      report: null, reportStatus: "idle", phasesSeen: ["reporting"], seqs: new Set(), chain: null };
    for (const [name, view] of Object.entries(h.PP.views)) {
      if (!view.mount) continue;
      const root = h.document.createElement("div"); view.mount(root); view.update(h.PP.store.state);
      assert.ok(root.children.length, name);
    }
    h.PP.panels.render(h.PP.store.state);
  }
  const old = F.report(); delete old.verification.control;
  await h.PP.store.loadReplay({ name: "old-report.json", size: 1024, text: async () => JSON.stringify(old) });
  for (const view of Object.values(h.PP.views)) {
    if (!view.mount) continue;
    const root = h.document.createElement("div"); view.mount(root); view.update(h.PP.store.state);
    assert.ok(root.children.length);
  }
  h.PP.panels.render(h.PP.store.state);
  assert.match(h.document.getElementById("right").textContent, /Final report/);
});

test("operation UI exposes only server-offered choices and filters unavailable runtimes", async (t) => {
  const caps = F.copy(F.capabilities); delete caps.operations.audit;
  caps.operations.migration.execution_modes = ["offline_fixtures"];
  caps.runtimes.find((r) => r.version === "3.13").verified = false;
  const h = setup(t, (call) => call.url === "/api/v1/capabilities" ? response(caps) : defaultReply(call));
  await h.PP.control.refresh();
  const root = h.document.createElement("div"), view = h.PP.controlForm.mount(root);
  h.PP.control.edit({ choice: "compatibility:offline" }); view.update(h.PP.store.state);
  const cards = root.querySelectorAll("button.op-card");
  assert.equal(cards.length, 2);
  assert.equal(cards.some((b) => b.textContent.includes("Simulation") || b.textContent.includes("Security Audit")), false);
  assert.deepEqual(root.querySelector("#control-target_version").children.map((e) => e.value), ["3.12"]);
});

test("capabilities refresh invalidates an already successful preflight", async (t) => {
  const h = setup(t); await h.PP.control.refresh(); await h.PP.control.preflight();
  assert.equal(h.PP.control.canStart(), true);
  await h.PP.control.refresh();
  assert.equal(h.PP.control.state.preflight, null);
  assert.equal(h.PP.control.canStart(), false);
});
