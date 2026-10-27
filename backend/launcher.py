"""Launch the local server and open its browser only after it is ready."""

import os
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

import uvicorn


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
    try:
        port = int(os.environ.get("PROOFPORT_PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit("PROOFPORT_PORT must be a number between 1 and 65535.") from None
    if os.environ.get("PROOFPORT_NO_BROWSER") != "1":
        threading.Thread(target=open_when_ready, args=(f"http://127.0.0.1:{port}",), daemon=True).start()
    uvicorn.run("backend.api.main:app", host="127.0.0.1", port=port)
