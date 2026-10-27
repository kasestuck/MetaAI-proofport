# Backend working rules

- Work only on `backend/codex`.
- Edit only `backend/`, `tests/`, and `start.bat`. This requested root
  `AGENTS.md` is the one exception. Put pinned dependencies in
  `backend/requirements.txt`.
- Keep changes simple, original, and focused on the current milestone.
- Make small, focused commits. Never stage unrelated changes.
- Run the relevant tests before finishing and report their actual output.
- Never commit secrets, `.env`, virtual environments, caches, or generated data.
- Preserve the shared API contract. Read `docs/BRIEF.md` fully when available.
  Until it is supplied, use section 8 of the user-supplied full specification,
  as authorized in this chat.
- Treat sample sources as read-only; hash actual bytes and never execute them.
- Label simulated evidence and metrics honestly; do not claim real migration,
  test execution, security remediation, or model usage from a simulation.
