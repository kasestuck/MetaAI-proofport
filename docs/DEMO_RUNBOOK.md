# Demo runbook — saved genuine Meta runs

No command here grants paid permission. Do not invoke any P8 `--execute` command.
The three main scenarios inspect past real runs, not new live generation.

## Prerequisites

Start with the current local `integration/p4` checkout, Python 3.12 and installed
requirements. Run `start.bat`, or launch uvicorn as shown in the root README.
Normal replay needs neither Docker nor a model key. Actual offline operations
need the installed, verified images/profiles described in the README.

From the repository root on the original workstation:

```powershell
.venv/Scripts/python.exe -m backend.release prepare-demo
```

Expected: a **new** `backend/.work/p10-demo-<id>/` and sibling ZIP. The command
first verifies the three original report hashes, their artifact seals, HTML/JSON,
evidence chains and current source hashes. Missing/changed proof stops export;
there is no replacement result. Existing artifacts are never overwritten/deleted.

The pack contains all original sealed artifacts and full owned source snapshots,
three dashboard projections, a raw-report HTML index and a SHA-256 manifest.
Projection events are the exact original events; no event or success is invented.
Unknown total elapsed time and migrated-line count are omitted. Reported tokens
and cost are historical, not new usage. The security projection deliberately uses
run status `failed` and finding status `needs_review`.

Check a transferred/unpacked copy with:

```powershell
.venv/Scripts/python.exe -m backend.release verify-demo --pack backend/.work/<pack-name>
```

Portable verification checks original seals/recorded source bytes and rebuilds the
projection for exact equality. A fresh clone alone has no original local recordings
and cannot manufacture this pack. Get the reviewed owner export, not the whole
`.work` directory. This is local consistency verification, not a signed Meta receipt.

## Scenario A — Python migration

1. In the console, click **Open saved report** and choose `proofport-python.json`.
2. Confirm **Saved real Meta run**, Python, `done`, and browser chain `ok`.
3. Open **Compatibility**: Python 2.7.18 → 3.12.16; **31/31 cases**, **3/3 tests**.
4. Open **Evidence**: original hashes unchanged, actual model event/provenance.
5. For the raw full record, open `python/report.html` from pack `index.html`.

Say: “This is the saved verification of a real Meta run, not a new live call.”
Do not call a running offline dashboard fixture job “the Meta migration.”

## Scenario B — PHP migration

1. Import `proofport-php.json` with the same button.
2. Confirm saved real Meta provenance, PHP and `done`.
3. Open **Compatibility**: **22/22 cases**, **9/9 native tests** on PHP 8.3.36,
   recorded against PHP 7.4.33. Only `src/legacy.php` was AI-translated.
4. Use `php/report.html` to inspect the original raw report/usage.

This module run did not include a security audit. Zero findings in its projection
mean **not scanned**; the interface explicitly says so.

## Scenario C — AI Security Fix rejected

1. Import `proofport-security.json`.
2. Confirm **Saved real Meta proposal · rejected / needs review** and run `failed`.
3. Open **Security**, expand the proposal: syntax passed, **5/9** cases,
   **0/1** ConfigTests; B307 was removed but B110 appeared.
4. Show rollback/no accepted patch and **needs_review**. The next request was
   stopped locally by the input guard, not sent to Meta.
5. Explain the Python 2.7 AST issue and expression-contract change. P9 now
   detects direct missing AST APIs and reduces repair context; it has not
   produced or verified another live security patch.

Do not describe warning disappearance or a compile pass as remediation.

## Optional real offline operation

This is a separate scenario, **not** one of the historical Meta jobs. For PHP
choose Migration, `php_shop`, 7.4 → 8.3, matching server profiles, then readiness
and Start. Expect 22 golden comparisons and nine tests. Audit reports ten potential
warnings without execution. Compatibility of the untouched legacy syntax on 8.3
correctly fails. Show actual outcomes, never fabricated timing/progress.

## Rehearsal and recording

- Use a quiet desktop with no terminal displaying private configuration.
- Open the three JSON files and raw HTML index beforehand. Check chain `ok`.
- Record only the app/report windows. Never display `.tmp`, the key, account
  pages, tokens, private notifications or unrelated projects.
- Keep “Saved real run / no new API call” visible during historical scenes.
- Use [the three-minute script](DEMO_SCRIPT.md), rehearse with a timer, and
  capture the final video yourself. P10 creates no screenshots or video.
- Test the final video and published links in a signed-out browser.

## Failure procedure

If pack verification fails, stop and retain the files. Do not recalculate seals
to hide a mismatch. If the server is unavailable, open the original self-contained
HTML reports and clearly state they are saved results. If Docker is unavailable,
do not run projects on Windows. A blocked preflight is an honest outcome.

Public Live AI stays disabled. Any new generation needs separately reviewed
scope, current model/pricing verification and explicit owner budget approval.
