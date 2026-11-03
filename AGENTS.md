# Proofport working rules (P11 judge-suite preparation)

- P11 explicitly authorizes creating and working on `release/hackathon` from
  audited `integration/p4`. Keep all original branch refs and main unchanged.
  No push, history rewriting, forced operations or branch deletion. Merge only
  genuinely useful unique commits; stop on conflicts or potential lost changes.
- P11 permits `judge_tests/`, release documentation/configuration at the root and
  in `docs/`, plus focused changes in `backend/`, `tests/` and `start.bat`.
  Frontend changes must be necessary for truthful replay/demo integration;
  preserve the design. Put pinned dependencies in `backend/requirements.txt`.
- Keep changes simple, original, and focused on the current milestone.
- Make small, focused commits. Never stage unrelated changes.
- Run the relevant tests before finishing and report their actual output.
- Never commit secrets, `.env`, virtual environments, caches, or generated data.
- Preserve the shared API contract. Read `docs/BRIEF.md` fully when available.
  Until it is supplied, use section 8 of the user-supplied full specification,
  as authorized in this chat.
- Treat demo sources/fixtures as read-only; hash actual bytes. Execute projects
  and model-generated candidates only in Docker, never on the host. No host fallback.
- Label simulated evidence and metrics honestly; do not claim real migration,
  test execution, security remediation, or model usage from a simulation.
- No Meta API calls or credit use during P11. Showing a retained real run is
  saved-report replay, never a new live run. Never suppress failures for a demo.
- Keep raw/generated runtime data and demo packs ignored; publish them only
  after a separate owner review. Do not delete retained working artifacts.
- No screenshots. Run fast tests first, then only necessary Docker smoke checks.
- Judge fixture sources, tests, input cases and explicitly authored offline
  candidates are intentional versioned inputs, not generated execution results.
  Put all execution results under ignored backend/.work, never judge_tests/.
- Missing mandatory Docker/runtime checks mean SKIP and a nonzero suite exit.
  Expected NEEDS_REVIEW may pass its scenario assertions but never means fixed.
- MIT for the whole project was explicitly chosen by the owner during P10;
  preserve third-party notices and the existing sample license.
