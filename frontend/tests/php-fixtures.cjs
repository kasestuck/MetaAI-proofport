// Frontend contract fixtures only. These are not Docker/model execution evidence.
const F = require("./contract-fixtures.cjs");
const rules = ["PHP-SQL", "PHP-XSS", "PHP-CMD", "PHP-DESERIALIZE", "PHP-PATH", "PHP-SECRET", "PHP-HASH", "PHP-UPLOAD"];
function capabilities() {
  const caps = F.copy(F.capabilities);
  caps.languages = { php: { language: "php", configured: true, available: true, verified: true,
    supported_operations: ["migration", "audit", "compatibility"],
    readiness: { can_start: true, requires_preflight: true, reason: "preflight_required" },
    runtimes: ["7.4", "8.3"].map((version) => ({ version, configured: true, available: true, verified: true, source: true, target: version === "8.3", image: "php:" + version })),
    source_versions: ["7.4", "8.3"], target_versions: ["8.3"],
    operations: { migration: { pairs: [["7.4", "8.3"]], execution_modes: ["offline_fixtures"] },
      audit: { source_versions: ["7.4", "8.3"], execution_modes: ["offline"], static_only: true },
      compatibility: { pairs: [["7.4", "8.3"]], execution_modes: ["offline"], verification_levels: ["syntax", "tests", "behavior"] } } } };
  return caps;
}
function projects() {
  const data = F.copy(F.projects);
  data.projects.forEach((p) => { p.language = "python"; });
  data.projects.push({ project_id: "php_shop", relative_path: "tests/fixtures/php_shop", available: true, language: "php",
    available_profiles: { cases: ["php_shop_golden"], fixture: ["php_shop_74_83"], security_fix: ["php_shop_security"] } });
  data.cases_profiles.push({ id: "php_shop_golden", project_id: "php_shop", available: true });
  data.fixture_profiles.push({ id: "php_shop_74_83", project_id: "php_shop", available: true });
  data.security_fix_profiles = [{ id: "php_shop_security", project_id: "php_shop", available: true, mode: "fixture" }];
  return data;
}
function parameters(operation = "migration") {
  return { language: "php", operation, project_id: "php_shop", source_version: "7.4", target_version: operation === "audit" ? null : "8.3",
    execution_mode: operation === "migration" ? "offline_fixtures" : "offline", max_iterations: 5,
    verification_level: operation === "audit" ? null : "behavior", fixture_profile_id: operation === "migration" ? "php_shop_74_83" : null,
    cases_profile_id: operation === "audit" ? null : "php_shop_golden", security_fix_profile_id: null };
}
function findings() {
  return rules.map((scanner_test, i) => ({ id: scanner_test + "-contract", file: "src/security.php", line: i + 1,
    severity: "MEDIUM", confidence: "LOW", status: "open", scanner_test, scanner: "proofport-php-lexical-v1",
    description: "Potential contract fixture warning", proposed_fix: "Review the application context",
    cwe: { id: [89, 79, 78, 502, 22, 798, 328, 434][i] }, verification_status: "potential_risk_not_confirmed" }));
}
function tests(php) { return { php, tests_run: 1, passed: true, outcomes: [{ id: "contract-check", status: "passed" }], runner: "proofport" }; }
function report(operation = "migration", events = []) {
  const p = parameters(operation), audit = operation === "audit", found = findings();
  const state = F.state(); state.isolation = audit ? "reduced" : "docker";
  state.modules = [{ name: "src.security", status: "green", tests_passed: audit ? 0 : 1, tests_total: audit ? 0 : 1, iterations: 0 }];
  state.security = { before: found.length, after: found.length, findings: found.map((f) => ({ id: f.id, file: f.file, line: f.line, severity: f.severity, status: f.status, note: f.description })) };
  const scan = { scanner: "proofport-php-lexical-v1", findings: found, confirmed_findings: [], errors: [], coverage: "limited_lexical", project_executed: false, fixes_applied: false, limitations: ["Limited lexical rules; not complete data-flow analysis."] };
  const compatibility = { level: audit ? "not_verified" : "behavior_verified", syntax_passed: audit ? null : true, tests_passed: audit ? null : true, behavior_verified: audit ? null : true };
  return { ...F.report(events), state, settings: { pipeline: p.execution_mode, model: null, max_iterations: 5 },
    verification: { language: "php", mode: "php_" + operation, execution_mode: p.execution_mode,
      control: { parameters: p, live_enabled: false }, compatibility, source_version: p.source_version, target_version: p.target_version,
      security_audit: audit ? scan : null, security_before: operation === "migration" ? scan : null,
      security_after: operation === "migration" ? scan : null, source_tests: audit ? null : tests("7.4.33"), target_tests: audit ? null : tests("8.3.36"),
      comparisons: audit ? [] : [{ id: "one", module: "src/security.php", matches: true, allowed_differences: [] }],
      golden_case_count: audit ? undefined : 1, syntax_passed: compatibility.syntax_passed, tests_passed: compatibility.tests_passed,
      behavior_verified: compatibility.behavior_verified, model_calls: 0, ai_migration: false, project_executed: !audit,
      migration_performed: operation === "migration", limitations: ["Offline fixture; finite recorded inputs, not AI migration."] } };
}
function details(operation = "migration", lifecycle = "done", exported = report(operation)) {
  const v = exported.verification;
  return F.details(lifecycle, { parameters: v.control.parameters, state: { ...exported.state, status: lifecycle === "finalizing" ? "running" : lifecycle },
    execution: { effective: v.execution_mode, simulated: false, ai_generated: false, live_enabled: false },
    result: { compatibility: v.compatibility, security_audit: v.security_audit, security_fix: v.security_fix || null, target_tests: v.target_tests, limitations: v.limitations } });
}
module.exports = { capabilities, projects, parameters, findings, report, details };
