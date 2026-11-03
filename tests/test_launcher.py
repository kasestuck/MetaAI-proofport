from backend import launcher
import pytest


def test_browser_opens_only_after_health_is_ready(monkeypatch):
    calls = []
    opened = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    def health(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise OSError("not listening yet")
        return Response()

    monkeypatch.setattr(launcher, "urlopen", health)
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    launcher.open_when_ready()
    assert len(calls) == 2
    assert opened == ["http://127.0.0.1:8000"]


def test_browser_does_not_open_if_server_never_starts(monkeypatch):
    opened = []
    # A refused connection is the usual failure before uvicorn binds its socket.
    def refused(*args, **kwargs):
        raise OSError("connection refused")
    monkeypatch.setattr(launcher, "urlopen", refused)
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    launcher.open_when_ready()
    assert not opened


def test_approved_demo_startup_loads_mode_but_never_exports_key(tmp_path):
    path=tmp_path/"backend/.tmp/meta-demo.env";path.parent.mkdir(parents=True)
    path.write_text("MODEL_API_KEY=unit-private-key\nLLM_MODE=live\nLIVE_DEMO_APPROVED=true\n"
                    "LIVE_DEMO_KEY_CONFIRMED_NEW=true\nMODEL_NAME=muse-spark-1.3\n"
                    "MODEL_BASE_URL=https://api.meta.ai/v1\nPRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\n")
    environment={"LLM_MODE":"mock"}
    assert launcher.configure_live_demo(tmp_path,environment)
    assert environment=={"LLM_MODE":"live"}
    assert launcher.default_port(True,environment)==8765
    assert launcher.default_port(False,{})==8000
    assert launcher.default_port(True,{"PROOFPORT_PORT":"8001"})==8001


@pytest.mark.parametrize("change",["key","approval","confirmed","model","price"])
def test_incomplete_private_config_does_not_enable_live_startup(tmp_path,change):
    path=tmp_path/"backend/.tmp/meta-demo.env";path.parent.mkdir(parents=True)
    fields={"MODEL_API_KEY":"unit-key","LLM_MODE":"live","LIVE_DEMO_APPROVED":"true",
            "LIVE_DEMO_KEY_CONFIRMED_NEW":"true","MODEL_NAME":"muse-spark-1.3",
            "MODEL_BASE_URL":"https://api.meta.ai/v1","PRICE_IN_PER_MTOK":"1.25","PRICE_OUT_PER_MTOK":"4.25"}
    fields[{"key":"MODEL_API_KEY","approval":"LIVE_DEMO_APPROVED","confirmed":"LIVE_DEMO_KEY_CONFIRMED_NEW",
            "model":"MODEL_NAME","price":"PRICE_OUT_PER_MTOK"}[change]]=""
    path.write_text("\n".join(k+"="+v for k,v in fields.items()))
    environment={}
    assert launcher.configure_live_demo(tmp_path,environment) is False and environment=={}
