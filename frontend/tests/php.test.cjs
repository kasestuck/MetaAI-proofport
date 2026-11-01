const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const { harness, response, deferred, until, flush, defaultReply } = require("./harness.cjs");
const F = require("./contract-fixtures.cjs"), P = require("./php-fixtures.cjs");
const plain = (v) => JSON.parse(JSON.stringify(v));

function setup(t, { caps = P.capabilities(), projects = P.projects(), handler, storage } = {}) {
  const h = harness((call) => {
    const answer = handler && handler(call);
    if (answer !== undefined) return answer;
    if (call.url === "/api/v1/capabilities") return response(caps);
    if (call.url === "/api/v1/projects") return response(projects);
    return defaultReply(call);
  }, storage);
  t.after(h.cleanup); return h;
}
async function php(h) { await h.PP.control.refresh(); assert.equal(h.PP.control.state.mode, "v1"); h.PP.control.edit({ language: "php" }); }
function view(h, route) {
  h.load("js/views/shared.js"); h.load("js/views/" + route + ".js");
  h.PP.app = { refresh() {} };
  const el = h.document.createElement("div"); h.document.appendChild(el);
  h.PP.views[route].mount(el); h.PP.views[route].update(h.PP.store.state); return el;
}
async function replay(h, report, name) {
  assert.equal(await h.PP.store.loadReplay({ name, size: 1000, text: async () => JSON.stringify(report) }), true);
}

test("PHP selectors use per-language policy, projects and server profiles; Python stays unchanged", async (t) => {
  const h = setup(t); await h.PP.control.refresh();
  const python = plain(h.PP.control.payload());
  await php(h); const C = h.PP.control;
  assert.deepEqual(plain(C.projectChoices()).map((p) => p.project_id), ["php_shop"]);
  assert.deepEqual(plain(C.pairs("migration")), [["7.4", "8.3"]]);
  assert.deepEqual(plain(C.choices()).map((c) => c.operation), ["migration", "audit", "compatibility"]);
  assert.equal(C.choices().some((c) => c.mode === "simulation" || c.mode === "live"), false);
  assert.deepEqual(plain(C.payload()), { operation: "migration", project_id: "php_shop", execution_mode: "offline_fixtures", language: "php",
    source_version: "7.4", target_version: "8.3", max_iterations: 5, fixture_profile_id: "php_shop_74_83", cases_profile_id: "php_shop_golden" });
  C.edit({ security_fix_profile_id: "php_shop_security" }); assert.equal(C.payload().security_fix_profile_id, "php_shop_security");
  C.edit({ language: "python" }); assert.deepEqual(plain(C.payload()), python);
});

for (const missing of ["entry", "receipt", "unverified_image"]) test("PHP unavailable: " + missing + " has a reason and never falls back to Python", async (t) => {
  const caps = P.capabilities();
  if (missing === "entry") delete caps.languages.php;
  else if (missing === "receipt") Object.assign(caps.languages.php, { verified: false, supported_operations: [], readiness: { can_start: false, reason: "php_e2e_verification_required" } });
  else caps.languages.php.runtimes[0].verified = false;
  const h = setup(t, { caps }); await php(h); const C = h.PP.control;
  if (missing !== "unverified_image") assert.ok(C.languageReason());
  else assert.ok(C.choices().find((c) => c.operation === "migration").reason);
  assert.deepEqual(plain(C.pairs("migration")), missing === "entry" ? [] : missing === "receipt" ? [["7.4", "8.3"]] : []);
  await C.preflight(); assert.equal(C.canStart(), false);
  assert.equal(C.state.draft.language, "php"); assert.equal(h.calls.some((c) => c.url === "/api/runs" && c.method === "POST"), false);
});

test("PHP image presence and policy lists cannot replace supported_operations", async (t) => {
  const caps = P.capabilities(); caps.languages.php.supported_operations = ["audit"];
  const h = setup(t, { caps }); await php(h);
  assert.deepEqual(plain(h.PP.control.choices()).map((c) => c.operation), ["audit"]);
  assert.equal(h.PP.control.payload().operation, "audit");
});

