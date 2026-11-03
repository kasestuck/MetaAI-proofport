"""Launch the local server and open its browser only after it is ready."""

import os
from pathlib import Path
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

import uvicorn
from dotenv import dotenv_values


def configure_live_demo(root=None, environment=None):
    """Load only the approved mode; keep keys in P13's isolated private file.

    No HTTP request or paid permission is created here. P13 still checks the
    private configuration, model access, fixed budgets and per-run UI consent.
    """
    from backend.core.projects import linked
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    environment = os.environ if environment is None else environment
    path = root / "backend/.tmp/meta-demo.env"
    if not path.is_file() or path.stat().st_size > 16384 or any(linked(p) for p in (path,*path.parents)):
        return False
    settings = dotenv_values(path)
    required = {"LLM_MODE":"live", "LIVE_DEMO_APPROVED":"true", "LIVE_DEMO_KEY_CONFIRMED_NEW":"true",
                "MODEL_NAME":"muse-spark-1.3", "MODEL_BASE_URL":"https://api.meta.ai/v1",
                "PRICE_IN_PER_MTOK":"1.25", "PRICE_OUT_PER_MTOK":"4.25"}
    if not settings.get("MODEL_API_KEY") or any(settings.get(k)!=v for k,v in required.items()):
        return False
    environment["LLM_MODE"] = "live"
    return True


def default_port(live_demo, environment=None):
    environment = os.environ if environment is None else environment
    port = int(environment.get("PROOFPORT_PORT", "8765" if live_demo else "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("Port must be within 1..65535")
    return port


def open_when_ready(url: str = "http://127.0.0.1:8000"):
    for _ in range(100):
        try:
            with urlopen(url + "/api/health", timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.1)


if __name__ == "__main__":
    live_demo = configure_live_demo()
    try:
        port = default_port(live_demo)
    except ValueError:
        raise SystemExit("PROOFPORT_PORT must be a number between 1 and 65535.") from None
    if os.environ.get("PROOFPORT_NO_BROWSER") != "1":
        threading.Thread(target=open_when_ready, args=(f"http://127.0.0.1:{port}",), daemon=True).start()
    if live_demo:
        print("P13 live configuration loaded privately. Paid generation still requires UI consent; no model call at startup.")
    uvicorn.run("backend.api.main:app", host="127.0.0.1", port=port)
