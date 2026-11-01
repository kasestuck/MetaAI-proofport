"""P8: prepare one real module baseline; paid execution needs separate consent.

No HTTP endpoint enables this command. Samples and model candidates execute only
in the existing DockerRunner. No fixture translator or security fixes are used.
"""

import argparse
import ast
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from dotenv import dotenv_values

from backend.ai.provider import ModelSession, ModuleLiveApproval, StructuredTranslator
from backend.ai.feedback import repair_feedback
from backend.core.analyzer import analyze
from backend.core.comparator import compare_cases
from backend.core.evidence import Evidence, entry_hash
from backend.core.projects import linked
from backend.core.recorder import invoke, load_cases
from backend.languages.base import inventory, hashes
from backend.llm.budget import LLMLimits
from backend.llm.client import LLMClient, ModelUnavailable
from backend.llm.smoke import credential_git_check
from backend.sandbox.runner import DockerRunner, SandboxError


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "samples/legacy_shop"
FILE = "legacy_shop/mathutils.py"
LIMITS = LLMLimits(max_calls=3, max_input_tokens=7936, max_output_tokens=1536,
                   max_total_tokens=28416, max_cost_usd=Decimal("0.05"), timeout_seconds=30)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, data):
    # Exclusive writes prevent an accidental paid restart overwriting evidence.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, ensure_ascii=True, indent=2)


def project_hashes(source=None):
    root, files = inventory(source if source is not None else SOURCE)
    return hashes(root, files)


def local_settings(env_file):
    settings = {**dotenv_values(env_file), **os.environ}
    expected = {"LLM_MODE":"live", "MODEL_NAME":"muse-spark-1.3",
                "MODEL_BASE_URL":"https://api.meta.ai/v1",
                "PRICE_IN_PER_MTOK":"1.25", "PRICE_OUT_PER_MTOK":"4.25"}
    if any(settings.get(k) != v for k, v in expected.items()) or not settings.get("MODEL_API_KEY", "").strip():
        raise ModelUnavailable("Use the separately smoke-tested private Meta configuration; no request sent.", "invalid_configuration")
    credential_git_check(ROOT, env_file, settings["MODEL_API_KEY"])
    return settings


def assert_originals(before):
    if project_hashes() != before:
        raise ModelUnavailable("Original project hashes changed; no success may be claimed.", "source_changed")


def suite_passed(observed, baseline=None):
    outcomes = observed.get("outcomes", [])
    ids = {o["id"] for o in outcomes}
    if not outcomes or observed["tests_run"] != len(outcomes) or len(ids) != len(outcomes):
        return False
    return (all(o["status"] == "passed" for o in outcomes)
            and (baseline is None or ids == {o["id"] for o in baseline["outcomes"]}))


