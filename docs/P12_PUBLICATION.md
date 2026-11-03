# P12: final GitHub publication preparation

Verification date: **3 November 2026**. Starting branch: `release/hackathon`;
starting HEAD: `ab0c48b2e221dae58c64cf5eaeeb7ac49ab54a05`.
The owner confirms the previously disclosed Meta key is revoked. No new key is
required for source publication, offline judge checks or saved-report replay.
No Meta call, credit use, push, merge, branch switch or default-branch change is
part of this task. This is a local verification record, not a published release.

## Git and remote state

The starting working tree was clean. All local backend, frontend and integration
branch histories are ancestors of the assembled release. Existing branch refs,
sample sources, fixture content and frontend code remain unchanged.

Live read-only `git ls-remote --symref origin HEAD 'refs/heads/*'` succeeded using
the existing Git credential manager. It returned:

| Remote ref | Actual SHA |
| --- | --- |
| HEAD → main | `b1a2f5b018a2c63f857029ec0224ce1e1b1ce4d1` |
| main | `b1a2f5b018a2c63f857029ec0224ce1e1b1ce4d1` |
| Front | `b1a2f5b018a2c63f857029ec0224ce1e1b1ce4d1` |
| backend/codex | `2e330c7ff380b356fa8c1c0c77e49fed41b8bfed` |
| frontend/claude | `968c5b8e72be45dcd3cf862aa611c7213bd69f2d` |
| release/hackathon | Not yet present |

Origin fetch/push URL:
`https://github.com/kasestuck/MetaAI-proofport.git`.
There is no separate push URL/refspec override. Git Credential Manager is
configured. The release has no upstream yet. Local `main` equals remote `main`;
at the starting release HEAD the release was 56 commits ahead, zero behind.
All observed remote branches are included in the release ancestry. The P12
documentation commit adds to that same history; it does not replace main.

The remote repository **exists and is readable using the configured Git access**.
The GitHub connector and an anonymous GitHub REST metadata request returned 404.
Public/signed-out access is therefore **not confirmed**; the response does not
distinguish a private repository from access restrictions. No visibility setting
was changed. A successful Git read does not prove push permission: no receive-pack
or dry-run push was attempted. The available configured route is ordinary HTTPS
Git through the existing credential manager. GitHub Desktop may use that same
repository; SSH access and write permission were not independently tested.

## Included components and documentation

Checked present: Python/PHP language adapters and pipelines, Docker runner and
verification harnesses, AI migration/provider/prompts, LLMClient, Python/PHP
security scanners and fix engines, immutable RunSpec and API Control Plane,
dashboard, evidence integrity handling, replay, English README, MIT license,
third-party notices, security policy and release/submission documentation.

Exactly ten scenario directories are present under `judge_tests/`. Each has an
English README, source/profile references, runtime/dependency requirements,
Windows run commands, checks, limits and UI/CLI boundaries. The root README has
the required **Try Proofport — 10 Judge Test Scenarios** section and links to the
complete [scenario table and setup](../judge_tests/README.md).

## Verification results

Fast backend output:

```text
554 passed, 58 deselected in 71.76s (0:01:11)
```

Frontend Node tests: **73 passed, 0 failed, 0 skipped**. These include legacy/v1
behavior, PHP controls, errors, preflight, idempotency, finalizing, old reports,
historical provenance and rejected security-fix labels. No redesign or frontend
change was necessary. `pip check`: **No broken requirements found**.

Selected genuine-candidate and real audit API Docker regressions:

```text
3 passed, 3 deselected in 19.72s
```

The Python model candidate still passes **31/31 cases and 3/3 MathTests**; the PHP
model candidate still passes **22/22 cases and 9/9 tests**. Tests prohibit model
construction/calls. Original Python/PHP/security live reports, artifact receipts,
SHA-256 and evidence chains were independently checked without changing them.
The real eval proposal remains **needs_review**, with **5/9 cases, 0/1 ConfigTests**
and `ai_security_fix: false`; it is not presented as a successful remediation.

Docker Desktop was initially stopped. The installed Desktop was started for
verification and reported a Linux daemon. Only existing images were used;
nothing was pulled. No unrelated service was stopped. The complete ten-scenario
offline rerun and saved-summary integrity verification are recorded below.

New full judge run: **5 PASS, 5 NEEDS_REVIEW, 0 FAIL, 0 SKIP; exit 0**.
All mandatory assertions completed and passed. NEEDS_REVIEW means the intended
review/rejection checks passed, not that the patch was accepted.

