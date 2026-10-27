from backend import launcher


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
