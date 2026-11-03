# Security policy

Proofport is a local hackathon prototype. No supported production release or
response-time commitment is offered. Do not expose it to an untrusted network.

## Reporting

Do not publish credentials, personal sources, working archives or unredacted
exploit inputs in an issue. If the repository's Security tab offers private
reporting, use it; otherwise contact the owner through a private channel the
owner explicitly provides. **No private contact channel is configured yet.**
Do not invent one. Establishing it is an open release checklist item.

Include the commit, component, sanitized reproduction, observed impact and
environment. Do not test against systems you do not own.

## Execution and access

Projects/model candidates run only in Docker with no network, non-root UID,
read-only mounts and resource/time/output bounds. There is no host fallback.
Demo sources contain intentional unsafe examples; never run them directly on
Windows or use them as production libraries. Never mount keys, writable original
projects or the Docker socket. Trusted image setup and host/Docker patching are
operator responsibilities; containers share their host kernel.

The API binds to loopback. Host/Origin checks limit browser access but are not
authentication against local users/processes. Project policy rejects escape
paths, links/junctions, hardlinks and secret/service directories. Browser callers
cannot supply Docker commands or mount options. Remote hosting is unsupported.

## Models, secrets and exports

Generic API/UI live generation stays disabled. The two fixed P13 Dashboard
demos additionally require an isolated new key, local operator permission and
expiring per-run paid UI consent. Live CLI jobs also require separate consent
and bounded budgets; API errors/timeouts stop without paid retries.
Offline fixtures and saved real runs are explicitly labelled.

Keep keys in ignored private configuration, never browser forms, recordings,
issues or committed files. Git ignore is an accidental-staging guard, not a
secrets manager. If a key leaks, revoke/rotate it and privately review history;
this project never rewrites history automatically.

Before publishing a demo ZIP, verify and privately inspect it. It includes owned
source snapshots, actual model output and observations. Known-key/common-token
scans cannot prove absence of every possible secret. Publish only the reviewed
pack, never unrelated `.work`/`.tmp` directories. Generated packs stay outside Git.

## Findings and evidence

Scanner findings are potential risks, not confirmed exploits. Zero findings do
not certify safety; parse errors and missing checks remain visible. Candidates
are staged, tested, rescanned and evaluated against conservative policy. Failed
promotion rolls back while retaining evidence. Eval, crypto, data/API/configuration
changes and insufficient coverage require review. Model confidence is not approval.

Evidence hashes check local consistency, not external signatures or protection
from someone rewriting every artifact. Finite tests do not prove universal
behavior or complete remediation. Current findings: [P9 audit](backend/P9_STABILIZATION.md).
