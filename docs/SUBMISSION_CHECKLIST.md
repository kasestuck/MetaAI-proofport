# Hackathon submission checklist

Prepared **November 2, 2026**. Submission is **not complete**. This file creates
no account, public link, upload, push or submission.

## Sources and certainty

The owner-supplied *Proofport — Full Project Specification*, sections 2 and 15,
requires a public GitHub repository, genuine Meta usage, a three-minute demo,
built-during-hackathon/AI-assistance notes, team information and the theme.
Its PDF SHA-256 is
`2611cf3892bdc1738d11efd3b027a64fde174a2d8200f693fae8fca2b54d77b8`.
The PDF is an owner brief, **not independently verified organizer rules**; its
older implementation instructions do not override current safety constraints.

Primary sources checked:
[Meta event](https://dev.meta.ai/events/global-hackathon) and
[organizer event](https://cerebralvalley.ai/e/meta-ai-developer-hackathon).
They confirm the event, tracks/theme and November 4 submission deadline.
The public [waiver page](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver)
returned only a loading shell. Full final rules, authenticated submission fields,
video hosting/length constraints and participant acceptance remain owner checks.
Do not substitute a third-party blog or this brief for final organizer rules.

## Deadline

Published deadline: **Wednesday, November 4, 2026, 9:00 PM ET**.
On that date this is **November 5, 02:00 UTC**, or **November 5, 07:00 in
Asia/Qyzylorda (UTC+5)**. Source dates may change; recheck the official portal
and submit early. No reminder or submission automation was created.

## Required submission gates

- [ ] **Public GitHub / judge access.** Configured repository:
  `https://github.com/kasestuck/MetaAI-proofport`. Anonymous GitHub REST returned
  **404** during P10. It may be private, absent or inaccessible; public access
  cannot be claimed. The connector also could not see it. The owner must review
  and publish the intended release snapshot, then test signed out.
- [ ] **Correct code revision published.** P10 commits are local on `integration/p4`.
  No merge/rebase/push was performed. Confirm the published branch/link contains
  the reviewed frontend/backend, README and license; an old default branch is not enough.
- [x] **English README drafted**, including architecture, Windows/Docker setup,
  actual results, limitations, security, Meta integration and AI disclosure.
- [x] **MIT license selected by the owner and added**; sample license preserved;
  dependency notice inventory prepared.
- [x] **Genuine product Meta use documented.** P8.2 Python 31/31 + 3/3; P8.3
  PHP 22/22 + 9/9; P8.4 rejected proposal. This is more than coding-assistant use.
- [ ] **Public reviewed proof pack.** Local verified export exists. Inspect and
  upload only the curated pack; never publish `.tmp`, private env or unrelated
  `.work`. Add a real download URL and test independent verification after transfer.
  Current public proof-pack URL: **TODO**.
- [x] **Three-minute English demo script and runbook prepared**.
- [ ] **Final video recorded/exported**, actual duration checked, saved runs
  labelled, no secrets exposed. Video URL: **TODO**.
- [ ] **Video opens without login**, in a signed-out browser; sound/text legible.
- [x] **Team confirmed:** Proofport; team size **1**; role **Solo Developer /
  Project Creator**. Codex/Claude Code are tools, not team members.
- [ ] **Creator's public name: TODO**; **GitHub profile: TODO**, intentionally
  left for the owner. Never infer identity from commit authors or repository ownership.
- [x] **Track/theme stated:** Indie Developer / Push the Frontier (software).
- [x] **Built during the hackathon / AI assistance disclosed.** Local history
  begins October 27. Dependencies retain separate licenses; dates alone are not
  independent ownership/originality proof.
- [ ] **Participant acceptance and latest official rules confirmed** in the
  owner's account, including any final repository/video/team requirements.
- [ ] **Private security-reporting channel configured**, without publishing secrets
  (project release recommendation, not a verified organizer requirement).
- [ ] **Final portal submission completed** before the deadline; keep the actual
  confirmation and URLs. P10 does not submit on the owner's behalf.

## Before publishing

- [ ] Inspect the final local commit range and run `python -m backend.release audit`.
- [ ] Check README links, selected branch, MIT/third-party notices and `.gitignore`.
- [ ] Keep `.env`, `.venv`, caches, generated candidates/reports and private keys out
  of Git. Explicitly reviewed demo archives are published separately, not staged wholesale.
- [ ] Run fast tests and bounded smoke from [release readiness](RELEASE_READINESS.md).
- [ ] Recheck the exported pack after downloading/unpacking it on another path.
- [ ] Rehearse all three scenarios with [runbook](DEMO_RUNBOOK.md) and
  [script](DEMO_SCRIPT.md). A saved replay must never be presented as new generation.
- [ ] Sign out and independently check repository, video and proof URLs.

## Claims to preserve

The genuine demonstrations are scoped module migrations, not all-project live
migration. P8.4 remains rejected/needs_review. P9 hardening did not create a new
accepted live security patch. No complete security coverage, production isolation,
universal equivalence, new paid calls or successful portal submission is claimed.