test("PHP static audit works without Docker/Bandit and sends only the source label", async (t) => {
  const caps = P.capabilities(); caps.docker.available = false; caps.scanner.available = false;
  caps.languages.php.supported_operations = ["audit"];
  caps.languages.php.runtimes.forEach((r) => { r.available = false; r.verified = false; });
  const h = setup(t, { caps }); await php(h); const C = h.PP.control;
  assert.deepEqual(plain(C.sources("audit")), ["7.4", "8.3"]);
  assert.deepEqual(plain(C.payload()), { language: "php", operation: "audit", project_id: "php_shop", execution_mode: "offline", source_version: "7.4" });
  await C.preflight(); assert.equal(C.canStart(), true);
  const el = h.document.createElement("div"), form = h.PP.controlForm.mount(el); form.update(h.PP.store.state);
  assert.match(el.textContent, /operator label/); assert.match(el.textContent, /no project execution, Docker or AI required/);
  assert.doesNotMatch(el.textContent, /Bandit warnings/);
});

test("PHP compatibility levels, pairs and optional profiles are operation-specific", async (t) => {
  const caps = P.capabilities(); caps.languages.php.operations.compatibility.verification_levels = ["syntax", "behavior"];
  caps.languages.php.runtimes.push({ version: "8.4", configured: true, available: true, verified: true, source: true, target: true });
  const h = setup(t, { caps }); await php(h); const C = h.PP.control;
  C.edit({ choice: "compatibility:offline" });
  assert.deepEqual(plain(C.levels()), ["syntax", "behavior"]);
  assert.deepEqual(plain(C.pairs("compatibility")), [["7.4", "8.3"]]);
  assert.equal(C.payload().verification_level, "syntax"); assert.equal("fixture_profile_id" in C.payload(), false);
  C.edit({ verification_level: "behavior" }); assert.equal(C.payload().cases_profile_id, "php_shop_golden");
});

test("missing PHP profiles block before POST; security fixture is explicit and bound", async (t) => {
  const projects = P.projects(); projects.cases_profiles = projects.cases_profiles.filter((p) => p.project_id !== "php_shop");
  const h = setup(t, { projects }); await php(h); const C = h.PP.control;
  await C.preflight(); assert.equal(C.state.preflight.result.errors[0].code, "profile_unavailable");
  assert.equal(h.calls.some((c) => c.url.endsWith("/preflight")), false);
  assert.equal(C.state.draft.security_fix_profile_id, "");
});

test("cross-language project and profile injection cannot enter a PHP request", async (t) => {
  const h = setup(t); await php(h); const C = h.PP.control;
  C.state.draft.project_id = "legacy_shop";
  assert.throws(() => C.payload(), /registered project for this language/);
  C.edit({ project_id: "php_shop" }); C.state.draft.security_fix_profile_id = "legacy_shop_py27_py312";
  assert.throws(() => C.payload(), /project-bound security_fix/);
});

test("blocked PHP preflight and late language changes never enable Start", async (t) => {
  const late = deferred(); const h = setup(t, { handler: (c) => c.url.endsWith("/preflight") ? late.promise : undefined });
  await php(h); const C = h.PP.control; const checking = C.preflight(); await flush();
  C.edit({ language: "python" }); late.resolve(response({ can_start: true, errors: [], parameters: P.parameters() })); await checking;
  assert.equal(C.canStart(), false); assert.equal(C.state.preflight, null);
});

test("PHP HTTP 200 blocked preflight shows actual backend reason", async (t) => {
  const h = setup(t, { handler: (c) => c.url.endsWith("/preflight") ? response({ can_start: false, parameters: P.parameters(), errors: [{ code: "php_e2e_verification_required", message: "Current PHP proof unavailable", field: null }] }) : undefined });
  await php(h); await h.PP.control.preflight();
  const el = h.document.createElement("div"), form = h.PP.controlForm.mount(el); form.update(h.PP.store.state);
  assert.match(el.textContent, /Current PHP proof unavailable/); assert.equal(h.PP.control.canStart(), false);
});

