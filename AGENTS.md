# Proofport working rules (P10 release preparation)

- Work only on `integration/p4` for the currently authorized release task.
  Do not merge, rebase, push or switch branches. Stop if unrelated changes appear.
- P10 permits release documentation/configuration at the repository root and in
  `docs/`, plus focused changes in `backend/`, `tests/` and `start.bat`.
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
- No Meta API calls or credit use during P10. Showing a retained real run is
  saved-report replay, never a new live run. Never suppress failures for a demo.
- Keep raw/generated runtime data and demo packs ignored; publish them only
  after a separate owner review. Do not delete retained working artifacts.
- No screenshots. Run fast tests first, then only necessary Docker smoke checks.
- MIT for the whole project was explicitly chosen by the owner during P10;
  preserve third-party notices and the existing sample license.
