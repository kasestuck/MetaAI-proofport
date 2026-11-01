"""Opt-in local HTTP/browser verification server; never the production entrypoint.

Run uvicorn integration_probe:create_probe --factory --app-dir tests on loopback.
The two-second finalization delay exposes a real intermediate lifecycle to the
browser; the original hash/evidence/report finalizer still performs every check.
No results, capability receipts, fixtures or HTTP contracts are substituted.
"""

import os
import time


def create_probe():
    if os.environ.get("PROOFPORT_INTEGRATION_TESTS") != "1" or os.environ.get("LLM_MODE") != "mock":
        raise RuntimeError("Integration probe requires explicit opt-in and LLM_MODE=mock.")

    import backend.llm.client as llm

    def forbidden(*args, **kwargs):
        raise AssertionError("Meta/LLM construction and completion are forbidden during P4.3 verification.")

    llm.OpenAI = forbidden
    llm.LLMClient.complete = forbidden
    from backend.api.main import create_app

    app = create_app()
    original_finish = app.state.runs._finish

    def observed_finish(run):
        time.sleep(2)
        original_finish(run)

    app.state.runs._finish = observed_finish
    return app