def scoped_tests(text):
    """Extract the existing MathTests verbatim, without evaluating sample code."""
    tree = ast.parse(text)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MathTests"]
    if len(classes) != 1 or classes[0].decorator_list:
        raise ValueError("Expected one undecorated existing MathTests class")
    node = classes[0]
    body = "".join(text.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    return "import unittest\nfrom legacy_shop import mathutils\n\n" + body + "\n", body


def prepare(env_file, *, runner=None):
    settings = local_settings(env_file)
    before = project_hashes()
    if any(settings["MODEL_API_KEY"].encode() in p.read_bytes() for p in inventory(SOURCE)[1]):
        raise ModelUnavailable("Credential found in project; no model request sent.", "credential_in_prompt")
    runner = runner or DockerRunner()
    if not runner.available():
        raise SandboxError("Docker unavailable; no host execution permitted")
    for image in ("python:2.7", "python:3.12-slim"):
        runner.image_id(image)
    workspace = ROOT / "backend/.work" / ("p8-mathutils-" + uuid4().hex)
    if any(linked(p) for p in (workspace, *workspace.parents)):
        raise ValueError("Link-free workspace required")
    original = workspace / "original"
    (original / "legacy_shop").mkdir(parents=True)
    (original / "tests").mkdir()
    for file in (FILE, "legacy_shop/__init__.py", "tests/__init__.py"):
        shutil.copyfile(SOURCE / file, original / file)
    test_file = SOURCE / "tests/test_legacy_shop.py"
    projected, body = scoped_tests(test_file.read_text(encoding="utf-8"))
    (original / "tests/test_legacy_shop.py").write_text(projected, encoding="utf-8")
    cases = [c for c in load_cases(ROOT / "tests/fixtures/legacy_shop/cases.json") if c["module"] == "legacy_shop.mathutils"]
    if not cases:
        raise ValueError("Missing real golden inputs")
    evidence = Evidence()
    evidence.bind(workspace / "preparation.log")
    evidence.append("scope", "Single module mathutils; existing MathTests class copied verbatim; imports narrowed. Full project suite NOT run.")
    analysis = analyze(runner, original)
    golden = invoke(runner, "python:2.7", original, "cases", cases, evidence)
    tests = invoke(runner, "python:2.7", original, "tests", evidence=evidence)
    if not suite_passed(tests) or tests["tests_run"] != 3:
        raise ValueError("Existing scoped source tests did not all pass")
    target_baseline = invoke(runner, "python:3.12-slim", original, "compile", evidence=evidence)
    assert_originals(before)
    write(workspace / "cases.json", {"cases":cases})
    write(workspace / "golden.json", golden)
    write(workspace / "source_tests.json", tests)
    write(workspace / "analysis.json", analysis)
    write(workspace / "target_baseline.json", target_baseline)
    scoped = hashes(original, inventory(original)[1])
    artifacts = {p.name:digest(p) for p in workspace.iterdir() if p.is_file()}
    manifest = {"status":"awaiting_paid_approval", "file":FILE, "model":settings["MODEL_NAME"],
        "source_hashes":before, "scoped_hashes":scoped, "artifacts":artifacts,
        "source_sha256":sha256((original / FILE).read_text(encoding="utf-8").encode()).hexdigest(),
        "test_projection":{"original_sha256":digest(test_file), "class_sha256":sha256(body.encode()).hexdigest(),
                           "class":"MathTests", "tests":3, "full_project_suite":False},
        "images":dict(runner._images), "source_python":golden["python"],
        "golden_cases":len(cases), "source_tests":tests["tests_run"], "chain_intact":evidence.verify(),
        "limits":{**asdict(LIMITS), "max_cost_usd":str(LIMITS.max_cost_usd)},
        "max_reserved_cost_usd":"0.049344", "paid_requests":0}
    write(workspace / "prepared.json", manifest)
    return manifest, workspace


def validate_prepared(workspace, runner):
    workspace = Path(workspace).absolute()
    parent = ROOT / "backend/.work"
    if (workspace.parent != parent or not workspace.name.startswith("p8-mathutils-")
            or any(linked(p) for p in (workspace, *workspace.parents))):
        raise ValueError("Expected a retained P8 preparation workspace")
    manifest = json.loads((workspace / "prepared.json").read_text(encoding="utf-8"))
    if manifest["file"] != FILE or manifest["model"] != "muse-spark-1.3" or not manifest["chain_intact"]:
        raise ValueError("Invalid preparation binding")
    assert_originals(manifest["source_hashes"])
    original = workspace / "original"
    if hashes(original, inventory(original)[1]) != manifest["scoped_hashes"]:
        raise ValueError("Scoped source or existing tests changed")
    projected, body = scoped_tests((SOURCE / "tests/test_legacy_shop.py").read_text(encoding="utf-8"))
    expected_files = {FILE, "legacy_shop/__init__.py", "tests/__init__.py", "tests/test_legacy_shop.py"}
    if set(manifest["scoped_hashes"]) != expected_files:
        raise ValueError("Unexpected scoped project files")
    if any((original / p).read_bytes() != (SOURCE / p).read_bytes() for p in expected_files - {"tests/test_legacy_shop.py"}):
        raise ValueError("Prepared sources differ from actual original bytes")
    if (original / "tests/test_legacy_shop.py").read_text(encoding="utf-8") != projected:
        raise ValueError("Existing test class was changed")
    if sha256((original / FILE).read_text(encoding="utf-8").encode()).hexdigest() != manifest["source_sha256"]:
        raise ValueError("Prepared source binding changed")
    expected_cases = [c for c in load_cases(ROOT / "tests/fixtures/legacy_shop/cases.json") if c["module"] == "legacy_shop.mathutils"]
    if load_cases(workspace / "cases.json") != expected_cases:
        raise ValueError("Golden case inputs changed")
    if set(manifest["artifacts"]) != {"cases.json", "golden.json", "source_tests.json", "analysis.json", "preparation.log", "target_baseline.json"}:
        raise ValueError("Preparation artifact list changed")
    for name, expected in manifest["artifacts"].items():
        if digest(workspace / name) != expected:
            raise ValueError("Preparation artifacts changed")
    if not runner.available():
        raise SandboxError("Docker unavailable; no model request sent")
    for image, expected in manifest["images"].items():
        if image not in {"python:2.7", "python:3.12-slim"} or runner.image_id(image) != expected:
            raise ValueError("Prepared Docker images changed")
    if set(manifest["images"]) != {"python:2.7", "python:3.12-slim"}:
        raise ValueError("Missing prepared runtime image")
    return manifest


def verify_candidate(runner, candidate, cases, golden, baseline, evidence):
    syntax = invoke(runner, "python:3.12-slim", candidate, "compile", evidence=evidence)
    result = {"syntax_passed":not syntax["errors"], "syntax":syntax,
              "tests_passed":None, "behavior_verified":None}
    if syntax["errors"]:
        return result
    observed = invoke(runner, "python:3.12-slim", candidate, "cases", cases, evidence)
    tests = invoke(runner, "python:3.12-slim", candidate, "tests", evidence=evidence)
    comparisons = compare_cases(golden["cases"], observed["cases"])
    result.update(tests_passed=suite_passed(tests, baseline),
                  behavior_verified=bool(comparisons) and all(c["matches"] for c in comparisons),
                  comparisons=comparisons, target_tests=tests, target_python=observed["python"], observed=observed)
    return result


def execute(workspace, env_file, *, acknowledged=False, runner=None, client=None):
    if acknowledged is not True:
        raise ModelUnavailable("Separate permission and explicit paid acknowledgment required.", "approval_required")
    settings = local_settings(env_file)
    runner = runner or DockerRunner()
    manifest = validate_prepared(workspace, runner)
    workspace = Path(workspace).absolute()
    # Created exclusively BEFORE constructing a client. A second invocation is
    # forbidden even after a timeout/process crash; paid continuation needs review.
    write(workspace / "execution_started.json", {"prepared_sha256":digest(workspace / "prepared.json"),
        "scope":FILE, "max_calls":3, "max_cost_usd":"0.05", "mode":"live"})
    evidence = Evidence()
    evidence.bind(workspace / "evidence.log")
    evidence.append("prepared_baseline", json.dumps({"manifest_sha256":digest(workspace / "prepared.json"),
                    "preparation_log_sha256":digest(workspace / "preparation.log")}, sort_keys=True))
    original = workspace / "original"
    candidate = workspace / "candidate"
    shutil.copytree(original, candidate)
    source = (original / FILE).read_text(encoding="utf-8")
    cases = load_cases(workspace / "cases.json")
    golden = json.loads((workspace / "golden.json").read_text())
    baseline = json.loads((workspace / "source_tests.json").read_text())
    client = client or LLMClient(env_file, mode="live", allow_live=True, limits=LIMITS)
    session = None
    report = {"status":"failed", "file":FILE, "mode":"live", "provider_validated":False,
              "ai_migration":False, "iterations":[], "original_hashes":manifest["source_hashes"],
              "source_python":manifest["source_python"], "images":manifest["images"], "golden_cases":len(cases),
              "source_tests":baseline, "test_projection":manifest["test_projection"],
              "isolation":"docker: network none; readonly mounts/root; non-root; 1 CPU; 256MiB; 32 PIDs",
              "limitations":["Only mathutils and the unchanged MathTests class were exercised; full legacy_shop suite NOT run.",
                             "Finite cases are evidence for those inputs, not a proof for every possible input.",
                             "No security fix or full security audit is included.",
                             "Costs are estimated from reported usage; the client cap is not a provider billing guarantee."]}
    try:
        if (client.mode != "live" or client.limits != LIMITS or client.model != settings["MODEL_NAME"]
                or client.base_url != settings["MODEL_BASE_URL"] or client._api_key != settings["MODEL_API_KEY"]
                or client._price_in != Decimal("1.25") or client._price_out != Decimal("4.25")):
            raise ModelUnavailable("Unexpected client/limits; no live fallback.", "live_not_authorized")
        session = ModelSession(client, "python", evidence=evidence,
            live_approval=ModuleLiveApproval(FILE, manifest["source_sha256"]), response_dir=workspace, case_feedback=True)
        translator = StructuredTranslator(session)
        previous = feedback = None
        for iteration in range(1, 4):
            assert_originals(manifest["source_hashes"])
            code = translator.translate(FILE, source, previous=previous, failures=feedback)
            (candidate / FILE).write_text(code, encoding="utf-8")
            saved = workspace / ("iteration_%02d" % iteration)
            shutil.copytree(candidate, saved)
            checks = verify_candidate(runner, candidate, cases, golden, baseline, evidence)
            record = {"iteration":iteration, "candidate":saved.name, **checks}
            write(workspace / ("verification_%02d.json" % iteration), record)
            evidence.append("candidate_verified", json.dumps({"iteration":iteration,
                **{k:checks[k] for k in ("syntax_passed", "tests_passed", "behavior_verified")},
                "verification_sha256":digest(workspace / ("verification_%02d.json" % iteration))}, sort_keys=True))
            report["iterations"].append(record)
            assert_originals(manifest["source_hashes"])
            # The model cannot change tests, initializers or any other baseline file.
            if any(digest(candidate / p) != value for p,value in manifest["scoped_hashes"].items() if p != FILE):
                raise ValueError("Non-target scoped files changed")
            if all(checks[k] is True for k in ("syntax_passed", "tests_passed", "behavior_verified")):
                report.update(status="done", ai_migration=True, accepted_copy="candidate")
                break
            # Only locally verified failures permit another paid call within the
            # explicitly approved batch. Transport/JSON/budget failures stop.
            previous = code
            feedback = repair_feedback(checks, cases)
        if report["status"] != "done":
            report["error"] = {"code":"verification_failed"}
    except (ModelUnavailable, SandboxError, ValueError, OSError):
        # Never serialize exception/provider bodies or private configuration.
        import sys
        exc = sys.exception()
        report["error"] = {"code":getattr(exc, "code", "local_verification_error")}
    finally:
        client.close()
    report.update(model=client.model, model_calls=len(client.attempts), usage=[asdict(c) for c in client.calls],
                  model_attempts=[asdict(a) for a in client.attempts],
                  budget=client.budget_snapshot(), responses=session.responses if session else [],
                  provider_validated=bool(client.calls), ai_fix_loop_used=len(client.attempts)>1,
                  originals_unchanged=project_hashes() == manifest["source_hashes"])
    report["chain_intact"] = evidence.verify()
    if not report["originals_unchanged"] or not report["chain_intact"]:
        report.update(status="failed", ai_migration=False, error={"code":"integrity_failed"})
    if report["status"] != "done":
        candidate.rename(workspace / "rejected_final")
        shutil.copytree(original, candidate)
        report.pop("accepted_copy", None)
        report.update(ai_migration=False, rollback=True)
        if report["chain_intact"]:
            evidence.append("rollback", "Rejected candidates retained; candidate restored to scoped original.")
    artifact_hashes = {p.relative_to(workspace).as_posix():digest(p) for p in workspace.rglob("*") if p.is_file()}
    report["artifact_hashes"] = artifact_hashes
    if evidence.verify():
        evidence.append("artifacts_sealed", json.dumps({k:v for k,v in artifact_hashes.items() if k != "evidence.log"}, sort_keys=True))
        report["artifact_hashes"]["evidence.log"] = digest(workspace / "evidence.log")
    report["events"] = evidence.since(0)
    report["chain_intact"] = report["chain_intact"] and evidence.verify()
    exported = session.private.clean(report) if session else report
    write(workspace / "report.json", exported)
    (workspace / "report.html").write_text('<!doctype html><meta charset="utf-8"><title>Proofport P8 Meta verification</title>'
        '<h1>Real Meta module verification</h1><pre>' + escape(json.dumps(exported, indent=2, sort_keys=True)) + '</pre>', encoding="utf-8")
    write(workspace / "report_receipt.json", {"report.json":digest(workspace / "report.json"),
                                             "report.html":digest(workspace / "report.html")})
    verify_export(workspace)
    return exported


def verify_export(workspace):
    """Check retained report/artifact bytes and the complete ordered evidence chain.

    Local hashes detect inconsistency, not a malicious rewrite of all receipts.
    """
    workspace = Path(workspace)
    receipt = json.loads((workspace / "report_receipt.json").read_text(encoding="utf-8"))
    if set(receipt) != {"report.json", "report.html"}:
        raise ValueError("Invalid report receipt")
    if any(digest(workspace / name) != value for name,value in receipt.items()):
        raise ValueError("Report bytes changed")
    report = json.loads((workspace / "report.json").read_text(encoding="utf-8"))
    for name, expected in report["artifact_hashes"].items():
        path = workspace / name
        if not path.resolve().is_relative_to(workspace.resolve()) or any(linked(p) for p in (path, *path.parents)):
            raise ValueError("Unsafe report artifact path")
        if digest(path) != expected:
            raise ValueError("Report artifact bytes changed")
    events = [json.loads(line) for line in (workspace / "evidence.log").read_text(encoding="utf-8").splitlines()]
    if events != report["events"]:
        raise ValueError("Report events differ from evidence log")
    previous = "0" * 64
    for seq, event in enumerate(events, 1):
        if event["seq"] != seq or event["prev_hash"] != previous or entry_hash(event) != event["entry_hash"]:
            raise ValueError("Evidence chain mismatch")
        previous = event["entry_hash"]
    expected_html = '<!doctype html><meta charset="utf-8"><title>Proofport P8 Meta verification</title>' + '<h1>Real Meta module verification</h1><pre>' + escape(json.dumps(report, indent=2, sort_keys=True)) + '</pre>'
    if (workspace / "report.html").read_text(encoding="utf-8") != expected_html:
        raise ValueError("HTML and JSON reports differ")
    assert_originals(report["original_hashes"])
    return True


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=Path, default=ROOT / "backend/.tmp/meta-smoke.env")
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--workspace", type=Path)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--acknowledge-paid-api", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.prepare and not any((args.execute, args.workspace, args.acknowledge_paid_api)):
            result, workspace = prepare(args.env_file)
            print(json.dumps({k:result[k] for k in ("status", "model", "golden_cases", "source_tests", "paid_requests", "max_reserved_cost_usd")}))
            print("Retained workspace: " + str(workspace))
            return 0
        if args.execute and args.acknowledge_paid_api and args.workspace and not args.prepare:
            result = execute(args.workspace, args.env_file, acknowledged=True)
            print(json.dumps({k:result.get(k) for k in ("status", "ai_migration", "model_calls", "budget", "originals_unchanged", "chain_intact", "error")}))
            return 0 if result["status"] == "done" else 2
        raise ModelUnavailable("Choose free --prepare, or a separately approved explicit execution.", "approval_required")
    except (ModelUnavailable, SandboxError, ValueError, OSError):
        import sys
        exc = sys.exception()
        print(json.dumps({"status":"blocked", "code":getattr(exc, "code", "local_preparation_error"),
                          "notice":"No fallback. Private details withheld; inspect local preparation."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