test("mounted language control resets preflight and updates PHP versions/projects", async (t) => {
  const h = setup(t); await h.PP.control.refresh(); await h.PP.control.preflight();
  const el = h.document.createElement("div"), form = h.PP.controlForm.mount(el); form.update(h.PP.store.state);
  const language = el.querySelector("#control-language"); language.value = "php"; language.dispatch("change"); form.update(h.PP.store.state);
  assert.equal(h.PP.control.canStart(), false);
  assert.deepEqual(el.querySelector("#control-project_id").children.map((p) => p.value), ["php_shop"]);
  assert.match(el.textContent, /Source PHP/); assert.match(el.textContent, /PHP 7.4/); assert.doesNotMatch(el.querySelector("#control-target_version").textContent, /Python/);
  assert.equal(el.querySelector("#control-security_fix_profile_id").value, "");
});

test("resolve refreshes server profiles and selects the returned language", async (t) => {
  const h = setup(t, { handler: (c) => c.url.endsWith("/resolve") ? response({ project_id: "php_shop", relative_path: "tests/fixtures/php_shop", kind: "directory", language: "php" }) : undefined });
  await h.PP.control.refresh(); await h.PP.control.resolve("tests/fixtures/php_shop");
  assert.equal(h.PP.control.payload().language, "php"); assert.equal(h.PP.control.payload().cases_profile_id, "php_shop_golden");
});

for (const operation of ["migration", "audit", "compatibility"]) test("PHP " + operation + " polls v1 and legacy events/report with honest labels", async (t) => {
  const report = P.report(operation);
  const h = setup(t, { handler: (c) => c.url === "/api/v1/runs/run-one" ? response(P.details(operation, "done", report))
    : c.url.endsWith("/report?format=json") ? response(report) : undefined });
  await php(h); const C = h.PP.control;
  if (operation !== "migration") C.edit({ choice: operation + ":offline" });
  await C.preflight(); await C.submit(false);
  await until(() => h.PP.store.state.run.reportStatus === "ready");
  const sent = h.calls.find((c) => c.url === "/api/v1/runs" && c.method === "POST");
  assert.equal(sent.payload.language, "php"); assert.equal(sent.payload.operation, operation); assert.ok(sent.headers["Idempotency-Key"]);
  const run = h.PP.store.state.run; assert.equal(run.language, "php");
  assert.doesNotMatch(h.PP.labels.provenance(run).label, /Live/);
  if (operation === "migration") assert.match(h.PP.labels.provenance(run).label, /fixtures.*not AI/);
  for (const route of ["migration", "security", "compatibility", "evidence", "overview"]) {
    const el = view(h, route); assert.ok(el.textContent.length);
    if (route === "compatibility") { assert.match(el.textContent, /PHP checks/); assert.match(el.textContent, /Syntax verified/); assert.doesNotMatch(el.textContent, /Python 8.3/); }
    if (route === "migration" && operation === "migration") assert.match(el.textContent, /Fixture migration/);
    if (route === "migration" && operation === "audit") { assert.doesNotMatch(el.textContent, /Fixture migration/); assert.match(el.textContent, /Audited/); }
  }
});

