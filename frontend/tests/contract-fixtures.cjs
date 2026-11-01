// Browser contract fixtures, not backend/Docker execution evidence.
const copy = (value) => JSON.parse(JSON.stringify(value));
const capabilities = {
  api_version: "1", instance_id: "instance-one", checked_at: "2026-11-01T00:00:00Z", cache_ttl_seconds: 5,
  docker: { available: true }, scanner: { available: true, image: "proofport-bandit:1.8.6", image_id: "sha256:fixture" },
  runtimes: ["2.7", "3.8", "3.10", "3.12", "3.13", "3.14"].map((version) => ({
    version, image: "python:" + version, configured: true, available: true,
    verified: ["2.7", "3.12", "3.13"].includes(version), source: true, target: version !== "2.7",
    python: version.split(".").map(Number).concat(version === "2.7" ? 18 : 16),
  })),
  operations: {
    migration: { pairs: [["2.7", "3.12"]], execution_modes: ["offline_fixtures", "simulation"] },
    audit: { source_versions: ["2.7", "3.12", "3.13"], execution_modes: ["offline"] },
    compatibility: { pairs: [["3.12", "3.12"], ["3.12", "3.13"], ["3.13", "3.12"]], execution_modes: ["offline"] },
  },
  live: { enabled: false, reason: "live_disabled", provider_validated: false },
  ai_security_fix: { enabled: false, reason: "not_implemented_live" },
};
const projects = {
  root_id: "workspace",
  projects: [{ project_id: "legacy_shop", relative_path: "samples/legacy_shop", available: true },
    { project_id: "universal_py3", relative_path: "tests/fixtures/universal_py3", available: true }],
  cases_profiles: [{ id: "legacy_shop_golden", project_id: "legacy_shop", available: true },
    { id: "universal_py3_golden", project_id: "universal_py3", available: true }],
  fixture_profiles: [{ id: "legacy_shop_py27_py312", project_id: "legacy_shop", available: true }],
};
const parameters = {
  operation: "migration", project_id: "legacy_shop", source_version: "2.7", target_version: "3.12",
  execution_mode: "offline_fixtures", max_iterations: 5, verification_level: "behavior",
  fixture_profile_id: "legacy_shop_py27_py312", cases_profile_id: "legacy_shop_golden",
};
function state(status = "done") {
  return { status, phase: "reporting", isolation: "docker", modules: [], security: { before: 0, after: 0, findings: [] },
    hashes: { files: {}, unchanged: status === "done" ? true : null },
    metrics: { tests_passed: 0, tests_total: 0, lines_migrated: 0, tokens_in: 0, tokens_out: 0, cost_usd: 0, seconds: 0 }, chain_intact: true };
}
function details(lifecycle = "done", overrides = {}) {
  return { run_id: "run-one", instance_id: capabilities.instance_id, parameters: copy(parameters), lifecycle,
    finalized: ["done", "failed"].includes(lifecycle),
    execution: { effective: "offline_fixtures", simulated: false, ai_generated: false, live_enabled: false },
    result: { compatibility: null, security_audit: null, target_tests: null, security_fix: null, limitations: [] },
    state: state(lifecycle === "finalizing" ? "running" : lifecycle), ...overrides };
}
function report(events = []) {
  return { simulation: false, notice: "Frontend contract fixture; not an executed migration.", state: state(),
    settings: { pipeline: "fixtures", model: "mock", max_iterations: 5 }, allowed_differences: [],
    verification: { control: { parameters: copy(parameters), live_enabled: false } }, events };
}
module.exports = { copy, capabilities, projects, parameters, state, details, report };
