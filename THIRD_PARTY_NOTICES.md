# Third-party notices

Proofport's owned code is MIT licensed. Dependencies retain their own copyright,
license text and terms. They are installed through their distributions, not
vendored here. Preserve full notices supplied with redistributed packages/images;
this inventory is not a substitute for those notices or legal advice.

Read from the installed Python 3.12 environment during P10; exact versions are
in `backend/requirements.txt`. `pip check` passed, which checks consistency,
**not known vulnerabilities**. No comprehensive dependency vulnerability audit
or independent license provenance review is claimed.

| Components | Distribution license metadata |
| --- | --- |
| FastAPI, Pydantic, pydantic-core, pytest, annotated-doc, annotated-types, anyio | MIT |
| h11, iniconfig, jiter, pluggy, truststore, typing-inspection | MIT |
| Uvicorn, Starlette, httpx, httpcore, httpx2, httpcore2, idna, click, python-dotenv | BSD-3-Clause |
| colorama | BSD; see the distribution's full license |
| OpenAI-compatible SDK (`openai`) | Apache-2.0 |
| certifi | MPL-2.0 |
| packaging | Apache-2.0 OR BSD-2-Clause |
| Pygments | BSD-2-Clause |
| sniffio | MIT OR Apache-2.0 |
| typing-extensions | PSF-2.0 |

Bandit 1.8.6 is installed in a separate scanner image (Apache-2.0). Its dependencies
retain their notices. Python/PHP interpreters and official images, Docker Desktop,
Chrome and optional Playwright are separate tools under their own licenses/terms.
Image IDs are recorded at execution. Floating base tags and scanner transitive
installs mean a rebuild may change an image and require fresh proof receipts.

No downloaded font, third-party runtime package or CDN bundle was found among
tracked frontend files. The frontend uses system fonts and inline UI assets.
Fast tests use Node's built-in runner; real browser checks additionally use locally
installed Playwright/Chrome, not application runtime dependencies.

The owned `samples/legacy_shop/LICENSE` is preserved. PHP demos/test fixtures
were written for Proofport and are covered by the project's MIT license.
Meta API/model usage remains subject to Meta's terms; MIT grants no API access
and does not relicense Meta models or services.