test("PHP findings use actual arrays and CWE; never fabricate absent categories or Bandit provenance", async (t) => {
  const h = setup(t); const report = P.report("audit"); await replay(h,report,"php-audit.json");
  let el = view(h,"security");
  for (const name of ["SQL Injection","XSS","Command Injection","Unsafe Deserialization","Path Traversal","Hardcoded Secrets","Weak Password Hashing","Unsafe File Upload"]) assert.ok(el.textContent.includes(name),name);
  assert.match(el.textContent,/8 warnings/); assert.match(el.textContent,/CWE-89/); assert.doesNotMatch(el.textContent,/Bandit 1.8.6|Bandit confidence/);
  report.state.security.findings=report.state.security.findings.slice(0,1); report.verification.security_audit.findings=report.verification.security_audit.findings.slice(0,1);
  await replay(h,report,"php-one.json"); el=view(h,"security");
  assert.match(el.textContent,/SQL Injection/); assert.doesNotMatch(el.textContent,/Unsafe File Upload|Weak Password Hashing/);
});

test("PHP security fix decisions retain review, rollback, rescan and original integrity", async (t) => {
  const h = setup(t), report=P.report();
  const finding=report.verification.security_before.findings[0]; finding.status="needs_review"; report.state.security.findings[0].status="needs_review";
  report.verification.security_fix={ mode:"fixture",not_ai:true,verified:true,source_unchanged:true,evidence_chain_intact:true,
    findings_before:[finding],findings_after:[finding],decisions:[finding],fixed:[],needs_review:[finding.id],rejected:[finding.id],
    attempts:[{finding_id:finding.id,mode:"fixture",status:"needs_review",applied:false,rolled_back:true,originals_unchanged:true,
      explanation:"Behavior changes",reasons:["Recorded behavior differs"],checks:{syntax:{ran:true,passed:true},golden:{ran:true,passed:false},existing_tests:{ran:true,passed:false}},
      security_rescan:{ran:true,target_removed:true,no_new_findings:true}}] };
  await replay(h,report,"php-fix.json"); const el=view(h,"security");
  assert.match(el.textContent,/Needs review/); assert.match(el.textContent,/Rejected attempts/); assert.match(el.textContent,/Rolled back/);
  assert.match(el.textContent,/Originals unchanged: Confirmed/); assert.match(el.textContent,/Accepted copy verified/);
  assert.match(el.textContent,/PHP rescan/); assert.doesNotMatch(el.textContent,/Status: unknown|Bandit rescan/);
});

test("PHP compatibility false and null flags remain failed and not verified", async (t) => {
  const h=setup(t), report=P.report("compatibility");
  report.verification.compatibility={level:"not_verified",syntax_passed:false,tests_passed:null,behavior_verified:null};
  report.state.status="failed"; report.state.error={code:"php_verification_failed",message:"Target syntax failed"};
  await replay(h,report,"php-failed.json"); const el=view(h,"compatibility");
  assert.match(el.textContent,/Run failed — no compatibility verdict/); assert.match(el.textContent,/Not verified/); assert.match(el.textContent,/Failed/);
});

test("saved PHP replay verifies evidence without API calls and keeps fixture provenance", async (t) => {
  const h=setup(t); const event={seq:1,ts:"2026-11-01T00:00:00Z",type:"security_scan",module:null,detail:"Contract evidence fixture",prev_hash:"0".repeat(64)};
  event.entry_hash=createHash("sha256").update(event.prev_hash+h.PP.integrity.canonical(event)).digest("hex");
  await replay(h,P.report("migration",[event]),"php-evidence.json");
  await until(()=>h.PP.store.state.run.chain && h.PP.store.state.run.chain.status==="ok");
  assert.match(h.PP.labels.provenance(h.PP.store.state.run).label,/Saved report.*PHP offline fixtures/);
  assert.match(view(h,"evidence").textContent,/security_scan/); assert.equal(h.calls.length,0);
});

