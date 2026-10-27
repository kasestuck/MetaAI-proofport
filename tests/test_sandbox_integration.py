import json
from pathlib import Path

import pytest

from backend.sandbox.runner import DockerRunner


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runner():
    runner = DockerRunner()
    assert runner.available(), "Real Linux Docker is required for enabled integration tests"
    runner.image_id("python:2.7")
    runner.image_id("python:3.12-slim")
    return runner


def test_real_isolation_and_resource_configuration(runner, tmp_path):
    marker = tmp_path / "original.txt"
    marker.write_text("unchanged")
    script = '''import json,os,socket
def blocked(path):
    try:
        open(path, 'w').write('changed')
        return False
    except OSError:
        return True
try:
    socket.create_connection(('1.1.1.1', 80), timeout=0.2)
    external = True
except OSError:
    external = False
status = open('/proc/self/status').read()
print(json.dumps({'uid': os.getuid(), 'source_readonly': blocked('/src/original.txt'), 'root_readonly': blocked('/etc/proofport-probe'), 'external_network': external, 'interfaces': os.listdir('/sys/class/net'), 'no_new_privs': 'NoNewPrivs:\\t1' in status, 'caps_zero': 'CapEff:\\t0000000000000000' in status, 'memory': open('/sys/fs/cgroup/memory.max').read().strip(), 'pids': open('/sys/fs/cgroup/pids.max').read().strip(), 'cpu': open('/sys/fs/cgroup/cpu.max').read().strip(), 'tmp_bytes': os.statvfs('/tmp').f_blocks * os.statvfs('/tmp').f_frsize}))
'''
    result = runner.run("python:3.12-slim", tmp_path, ["python", "-c", script])
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["uid"] == 65534
    assert data["source_readonly"] and data["root_readonly"]
    assert not data["external_network"]
    assert data["interfaces"] == ["lo"]
    assert data["no_new_privs"] and data["caps_zero"]
    assert int(data["memory"]) == 256 * 1024 * 1024
    assert data["pids"] == "32"
    assert data["cpu"] == "100000 100000"
    assert data["tmp_bytes"] <= 64 * 1024 * 1024
    assert marker.read_text() == "unchanged"


def test_timeout_removes_its_container(runner, tmp_path):
    result = runner.run("python:3.12-slim", tmp_path, ["python", "-c", "import time; time.sleep(60)"], timeout=1)
    assert result.timed_out
    assert runner._metadata(["container", "inspect", runner.last_container]).returncode != 0


def test_output_limit_is_enforced(tmp_path):
    runner = DockerRunner(max_output=4096)
    result = runner.run("python:3.12-slim", tmp_path, ["python", "-c", "import sys; sys.stdout.write('x'*1000000); sys.stdout.flush()"])
    assert result.output_exceeded
    assert len(result.stdout.encode()) + len(result.stderr.encode()) <= 4096
    assert runner._metadata(["container", "inspect", runner.last_container]).returncode != 0


def test_memory_exhaustion_is_contained(runner, tmp_path):
    result = runner.run("python:3.12-slim", tmp_path, ["python", "-c", "x=bytearray(400*1024*1024); print(len(x))"])
    assert result.exit_code != 0
    assert not result.timed_out
    assert runner._metadata(["container", "inspect", runner.last_container]).returncode != 0


def test_process_limit_is_enforced(runner, tmp_path):
    script = '''import json,subprocess
children=[]
try:
    for i in range(100):
        children.append(subprocess.Popen(['sleep','1']))
except OSError:
    pass
print(json.dumps({'children':len(children)}))
for child in children:
    child.wait()
'''
    result = runner.run("python:3.12-slim", tmp_path, ["python", "-c", script])
    assert result.exit_code == 0, result.stderr
    assert 1 <= json.loads(result.stdout)["children"] < 32


def test_source_analyzer_does_not_import_modules(runner, tmp_path):
    (tmp_path / "module.py").write_text("raise RuntimeError('not an import')\n\ndef f(a=1):\n    return a\n")
    from backend.core.analyzer import analyze
    data = analyze(runner, tmp_path)
    assert data["python"][:2] == [2, 7]
    assert data["order"][0]["functions"] == [{"name": "f", "args": ["a"], "defaults": 1}]
