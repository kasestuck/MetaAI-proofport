/* Opt-in, bounded real browser/API smoke. No screenshots, video, trace,
 * downloads, provider calls or backend/source edits. Uses installed Chrome.
 * One PHP fixture migration, static audit, syntax check and Python simulation.
 */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const { createHash } = require("node:crypto");
const fs = require("node:fs"), path = require("node:path");
const base = process.env.PROOFPORT_INTEGRATION_URL;
if (process.env.PROOFPORT_FRONTEND_PHP_SMOKE !== "1" || !/^http:\/\/127\.0\.0\.1:(8001|8765)$/.test(base || "")) {
  throw new Error("Explicit PROOFPORT_FRONTEND_PHP_SMOKE=1 and loopback PROOFPORT_INTEGRATION_URL required");
}
const root = path.resolve(__dirname, "../..");
function hashes(relative) {
  const result = {};
  function visit(folder) {
    for (const item of fs.readdirSync(folder, { withFileTypes: true })) {
      assert.equal(item.isSymbolicLink(), false);
      const name = path.join(folder, item.name);
      if (item.isDirectory()) visit(name);
      else if (item.isFile()) result[path.relative(root, name)] = createHash("sha256").update(fs.readFileSync(name)).digest("hex");
    }
  }
  visit(path.join(root, relative)); return result;
}
async function main() {
  const sources = ["tests/fixtures/php_shop", "samples/legacy_shop"];
  const before = sources.map(hashes), errors = [], external = [], results = [];
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.PROOFPORT_CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe",
    args: ["--disable-background-networking", "--disable-component-update", "--no-first-run"] });
  const context = await browser.newContext({ acceptDownloads: false, viewport: { width: 1440, height: 1000 } });
  await context.route("**/*", async (route) => {
    if (!route.request().url().startsWith(base + "/")) { external.push(route.request().url()); return route.abort(); }
    if (route.request().method() === "POST" && route.request().url().endsWith("/api/v1/runs")) {
      assert.notEqual(route.request().postDataJSON().execution_mode, "live");
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && m.text().includes("[proofport]")) errors.push(m.text()); });
  const button = (name) => page.getByRole("button", { name, exact: true }).filter({ visible: true });
  const select = (name, value) => page.locator("#control-" + name).selectOption(value);
  const operation = (name) => page.locator("button.op-card:visible").filter({ hasText: new RegExp("^" + name) }).click();
  async function route(name) { await page.goto(base + "/#/" + name); await page.waitForFunction(() => window.PP?.control?.state.mode === "v1"); }
  async function preflight() {
    const response = page.waitForResponse((r) => r.url() === base + "/api/v1/runs/preflight");
    await button("Check readiness").click(); return (await response).json();
  }
  async function complete(id, status = "done") {
    await page.waitForFunction((id) => {
      const r = window.PP.store.state.run;
      return r?.id === id && r.backendFinalized && r.reportStatus === "ready" && r.chain?.status === "ok";
    }, id, { timeout: 120000 });
    const data = await page.evaluate(() => ({ details: window.PP.store.state.run.control, report: window.PP.store.state.run.report,
      provenance: window.PP.labels.provenance(window.PP.store.state.run) }));
    assert.equal(data.details.lifecycle, status); assert.equal(data.details.state.status, status);
    assert.equal(data.report.state.hashes.unchanged, true); assert.equal(data.report.state.chain_intact, true);
    assert.equal(data.details.execution.live_enabled, false); assert.equal(data.details.execution.ai_generated, false);
    assert.doesNotMatch(data.provenance.label, /Live Meta/);
    assert.equal(await page.locator('.mode-seg[data-mode="live"][data-active="true"]').count(), 0);
    return data;
  }
  async function launch(name, status, whileRunning) {
    const readiness = await preflight(); assert.equal(readiness.can_start, true, JSON.stringify(readiness));
    const response = page.waitForResponse((r) => r.url() === base + "/api/v1/runs" && r.request().method() === "POST");
    await button("Start run").click(); const accepted = await response;
    assert.equal(accepted.status(), 202, await accepted.text()); assert.ok(accepted.request().headers()["idempotency-key"]);
    const id = (await accepted.json()).run_id;
    if (whileRunning) await whileRunning();
    const outcome = await complete(id, status);
    console.log(name + ": " + status + ", report ready, browser evidence chain verified");
    return { id, ...outcome };
  }
  try {
    const caps = await (await page.request.get(base + "/api/v1/capabilities")).json();
    assert.equal(caps.live.enabled, false);
    assert.ok(caps.languages.php.supported_operations.includes("migration"), "Current PHP proof/runtimes required; never synthesize readiness");
    const catalog = await (await page.request.get(base + "/api/v1/projects")).json();
    const project = catalog.projects.find((p) => p.language === "php" && p.available && p.available_profiles.fixture.length && p.available_profiles.cases.length);
    assert.ok(project, "A real project-bound PHP fixture profile is required");
    await route("migration");
    assert.equal(await page.locator("#control-language").inputValue(), "python");
    const pythonPreflight = await preflight(); assert.equal(pythonPreflight.can_start, true);
    assert.deepEqual(pythonPreflight.parameters.source_version, "2.7");
    await select("language", "php"); await operation("Migration"); await select("project_id", project.project_id);
    assert.equal(await page.locator("#control-source_version").inputValue(), "7.4");
    assert.deepEqual(await page.locator("#control-target_version option:enabled").evaluateAll((os) => os.map((o) => o.value)), ["8.3"]);
    assert.equal(await page.locator("#control-security_fix_profile_id").inputValue(), "");
    assert.ok(project.available_profiles.security_fix.length);
    await select("security_fix_profile_id", project.available_profiles.security_fix[0]);
    await page.locator("#control-max_iterations").fill("1");
    const migration = await launch("PHP fixture migration", "done", async () => {
      const blocked = await preflight(); assert.equal(blocked.can_start, false); assert.equal(blocked.errors[0].code, "run_busy");
      assert.match(await page.locator(".view[data-view='migration']").innerText(), /run_busy/);
    });
    const v = migration.report.verification;
    assert.equal(v.golden_case_count, 22); assert.ok(v.comparisons.every((c) => c.matches));
    assert.equal(v.source_tests.tests_run, 9); assert.equal(v.target_tests.tests_run, 9);
    assert.equal(v.model_calls, 0); assert.equal(v.ai_migration, false);
    assert.equal(v.security_fix.fixed.length, 1); assert.equal(v.security_fix.needs_review.length, 1); assert.equal(v.security_fix.rejected.length, 2);
    assert.match(await page.locator(".view[data-view='migration']").innerText(), /Fixture migration/);
    await route("security");
    let text = await page.locator(".view[data-view='security']").innerText();
    for (const category of ["SQL Injection", "XSS", "Command Injection", "Unsafe Deserialization", "Path Traversal", "Hardcoded Secrets", "Weak Password Hashing", "Unsafe File Upload"]) assert.ok(text.includes(category), category);
    assert.match(text, /Needs review/); assert.match(text, /Rolled back/); assert.doesNotMatch(text, /Bandit 1.8.6|Bandit confidence|Status: unknown/);
    await route("compatibility"); text = await page.locator(".view[data-view='compatibility']").innerText();
    assert.match(text, /PHP checks/); assert.match(text, /PHP 8.3.36/); assert.doesNotMatch(text, /Python runtime registry/);
    await route("evidence");
    assert.match(await page.locator(".view[data-view='evidence']").innerText(), /security_scan/);
    assert.equal((await page.request.get(`${base}/api/runs/${migration.id}/report?format=html`)).status(), 200);
    results.push({ operation: "php_migration", golden: 22, target_tests: 9, fixed: 1, needs_review: 1, rejected: 2 });

    await route("migration"); await operation("Security Audit");
    assert.equal(await page.locator("#control-target_version").isVisible(), false);
    assert.equal(await page.locator("#control-security_fix_profile_id").isVisible(), false);
    const audit = await launch("PHP static audit", "done");
    assert.equal(audit.report.verification.project_executed, false); assert.equal(audit.report.state.isolation, "reduced");
    assert.equal(audit.report.state.security.after, 10); assert.equal(audit.details.result.compatibility.level, "not_verified");
    await route("security"); text = await page.locator(".view[data-view='security']").innerText();
    assert.match(text, /10 warnings/); assert.match(text, /Limited PHP/); assert.match(text, /CWE-89/);
    results.push({ operation: "php_audit", potential_findings: 10, project_executed: false });

    await route("migration"); await operation("Compatibility Check"); await select("verification_level", "syntax");
    const compatibility = await launch("PHP unchanged legacy compatibility", "failed");
    assert.equal(compatibility.details.result.compatibility.syntax_passed, false);
    assert.equal(compatibility.details.result.compatibility.tests_passed, null);
    await route("compatibility"); text = await page.locator(".view[data-view='compatibility']").innerText();
    assert.match(text, /Run failed — no compatibility verdict/); assert.match(text, /Not verified/);
    assert.equal(await page.locator(".view[data-view='compatibility'] .check--ok").count(), 0);
    results.push({ operation: "php_compatibility", expected: "failed", syntax_passed: false, tests_passed: null });

    await route("migration"); await select("language", "python"); await operation("Simulation");
    await select("project_id", "legacy_shop");
    const simulation = await launch("Python regression simulation", "done");
    assert.equal(simulation.details.execution.effective, "simulation"); assert.equal(simulation.report.simulation, true);
    results.push({ operation: "python_simulation", simulated: true, real_migration_claimed: false });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.locator("#control-language").isVisible(), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, "Unexpected page overflow at mobile width");
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    sources.forEach((source, i) => assert.deepEqual(hashes(source), before[i], "Original source changed"));
    console.log(JSON.stringify({ passed: true, base, scenarios: results, javascript_errors: errors, external_requests: external,
      screenshots: false, source_hashes_unchanged: true, mobile_width: 390 }, null, 2));
  } finally { await context.close(); await browser.close(); }
}
main().catch((e) => { console.error(e); process.exitCode = 1; });