test("uncertain PHP retry keeps the exact language, security profile, payload and key after Python edits", async (t) => {
  let count=0;
  const h=setup(t,{handler:(c)=>{
    if(c.url==="/api/v1/runs" && c.method==="POST" && ++count===1) throw new Error("Unknown network outcome");
    if(c.url==="/api/v1/runs/run-one") return response(P.details("migration","running"));
  }});
  await php(h); const C=h.PP.control;
  C.edit({security_fix_profile_id:"php_shop_security"}); await C.preflight(); await C.submit(false);
  assert.ok(C.state.pending); const body=plain(C.state.pending.body),key=C.state.pending.key;
  C.edit({language:"python"});
  const el=h.document.createElement("div"),form=h.PP.controlForm.mount(el);form.update(h.PP.store.state);
  assert.match(el.textContent,/Original submission: PHP/);
  await C.submit(true);
  const requests=h.calls.filter((c)=>c.url==="/api/v1/runs" && c.method==="POST");
  assert.equal(requests.length,2);
  assert.deepEqual(requests.map((r)=>r.payload),[body,body]);
  assert.ok(requests.every((r)=>r.headers["Idempotency-Key"]===key));
  assert.equal(body.language,"php"); assert.equal(body.security_fix_profile_id,"php_shop_security");
});

test("pending PHP submission survives reload without automatic POST or language substitution", async (t) => {
  const saved={key:"php-pending-intent",instanceId:"instance-one",body:P.parameters()};
  const h=setup(t,{storage:{"proofport.console.lastRun.pending":JSON.stringify(saved)}});
  await h.PP.control.init();
  assert.deepEqual(plain(h.PP.control.state.pending.body),saved.body);
  assert.equal(h.calls.some((c)=>c.method==="POST"),false);
});

test("PHP finalizing remains active until final report and evidence are available", async (t) => {
  let finished=false; const report=P.report();
  const h=setup(t,{handler:(c)=>c.url==="/api/v1/runs/run-one" ? response(P.details("migration",finished?"done":"finalizing",report))
    :c.url.endsWith("/report?format=json")?response(report):undefined});
  await php(h); await h.PP.control.preflight(); await h.PP.control.submit(false);
  await until(()=>h.PP.store.state.run.control?.lifecycle==="finalizing");
  assert.equal(h.PP.store.state.run.reportStatus,"idle"); assert.equal(h.PP.store.state.run.backendFinalized,false);
  finished=true; await h.tick(); await until(()=>h.PP.store.state.run.reportStatus==="ready");
  assert.match(h.PP.labels.provenance(h.PP.store.state.run).label,/PHP offline fixtures/);
});

test("invalid PHP discovery is an error, not a legacy or Python fallback", async (t) => {
  const caps=P.capabilities(); caps.languages.php.operations.migration.pairs=[["7.4"]];
  const h=setup(t,{caps}); await h.PP.control.refresh();
  assert.equal(h.PP.control.state.mode,"error");
  assert.equal(h.PP.control.state.error.code,"unexpected_response");
  assert.equal(h.calls.some((c)=>c.url==="/api/runs"),false);
});

test("saved PHP reports without control parameters retain explicit PHP offline provenance", async (t) => {
  const h=setup(t),report=P.report(); delete report.verification.control;
  await replay(h,report,"earlier-php.json");
  assert.equal(h.PP.labels.language(h.PP.store.state.run),"php");
  assert.match(h.PP.labels.provenance(h.PP.store.state.run).label,/PHP offline fixtures.*not AI/);
  assert.equal(h.calls.length,0);
});

test("PHP mismatch view shows the supplied hashes and reason, not nonexistent raw values", async (t) => {
  const h=setup(t),report=P.report();
  report.verification.comparisons=[{id:"changed",module:"src/security.php",matches:false,expected_sha256:"a".repeat(64),observed_sha256:"b".repeat(64),reason:"Typed results differ",allowed_differences:[]}];
  report.state.status="failed"; report.state.error={code:"php_verification_failed",message:"Candidate rejected"};
  await replay(h,report,"php-mismatch.json"); const el=view(h,"migration");
  assert.match(el.textContent,/Typed results differ/); assert.match(el.textContent,/Source outcome SHA-256/);
  assert.ok(el.textContent.includes("a".repeat(64))); assert.ok(el.textContent.includes("b".repeat(64)));
});
