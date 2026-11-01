"""Only fixed trusted harness commands in the existing Docker sandbox."""

import base64
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from backend.languages.base import AdapterError, hashes, inventory
from backend.languages.runtimes import IMAGE_ID, PHP_RUNTIMES, php_runtimes
from backend.php.protocol import relative_php
from backend.sandbox.runner import DockerRunner


def source_hashes(source):
    source, files = inventory(source)
    if any(p.name.lower() in {"auth.json", "composer-auth.json"} for p in files):
        raise AdapterError("php_credentials_require_review", "Prepare input without Composer credential files.", 403)
    if any(p.suffix == ".py" for p in files):
        raise AdapterError("language_mismatch", "PHP jobs require an explicitly PHP project; mixed execution is not enabled.")
    return hashes(source, files)


def local_images(runner=None):
    runner = runner or DockerRunner()
    ready = runner.available()
    if not ready: raise AdapterError("docker_unavailable", "PHP execution requires Linux Docker; host fallback is forbidden.", 503)
    states = php_runtimes(runner, docker=ready)
    if not all(r["available"] is True for r in states):
        raise AdapterError("runtime_unavailable", "Install only the explicitly approved PHP images; no automatic pull.", 503)
    return {r["version"]: r["image_id"] for r in states}


class PHPExecutor:
    def __init__(self, *, runner, images, evidence):
        self.runner, self.images, self.evidence = runner, dict(images), evidence
        if any(not IMAGE_ID.fullmatch(value) for value in self.images.values()):
            raise ValueError("Use pinned PHP image IDs.")

    def invoke(self, project, version, action, **payload):
        runtime = next((r for r in PHP_RUNTIMES if r.version == version), None)
        if runtime is None or version not in self.images or action not in {"version", "lint", "cases", "tests", "phpunit"}:
            raise AdapterError("unsupported_php_operation", "Unconfigured PHP harness operation/version.")
        result = self.runner.run(self.images[version], project, ["php", "-n", "-d", "auto_prepend_file=", "-d", "auto_append_file=",
                                                              "-d", "opcache.enable_cli=0", "/tools/php_harness.php"], {"action": action, **payload})
        self.evidence.append("sandbox_run", json.dumps({"language": "php", "action": action, **result.summary()}, sort_keys=True))
        if result.exit_code or result.timed_out or result.output_exceeded:
            raise AdapterError("php_harness_unavailable", "PHP harness did not complete; no results inferred.", 503)
        try: data = json.loads(result.stdout)
        except (ValueError, TypeError): raise AdapterError("php_protocol_invalid", "PHP harness returned invalid JSON.") from None
        patch = runtime.image.split(":", 1)[1].split("-", 1)[0]
        if not isinstance(data, dict) or data.get("protocol") != "proofport-php-1" or data.get("php") != patch or data.get("action") != action or "error" in data:
            raise AdapterError("php_runtime_mismatch", "PHP runtime identity/action/protocol is not confirmed.", 503)
        return data

    def lint(self, project, version):
        _, files = inventory(project)
        names = [p.relative_to(project).as_posix() for p in files if p.suffix == ".php"]
        if not names or len(names) > 64: raise AdapterError("php_lint_limit", "Use 1..64 PHP files for this bounded workflow.")
        for name in names: relative_php(name, tests=True)
        result = self.invoke(project, version, "lint", files=names)
        outcomes = result.get("files")
        if not isinstance(outcomes, list) or [o.get("file") for o in outcomes] != names or any(type(o.get("passed")) is not bool or o.get("exit_code") not in {0, 255} or o["passed"] != (o["exit_code"] == 0) for o in outcomes):
            raise AdapterError("php_protocol_invalid", "Incomplete or inconsistent lint results.")
        return {"ran": True, "passed": all(o["passed"] for o in outcomes), "files": outcomes, "php": result["php"]}

    def cases(self, project, version, profile):
        result = self.invoke(project, version, "cases", cases=profile["cases"])
        cases = result.get("cases")
        if not isinstance(cases, list) or [c.get("id") for c in cases] != [c["id"] for c in profile["cases"]]:
            raise AdapterError("php_protocol_invalid", "Golden recording is incomplete.")
        return cases

    def tests(self, project, version, *, test_runner="proofport"):
        if test_runner == "proofport":
            if not (project / "tests/proofport.php").is_file():
                raise AdapterError("tests_unavailable", "A nonempty local tests/proofport.php suite is required.")
            data = self.invoke(project, version, "tests")
        elif test_runner == "phpunit":
            config = next((p for p in ("phpunit.xml", "phpunit.xml.dist", "phpunit.dist.xml") if (project / p).is_file()), None)
            if not config or not (project / "vendor/phpunit/phpunit/phpunit").is_file() or not (project / "vendor/autoload.php").is_file():
                raise AdapterError("phpunit_unavailable", "Compatible local PHPUnit configuration/dependencies are required; no installation is performed.")
            raw = self.invoke(project, version, "phpunit", configuration=config)
            xml = base64.b64decode(raw.get("junit", ""), validate=True)
            if len(xml) > 524288 or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper(): raise ValueError("Unsafe PHPUnit XML")
            tree = ET.fromstring(xml)
            outcomes = [{"id": t.get("classname", "") + "." + t.get("name", ""),
                         "status": "failed" if any(c.tag in {"failure", "error", "skipped"} for c in t) else "passed"} for t in tree.iter("testcase")]
            if raw.get("exit_code") != 0 and all(t["status"] == "passed" for t in outcomes): raise ValueError("Inconsistent PHPUnit exit")
            data = {"php": raw["php"], "tests_run": len(outcomes), "outcomes": outcomes}
        else: raise ValueError("Unsupported local test runner")
        outcomes = data.get("outcomes")
        if not isinstance(outcomes, list) or not 1 <= len(outcomes) <= 128 or data.get("tests_run") != len(outcomes):
            raise AdapterError("tests_unavailable", "No complete nonempty PHP test suite was observed.")
        ids = [o.get("id") for o in outcomes]
        if any(not isinstance(i, str) or not i or len(i) > 512 for i in ids) or len(set(ids)) != len(ids) or any(o.get("status") not in {"passed", "failed"} for o in outcomes):
            raise AdapterError("php_protocol_invalid", "Invalid PHP test identities/statuses.")
        return {"tests_run": len(ids), "outcomes": outcomes, "passed": all(o["status"] == "passed" for o in outcomes), "php": data["php"], "runner": test_runner}
