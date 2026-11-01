/* Explicit three-operation real HTTP/Docker/browser verification. Not included
 * in *.test.cjs. No screenshot, video, trace, fabricated results or model calls.
 * Requires the opt-in tests/integration_probe.py server and local Playwright.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createHash, randomUUID } = require("node:crypto");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "../..");
const base = process.env.PROOFPORT_INTEGRATION_URL;
if (process.env.PROOFPORT_INTEGRATION_TESTS !== "1" || !/^http:\/\/127\.0\.0\.1:(8001|8765)$/.test(base || "")) {
  throw new Error("Explicit PROOFPORT_INTEGRATION_TESTS=1 and loopback PROOFPORT_INTEGRATION_URL required.");
}
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const artifacts = path.join(root, "backend/.tmp", "p43-real-" + stamp);
fs.mkdirSync(artifacts, { recursive: true });
const save = (name, data) => fs.writeFileSync(path.join(artifacts, name), typeof data === "string" ? data : JSON.stringify(data, null, 2));
function hashes(relative) {
  const result = {};
  function visit(folder) {
    for (const item of fs.readdirSync(folder, { withFileTypes: true })) {
      const file = path.join(folder, item.name);
      assert.equal(item.isSymbolicLink(), false, "Unexpected link in verification project");
      if (item.isDirectory()) visit(file);
      else if (item.isFile()) result[path.relative(root, file).replaceAll("\\", "/")] = createHash("sha256").update(fs.readFileSync(file)).digest("hex");
    }
  }
  visit(path.join(root, relative));
  return result;
}
async function main() {
  const sourcePaths = ["samples/legacy_shop", "tests/fixtures/universal_py3"];
  const before = Object.fromEntries(sourcePaths.map((p) => [p, hashes(p)]));
  save("original-sha256.json", before);
  const errors = [], blockedExternal = [], observedRequests = [], results = [];
  const browser = await chromium.launch({ headless: true, executablePath: process.env.PROOFPORT_CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe",
    args: ["--disable-background-networking", "--disable-component-update", "--no-first-run"] });
  const context = await browser.newContext({ acceptDownloads: false });
  const page = await context.newPage();
  page.on("pageerror", (err) => errors.push(String(err)));
  page.on("console", (message) => { if (message.type() === "error" && /\[proofport\]|uncaught|unhandled/i.test(message.text())) errors.push(message.text()); });
  page.on("request", (request) => { if (request.url().startsWith(base + "/api/")) observedRequests.push({ method: request.method(), url: request.url().slice(base.length) }); });
  await context.route("**/*", async (route) => {
    const url = route.request().url();
    if (url.startsWith(base + "/")) return route.continue();
    blockedExternal.push(url); return route.abort();
  });
  async function json(method, endpoint, body, headers) {
    const response = await page.request.fetch(base + endpoint, { method, ...(body ? { data: body } : {}), headers });
    return { status: response.status(), body: await response.json() };
  }
  async function state() { return page.evaluate(() => {
    const r = window.PP.store.state.run;
    return r && { id: r.id, lifecycle: r.control && r.control.lifecycle, backendFinalized: r.backendFinalized,
      reportStatus: r.reportStatus, chain: r.chain, state: r.state, parameters: r.control && r.control.parameters };
  }); }
  const selectors = {
    project: "#control-project_id", source: "#control-source_version", target: "#control-target_version",
    level: "#control-verification_level", cases: "#control-cases_profile_id", fixture: "#control-fixture_profile_id",
  };
  const visibleButton = (label) => page.getByRole("button", { name: label, exact: true });
  async function choice(label) { await page.locator("button.op-card").filter({ has: page.getByText(label, { exact: true }) }).click(); }
  async function select(name, value) { await page.locator(selectors[name]).selectOption(value); }
  async function checkReadiness() {
    await visibleButton("Check readiness").click();
    await page.waitForFunction(() => !!window.PP.control.state.preflight && !window.PP.control.state.checking);
    return page.evaluate(() => {
      const result = window.PP.control.state.preflight.result;
      return { can_start: result.can_start, parameters: result.parameters,
        errors: result.errors.map((e) => ({ code: e.code, message: e.message, field: e.field })) };
    });
  }
  async function verifyReport(name, id) {
    await page.waitForFunction(() => { const r = window.PP.store.state.run; return r && r.backendFinalized && r.reportStatus === "ready" && r.chain && r.chain.status === "ok"; }, null, { timeout: 180000 });
    const details = await json("GET", "/api/v1/runs/" + id);
    assert.equal(details.status, 200); assert.equal(details.body.finalized, true); assert.equal(details.body.lifecycle, "done", JSON.stringify(details.body.state.error));
    const legacy = await json("GET", "/api/runs/" + id);
    assert.deepEqual(legacy.body, details.body.state);
    const report = await json("GET", `/api/runs/${id}/report?format=json`);
    assert.equal(report.status, 200);
    const allEvents = await json("GET", `/api/runs/${id}/events?since=0`);
    const later = await json("GET", `/api/runs/${id}/events?since=2`);
    assert.ok(later.body.length); assert.ok(later.body.every((e) => e.seq > 2));
    assert.deepEqual(report.body.events, allEvents.body);
    assert.deepEqual(report.body.verification.control.parameters, details.body.parameters);
    assert.equal(report.body.simulation, false);
    assert.equal(details.body.execution.ai_generated, false); assert.equal(details.body.execution.live_enabled, false);
    assert.equal(report.body.verification.model_calls, 0); assert.equal(report.body.verification.ai_migration, false);
    assert.equal(details.body.state.hashes.unchanged, true); assert.equal(details.body.state.chain_intact, true);
    assert.equal(details.body.state.isolation, "docker");
    for (const metric of ["tokens_in", "tokens_out", "cost_usd"]) assert.equal(details.body.state.metrics[metric], 0);
    const html = await page.request.get(`${base}/api/runs/${id}/report?format=html`);
    assert.equal(html.status(), 200); assert.match(html.headers()["content-type"], /text\/html/);
    save(name + "-details.json", details.body); save(name + "-events.json", allEvents.body);
    save(name + "-report.json", report.body); save(name + "-report.html", await html.text());
    for (const p of sourcePaths) assert.deepEqual(hashes(p), before[p], "Original files changed: " + p);
    assert.equal(await page.locator('.mode-seg[data-mode="live"][data-active="true"]').count(), 0);
    assert.equal(errors.length, 0, errors.join("\n"));
    return { details: details.body, report: report.body, browser: await state() };
  }
  async function launch(name, extraChecks) {
    const ready = await checkReadiness(); assert.equal(ready.can_start, true, JSON.stringify(ready));
    save(name + "-preflight.json", ready);
    const body = await page.evaluate(() => window.PP.control.payload());
    const responseWait = page.waitForResponse((r) => r.url() === base + "/api/v1/runs" && r.request().method() === "POST");
    await visibleButton("Start run").click();
    const response = await responseWait; assert.equal(response.status(), 202, await response.text());
    const id = (await response.json()).run_id;
    const key = response.request().headers()["idempotency-key"]; assert.ok(key);
    if (extraChecks) await extraChecks({ id, key, body });
    const verified = await verifyReport(name, id);
    console.log(name + ": done, report ready, evidence verified, source hashes unchanged");
    return { id, ...verified };
  }
  try {
    const health = await json("GET", "/api/health"); assert.equal(health.status, 200); assert.equal(health.body.ok, true); save("health.json", health.body);
    const caps = await json("GET", "/api/v1/capabilities"); assert.equal(caps.status, 200); assert.equal(caps.body.docker.available, true); assert.equal(caps.body.live.enabled, false); save("capabilities.json", caps.body);
    for (const version of ["2.7", "3.12", "3.13"]) assert.ok(caps.body.runtimes.some((r) => r.version === version && r.available === true && r.verified === true));
    const projects = await json("GET", "/api/v1/projects"); assert.equal(projects.status, 200); save("projects.json", projects.body);
    const resolved = await json("POST", "/api/v1/projects/resolve", { root_id: "workspace", relative_path: "samples/legacy_shop" });
    assert.equal(resolved.status, 200); assert.equal(resolved.body.project_id, "legacy_shop"); save("resolved-project.json", resolved.body);
    const unsafe = await json("POST", "/api/v1/projects/resolve", { relative_path: "../outside" }); assert.equal(unsafe.status, 403); save("blocked-path.json", unsafe);
    await page.goto(base + "/#/migration");
    await page.waitForFunction(() => window.PP && window.PP.control && window.PP.control.state.mode === "v1");
    assert.equal(await page.locator(".op-card:enabled").count(), 4);
    await choice("Migration");
    await select("project", "universal_py3");
    assert.equal(await page.locator(selectors.fixture + " option:enabled").count(), 0);
    assert.equal(await page.locator(selectors.fixture).inputValue(), "");
    const missing = await checkReadiness(); assert.equal(missing.can_start, false); assert.equal(missing.errors[0].code, "profile_unavailable");
    assert.equal(await visibleButton("Start run").isDisabled(), true);
    save("ui-missing-profile.json", missing);

    await choice("Compatibility Check"); await select("project", "universal_py3"); await select("source", "3.12"); await select("target", "3.13"); await select("level", "tests");
    const allowedSources = await page.locator(selectors.source + " option:enabled").evaluateAll((options) => options.map((o) => o.value));
    assert.deepEqual(allowedSources, ["3.12", "3.13"]);
    await select("project", "legacy_shop");
    const blocked = await checkReadiness(); assert.equal(blocked.can_start, false); assert.ok(blocked.errors.length);
    assert.ok(["source_version_conflict", "tests_unavailable", "source_metadata_conflict"].includes(blocked.errors[0].code), JSON.stringify(blocked));
    assert.ok((await page.locator("main").innerText()).includes(blocked.errors[0].message));
    assert.equal(await visibleButton("Start run").isDisabled(), true); save("ui-blocked-preflight.json", blocked);

    await choice("Migration"); await select("project", "legacy_shop");
    assert.deepEqual(await page.locator(selectors.source + " option:enabled").evaluateAll((options) => options.map((o) => o.value)), ["2.7"]);
    assert.deepEqual(await page.locator(selectors.target + " option:enabled").evaluateAll((options) => options.map((o) => o.value)), ["3.12"]);
    const migration = await launch("migration", async ({ id, key, body }) => {
      const repeated = await json("POST", "/api/v1/runs", body, { "Idempotency-Key": key });
      assert.equal(repeated.status, 202); assert.equal(repeated.body.run_id, id);
      const busy = await json("POST", "/api/v1/runs", body, { "Idempotency-Key": randomUUID() });
      assert.equal(busy.status, 409); assert.equal(busy.body.error.code, "run_busy"); save("run-busy.json", busy);
      const busyPreflight = await json("POST", "/api/v1/runs/preflight", body);
      assert.equal(busyPreflight.status, 200); assert.equal(busyPreflight.body.can_start, false); assert.equal(busyPreflight.body.errors[0].code, "run_busy");
      await page.waitForFunction(() => window.PP.store.state.run?.control?.lifecycle === "finalizing", null, { timeout: 180000, polling: 25 });
      const interim = await json("GET", "/api/v1/runs/" + id);
      assert.equal(interim.body.lifecycle, "finalizing"); assert.equal(interim.body.finalized, false);
      assert.equal((await state()).reportStatus, "idle");
      assert.match(await page.locator("#run-pill").innerText(), /Finalizing/);
      const earlyReport = await json("GET", `/api/runs/${id}/report?format=json`); assert.equal(earlyReport.status, 409);
      save("finalizing.json", { details: interim.body, report: earlyReport, browser: await state() });
    });
    const mv = migration.report.verification;
    assert.equal(mv.comparisons.length, 90); assert.ok(mv.comparisons.every((c) => c.matches));
    assert.equal(mv.legacy_tests.tests_run, 10); assert.equal(mv.target_tests.tests_run, 10);
    results.push({ operation: "migration", id: migration.id, comparisons: 90, matched: 90, legacy_tests: 10, target_tests: 10, findings: migration.details.state.security.after, chain: migration.browser.chain.status });

    await choice("Security Audit"); await select("project", "legacy_shop"); await select("source", "2.7");
    assert.equal(await page.locator(selectors.target).isVisible(), false);
    const audit = await launch("audit");
    assert.equal(audit.report.verification.security_audit.project_executed, false);
    assert.equal(audit.report.verification.security_audit.fixes_applied, false);
    assert.ok(audit.details.state.security.before > 0);
    assert.equal(audit.details.state.metrics.tests_total, 0);
    results.push({ operation: "audit", id: audit.id, findings: audit.details.state.security.after,
      coverage: audit.report.verification.security_audit.coverage, scan_errors: audit.report.verification.security_audit.scan.errors.length, chain: audit.browser.chain.status });

    await choice("Compatibility Check"); await select("project", "universal_py3"); await select("source", "3.12"); await select("target", "3.13"); await select("level", "behavior");
    const compatibility = await launch("compatibility");
    const check = compatibility.report.verification.compatibility;
    assert.equal(check.level, "behavior_verified"); assert.equal(check.tests_passed, true); assert.equal(check.behavior_verified, true);
    assert.equal(check.existing_tests.tests_run, 2); assert.equal(check.comparisons.length, 2); assert.ok(check.comparisons.every((c) => c.matches));
    results.push({ operation: "compatibility", id: compatibility.id, level: check.level, existing_tests: 2, matched_cases: 2, chain: compatibility.browser.chain.status });

    for (const route of ["overview", "security", "compatibility", "evidence", "migration"]) {
      await page.goto(base + "/#/" + route);
      await page.waitForFunction(() => {
        const run = window.PP?.store?.state?.run;
        return run?.reportStatus === "ready" && run.chain?.status === "ok";
      });
      assert.ok((await page.locator(`.view[data-view="${route}"]`).innerText()).trim());
    }
    assert.equal(errors.length, 0, errors.join("\n")); assert.deepEqual(blockedExternal, []);
    const summary = { passed: true, base, browser: "installed Chrome, headless, no screenshots/video/trace", finalization_delay_seconds: 2,
      scenarios: results, checks: ["health", "capabilities", "projects", "resolve", "path rejection", "missing profiles", "blocked preflight", "version matrix", "HTTP 202", "idempotency", "run_busy", "finalizing", "early report 409", "legacy state/events/reports", "browser evidence integrity", "all views", "unchanged originals", "zero model usage"],
      javascript_errors: errors, blocked_external_requests: blockedExternal, observed_api_requests: observedRequests.length, artifacts };
    save("summary.json", summary); console.log(JSON.stringify(summary, null, 2));
  } catch (error) {
    save("failure.json", { message: error.message, stack: error.stack, errors, blockedExternal, results, observedRequests });
    throw error;
  } finally { await context.close(); await browser.close(); }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