| Scenario | Actual result |
| --- | --- |
| 01_python_legacy_migration | PASS |
| 02_python_math_edge_cases | PASS |
| 03_python_compatibility | PASS |
| 04_python_sql_injection | NEEDS_REVIEW |
| 05_python_unsafe_eval | NEEDS_REVIEW |
| 06_python_secrets_crypto | NEEDS_REVIEW |
| 07_php_legacy_migration | PASS |
| 08_php_xss | NEEDS_REVIEW |
| 09_php_command_injection | PASS |
| 10_php_security_regression | NEEDS_REVIEW |

Retained local summary: `backend/.work/judge-75272e49/summary.json`.
SHA-256: `9a76c9d0966245244236207de1f3e6c5aa43a690fc573e0ec246e5bb75e4bfa6`.
The separate `runner.py --verify-summary` command passed receipt/result equality,
ordered evidence chain and summary decision/count checks, exit 0. All ten runs
are explicitly `offline_authored_fixtures_not_AI` with zero model calls. The
previous P11 summary was also verified without reinterpreting it as a new run.
No complete unrelated Docker matrix, new model response or host project execution
was used.

## Secret and artifact checks

`backend.release audit` checks tracked files and all local Git objects, including
unreachable objects. No available-key/common-prefix credential matches,
suspicious long key assignments, tracked private env files or generated files
were found. The P11 snapshot examined 767 blobs / 1,207 total objects; the final
P12 count grows with its documentation commit. The command prints counts only.

The revoked local key remains private and ignored. It was neither displayed nor
modified. No new key was requested. Exact matching covers available local key
copies; unknown retired values cannot be reconstructed. Revocation is the owner's
confirmation, not a new API authorization test. No universal absence-of-secrets
guarantee or remote/server-deleted-object audit is claimed.

Shared `.gitignore` protects private `.env` files, `.venv`, caches and working
directories. `.env.example` is the intentional empty-key template. No `.work`,
`.tmp`, environment, candidate execution output or report pack is tracked.
Authored judge fixtures are intentional test inputs, not runtime outputs.

The existing curated demo pack (130 files) passed receipt/projection/source
verification and available/common credential checks. It remains ignored and
local. Automated checks do not replace the separate owner review required before
sharing it. A source clone does not include the private historical proof files.
The ten offline judge scenarios do not require those private files or an API key.

## Safe publication command — not executed

After the owner separately authorizes publication, from the repository root:

```powershell
git push --set-upstream origin release/hackathon
```

This publishes only the named branch with an ordinary non-force push; it does
not merge main or change the default branch. If authentication or non-fast-forward
checks reject it, stop and inspect the new remote state. Do not add force flags,
delete branches or rewrite history. Re-read remote heads immediately before
publication, since another contributor may have changed them after this audit.

After authorized publication, the intended branch URL is:
`https://github.com/kasestuck/MetaAI-proofport/tree/release/hackathon`.
It is **not claimed to exist yet**. Check source visibility while signed out.
Publication to an existing private repository does not automatically make it
public; visibility changes require a separate deliberate owner action.

## Recommended main/default-branch integration

Keep **main as the default branch**. After publishing and reviewing the release,
open a pull request from `release/hackathon` to `main`. At the audited refs, main
is an ancestor of the release, so there is no unrelated-history problem.
Use an ordinary reviewed merge preserving both histories; do not squash/rebase
or replace main forcibly. Recheck ancestry and conflicts if main has advanced.
Merge only after separate owner approval. No PR, merge, main push or default
branch change was performed during P12. Until then, use the explicit release
branch link for review rather than the old default-branch page.

## Publication/submission gates

The owner-confirmed old-key revocation gate is resolved. The remaining gates are:

- Owner approval for the first ordinary release-branch push; actual write access
  is not tested before that approval.
- Public/signed-out access to the intended source revision and later reviewed
  main integration. GitHub currently exposes no confirmed anonymous access.
- Separate owner review and sharing of any historical proof pack; add and verify
  its real download URL. Do not bulk-add ignored runtime data.
- Record/export the three-minute video using the existing script/runbook, label
  saved replay honestly, and verify its signed-out video URL.
- Fill public name and GitHub profile TODOs without inferring them from Git
  authorship. Team remains Proofport, size 1; AI assistants are tools.
- Confirm final organizer requirements and deadline in the owner's portal and
  submit the real repository/video/team links. No submission was performed.

See the [submission checklist](SUBMISSION_CHECKLIST.md). Finite fixture coverage,
partial Python 2 Bandit coverage, lexical PHP rules, manual review of changed
security contracts and Docker's shared-kernel isolation remain documented limits.
No claim of universal migration or complete security remediation is made.
