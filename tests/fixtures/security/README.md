# Offline security proposals (not Meta AI)

These source-hash-bound manifests contain authored candidate transformations,
never canned test/scan outcomes. The verifier obtains results from real Docker.

- `legacy_shop_fixes.json`: eval, SQL parameters, non-shell `cp`, and an
  environment-backed secret proposal. All change or leave uncertainty about
  existing behavior/configuration and must remain review-only.
- `constant_command_fix.json`: an exact constant-command to identical absolute
  argv hardening fixture for `../security_subject/`, with no public API change.
- `constant_argv_triage.json`: contextual classification of the retained B603
  advisory when literal absolute argv and shell=False are independently checked.

No secret value is embedded in these manifests. The environment proposal is
authored as an assignment instruction instead of copying the original value.
The accepted project, original project and rejected staging artifacts are
separate. Fixture tests are excluded from host pytest and run only in Docker.
Successful verification establishes recorded behavior and narrow policy scope,
not universal safety or real AI Security Fix readiness.
