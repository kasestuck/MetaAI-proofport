"""Two explicit paid demo scopes; reuse P8 CLI verification, never generic live jobs.

Configuration and key stay on disk. Metadata is local; the optional model catalog
check is a GET, never inference. A local operator gate AND an expiring one-use UI
consent are required. The normal RunStore slot also covers these runs.
"""
import asyncio
from hashlib import sha256
import json
import logging
from pathlib import Path
import secrets
import subprocess
import threading
from time import monotonic

from dotenv import dotenv_values
import httpx

from backend.ai import first_live, first_php_live
from backend.core.control_models import ControlError, RunSpec
from backend.core.models import Error, Module
from backend.core.projects import linked
from backend.core.runs import hashes_for
from backend.llm.client import LLMClient, ModelUnavailable
from backend.sandbox.runner import DockerRunner

PROFILES = {
    "python_mathutils": {"language":"python", "project_id":"legacy_shop", "source":"samples/legacy_shop",
        "file":"legacy_shop/mathutils.py", "source_version":"2.7", "target_version":"3.12", "cases":31, "tests":3,
        "images":("python:2.7", "python:3.12-slim")},
    "php_legacy": {"language":"php", "project_id":"php_shop", "source":"tests/fixtures/php_shop",
        "file":"src/legacy.php", "source_version":"7.4", "target_version":"8.3", "cases":22, "tests":9,
        "images":("php:7.4.33-cli", "php:8.3.36-cli")},
}
LIMITS = first_live.P82_LIMITS
PUBLIC_LIMITS = first_live.public_limits(LIMITS)
MESSAGES = {
    "key_required":"Enter a new key privately in backend/.tmp/meta-demo.env; never in the browser.",
    "revoked_key":"The retired smoke key cannot be used. Configure a new key.",
    "configuration_invalid":"Use the documented isolated demo configuration; no request was sent.",
    "operator_approval_required":"Separate owner permission is required before enabling LIVE_DEMO_APPROVED.",
    "model_check_required":"Check model access using the catalog GET before approving a paid run.",
    "model_authentication_failed":"Model catalog rejected the key (401/403); configure a new authorized key.",
    "model_unavailable":"The requested model was not found in the returned catalog.",
    "model_check_failed":"Catalog unavailable or invalid; no generation or automatic retry occurred.",
}


def blocked(code, status=409):
    raise ControlError(code, MESSAGES.get(code, "Live demo prerequisites changed; refresh readiness."), status)


class LiveDemo:
    def __init__(self, root, control):
        self.root, self.control, self.store = Path(root), control, control.store
        control.live_demo = self
        self.env_file = self.root / "backend/.tmp/meta-demo.env"
        self.probe = None
        self.tickets, self.idempotency = {}, {}
        self.lock = threading.Lock()
        self.client_factory = LLMClient
        self.catalog_client = httpx.Client
        self.store.live_demo_worker = self.worker

    def configuration(self):
        path = self.env_file
        if not path.is_file(): blocked("key_required", 503)
        if path.stat().st_size > 16384 or any(linked(p) for p in (path, *path.parents)):
            blocked("configuration_invalid", 503)
        data = dotenv_values(path)
        key = data.get("MODEL_API_KEY", "") or ""
        if not key.strip(): blocked("key_required", 503)
        if len(key)>4096 or any(not 33<=ord(c)<=126 for c in key): blocked("configuration_invalid",503)
        old_path = self.root / "backend/.tmp/meta-smoke.env"
        if old_path.is_file() and not linked(old_path):
            retired = dotenv_values(old_path).get("MODEL_API_KEY")
            if retired and secrets.compare_digest(key.encode(), retired.encode()): blocked("revoked_key", 503)
        required = {"LLM_MODE":"live", "MODEL_NAME":"muse-spark-1.3", "MODEL_BASE_URL":"https://api.meta.ai/v1",
            "PRICE_IN_PER_MTOK":"1.25", "PRICE_OUT_PER_MTOK":"4.25", "LIVE_DEMO_KEY_CONFIRMED_NEW":"true"}
        if any(data.get(k) != v for k,v in required.items()): blocked("configuration_invalid", 503)
        # This reads ignored-file/Git bytes only; it does not construct an SDK.
        from backend.llm.smoke import credential_git_check
        try: credential_git_check(self.root, path, key)
        except (OSError,subprocess.SubprocessError,ModelUnavailable): blocked("configuration_invalid",503)
        return data, sha256(path.read_bytes()).hexdigest()

    def checked_configuration(self):
        data, binding = self.configuration()
        if data.get("LIVE_DEMO_APPROVED") != "true": blocked("operator_approval_required", 403)
        if not self.probe or self.probe["binding"] != binding or self.probe["expires"] < monotonic():
            blocked("model_check_required", 503)
        if self.probe["status"] != "available": blocked(self.probe["status"], 503)
        return data, binding

    def snapshot(self):
        error = None
        model_status = "not_verified"
        try:
            _, current = self.configuration()
            if self.probe and self.probe["binding"] == current and self.probe["expires"] > monotonic():
                model_status = self.probe["status"]
            _, binding = self.checked_configuration()
        except ControlError as exc:
            binding, error = None, {"code":exc.code, "message":exc.message}
        except (OSError, ValueError, ModelUnavailable):
            binding, error = None, {"code":"configuration_invalid", "message":MESSAGES["configuration_invalid"]}
        profiles = []
        for name,p in PROFILES.items():
            readiness = {"can_start":False,"error":error}
            if error is None:
                try:
                    self.prepare(name)
                    readiness = {"can_start":True,"error":None}
                except ControlError as exc:
                    readiness = {"can_start":False,"error":{"code":exc.code,"message":exc.message}}
                except (OSError,ValueError,RuntimeError):
                    readiness = {"can_start":False,"error":{"code":"runtime_unavailable","message":"Required project/runtime cannot be verified."}}
            profiles.append({"id":name,**{k:v for k,v in p.items() if k not in {"source","images"}},"readiness":readiness})
        active_id = self.store.active
        active_id = active_id if active_id and self.store.get(active_id).spec.pipeline == "live_demo" else None
        with self.lock:
            last = next(reversed(self.idempotency.values()),None)
        return {"instance_id":self.control.instance_id, "enabled":error is None, "error":error,
            "model":"muse-spark-1.3", "model_status":model_status,
            "active_run_id":active_id,"last_run_id":last[1] if last else None,
            "limits":PUBLIC_LIMITS, "max_reserved_cost_usd":"0.049152",
            "profiles":profiles,
            "notice":"Only the two fixed module demos. Offline/replay are separate. No key is sent to this browser."}

    def check_model(self):
        data, binding = self.configuration()
        names={"httpx","httpcore"}
        names.update(name for name in list(logging.Logger.manager.loggerDict) if name.startswith(("httpx.","httpcore.")))
        if any(logging.getLogger(name).isEnabledFor(logging.DEBUG) for name in names):
            blocked("configuration_invalid", 503)
        status = "model_check_failed"
        try:
            with self.catalog_client(timeout=10, follow_redirects=False, trust_env=False) as client:
                # Only this fixed GET can be used. Never completions or redirects.
                with client.stream("GET", "https://api.meta.ai/v1/models", headers={"Authorization":"Bearer "+data["MODEL_API_KEY"]}) as response:
                    if response.status_code in {401,403}: status = "model_authentication_failed"
                    elif response.status_code == 200:
                        chunks = bytearray()
                        for chunk in response.iter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > 262144: raise ValueError("Catalog size bound")
                        catalog = json.loads(chunks)
                        rows = catalog.get("data") if isinstance(catalog,dict) else None
                        if not isinstance(rows,list) or any(not isinstance(r,dict) or not isinstance(r.get("id"),str) for r in rows):
                            raise ValueError("Catalog schema")
                        status = "available" if any(r["id"] == "muse-spark-1.3" for r in rows) else "model_unavailable"
        except (httpx.HTTPError, ValueError, OSError): pass
        self.probe = {"binding":binding,"expires":monotonic()+300,"status":status}
        return {"status":status, "model":"muse-spark-1.3", "generation_calls":0,
            "notice":"Catalog access only; generation and future availability are not guaranteed.",
            "error":None if status == "available" else {"code":status,"message":MESSAGES[status]}}

    def prepare(self, profile):
        if profile not in PROFILES: raise ControlError("unsupported_demo", "Select one of the two fixed demo profiles.")
        _, binding = self.checked_configuration()
        p = PROFILES[profile]
        if self.store.active is not None: raise ControlError("run_busy", "Another run is in progress.", 409)
        source = self.control.projects.get(p["project_id"], inventory_only=True)
        if source.resolve() != (self.root / p["source"]).resolve(): blocked("configuration_invalid", 503)
        if not (source / p["file"]).is_file(): blocked("configuration_invalid",503)
        runner = DockerRunner()
        if not runner.available(): raise ControlError("docker_unavailable", "Docker Linux execution is required.", 503)
        try: pins = tuple((tag,runner.image_id(tag)) for tag in p["images"])
        except RuntimeError:
            raise ControlError("runtime_unavailable","Required local runtime image is missing; no image was pulled.",503) from None
        spec = RunSpec("migration",p["project_id"],str(source),p["source_version"],p["target_version"],"live","live_demo",2,
            "behavior",settings=(("demo_profile",profile),("demo_file",p["file"]),("private_binding",binding),("cases_binding",self.cases_binding(profile))), images=pins,
            source_hashes=tuple(sorted(hashes_for(source).items())),language=p["language"])
        return spec

    def cases_binding(self,profile):
        file = "tests/fixtures/legacy_shop/cases.json" if profile == "python_mathutils" else "tests/fixtures/php_profiles/cases.json"
        path = self.root/file
        if not path.is_file() or any(linked(p) for p in (path,*path.parents)) or path.stat().st_nlink != 1:
            blocked("configuration_invalid",503)
        return first_live.digest(path)

    def confirm(self, profile, consent):
        if consent is not True: raise ControlError("paid_consent_required", "Explicit consent to two calls / $0.05 is required.")
        spec = self.prepare(profile)
        with self.lock:
            self.tickets = {k:v for k,v in self.tickets.items() if v[1] > monotonic()}
            if len(self.tickets) >= 100: raise ControlError("approval_limit", "Too many pending approvals.", 429)
            token = secrets.token_urlsafe(32)
            self.tickets[token] = (spec,monotonic()+120)
        return {"approval_id":token,"expires_in_seconds":120,"limits":PUBLIC_LIMITS,"instance_id":self.control.instance_id}

    async def start(self, profile, approval, key):
        digest = sha256(json.dumps([profile,approval]).encode()).hexdigest()
        with self.lock:
            if key in self.idempotency:
                old,run_id = self.idempotency[key]
                if old != digest: raise ControlError("idempotency_conflict", "Submission key belongs to a different paid request.", 409)
                return run_id
        fresh = await asyncio.to_thread(self.prepare, profile)
        with self.lock:
            if key in self.idempotency:
                old,run_id = self.idempotency[key]
                if old != digest: raise ControlError("idempotency_conflict", "Submission key belongs to a different paid request.", 409)
                return run_id
            ticket = self.tickets.get(approval)
            if not ticket or ticket[1] < monotonic() or ticket[0] != fresh:
                raise ControlError("paid_approval_invalid", "Approval expired, consumed, or configuration/source/image changed.", 409)
            run_id = self.store.start(fresh.source_path,2,spec=fresh)
            del self.tickets[approval]
            self.idempotency[key] = digest,run_id
        return run_id

    async def worker(self, run_id):
        run = self.store.get(run_id)
        run.runner = self.store._runner(run)
        worker = asyncio.create_task(asyncio.to_thread(self.execute,run_id))
        try: await asyncio.shield(worker)
        except asyncio.CancelledError:
            await asyncio.to_thread(run.runner.cancel)
            await worker
            raise
        except ModelUnavailable as exc:
            self.store._fail(run,exc.code,"Live model prerequisites or response failed; no success or fallback is claimed.")

    def execute(self, run_id):
        run = self.store.get(run_id)
        settings = dict(run.spec.settings); profile = settings["demo_profile"]; p = PROFILES[profile]
        engine = first_live if p["language"] == "python" else first_php_live
        if engine.SOURCE.resolve() != run.source.resolve(): blocked("configuration_invalid",503)
        run.workspace = self.root / "backend/.work" / ("live-demo-api-"+run_id)
        run.workspace.mkdir(parents=True,exist_ok=False)
        run.evidence.bind(run.workspace / "evidence.log")
        run.state.status, run.state.isolation = "running","docker"
        run.execution_mode = "live"
        run.state.modules = [Module(name=p["file"],tests_total=0)]
        run.verification.update(language=p["language"],mode="live",model="muse-spark-1.3",model_calls=0,ai_migration=False,
            live_demo={"profile":profile,"scope":p["file"],"limits":PUBLIC_LIMITS,"model_status":"catalog_available",
                       "security_scanned":False,"billing_unknown":False},comparisons=[],limitations=[
                "Only the fixed module and its declared test scope; no full-project live/security certification.",
                "Finite golden behavior; estimated cost is not a provider billing guarantee."])

        def progress(stage,data):
            if stage in {"translating","fixing"}:
                try:
                    _, current = self.checked_configuration()
                    if current != settings["private_binding"] or self.cases_binding(profile) != settings["cases_binding"]:
                        blocked("configuration_invalid",503)
                except ControlError as exc:
                    raise ModelUnavailable(exc.message,exc.code) from None
                run.verification["live_demo"]["model_status"]="requesting"
            run.state.phase = "migrating" if stage in {"translating","fixing"} else "testing" if stage == "verified_iteration" else stage
            if stage in {"translating","fixing","testing"}: run.state.modules[0].status = stage
            run.state.modules[0].iterations = data.get("iteration",run.state.modules[0].iterations)
            if "usage" in data:
                run.verification["live_demo"]["model_status"]="response_received"
                run.verification["usage"] = data["usage"]; run.verification["model_calls"] = data["model_calls"]
                for field in ("tokens_in","tokens_out","cost_usd"):
                    setattr(run.state.metrics,field,sum(u[field] for u in data["usage"]))
            if "golden_total" in data:
                run.verification["live_demo"].update({k:data[k] for k in ("golden_matched","golden_total","tests_passed","tests_total")})
                run.state.metrics.tests_passed=data["golden_matched"]+data["tests_passed"]
                run.state.metrics.tests_total=data["golden_total"]+data["tests_total"]
                run.state.modules[0].tests_passed=run.state.metrics.tests_passed
                run.state.modules[0].tests_total=run.state.metrics.tests_total
            run.evidence.append("live_demo_"+stage,json.dumps({"stage":stage,**data},sort_keys=True))
        self.checked_configuration()
        options = {"profile":"p8.2"} if p["language"] == "python" else {}
        baseline, workspace = engine.prepare(self.env_file,runner=run.runner,progress=progress,isolate_settings=True,**options)
        count = baseline.get("golden_cases") if p["language"] == "python" else baseline.get("golden_case_count")
        tests_count = baseline.get("source_tests") if p["language"] == "python" else baseline.get("source_tests",{}).get("tests_run")
        if count != p["cases"] or tests_count != p["tests"]:
            raise ModelUnavailable("Baseline scope changed; no model request sent.","baseline_scope_changed")
        progress("baseline_verified",{})
        run.verification["live_demo"]["baseline_golden_cases"] = p["cases"]
        client = self.client_factory(self.env_file,mode="live",allow_live=True,limits=LIMITS,inherit_environment=False)
        raw = engine.execute(workspace,self.env_file,acknowledged=True,runner=run.runner,client=client,
            progress=progress,isolate_settings=True,**options)
        # Original CLI report/receipts stay in a separate retained directory.
        last = raw.get("iterations",[])[-1] if raw.get("iterations") else {}
        checks = last.get("checks",{}) if p["language"] == "php" else last
        golden = checks.get("golden",{}) if p["language"] == "php" else {}
        comparisons = golden.get("comparisons",[]) if p["language"] == "php" else checks.get("comparisons",[])
        tests = checks.get("existing_tests",{}) if p["language"] == "php" else checks.get("target_tests",{})
        syntax = checks.get("syntax",{}).get("passed") if p["language"] == "php" else checks.get("syntax_passed")
        good = (syntax is True and raw.get("status") == "done" and raw.get("ai_migration") is True and raw.get("originals_unchanged") is True
            and raw.get("chain_intact") is True and len(comparisons) == p["cases"] and all(c["matches"] is True for c in comparisons)
            and tests.get("tests_run") == p["tests"] and first_live.suite_passed(tests,raw["source_tests"]))
        run.verification.update(ai_migration=good,model_calls=raw["model_calls"],usage=raw["usage"],model_attempts=raw["model_attempts"],
            comparisons=comparisons,source_tests=raw["source_tests"],target_tests=tests,rollback=raw.get("rollback",False),
            target_compiles=syntax,syntax_passed=syntax,tests_passed=first_live.suite_passed(tests,raw["source_tests"]) if tests.get("tests_run") else None,
            behavior_verified=all(c["matches"] for c in comparisons) if comparisons else None,
            source_version=p["source_version"],target_version=p["target_version"])
        run.verification["live_demo"].update(model_status="response_received" if raw["usage"] else "no_confirmed_response",
            golden_matched=sum(c["matches"] for c in comparisons),golden_total=len(comparisons),
            billing_unknown=any(not a["usage_known"] for a in raw["model_attempts"]),
            raw_artifact_id=workspace.name,raw_report_sha256=first_live.digest(workspace / "report.json"))
        for field in ("tokens_in","tokens_out","cost_usd"):
            setattr(run.state.metrics,field,sum(u[field] for u in raw["usage"]))
        run.state.metrics.tests_total = len(comparisons)+tests.get("tests_run",0)
        run.state.metrics.tests_passed = sum(c["matches"] for c in comparisons)+sum(o["status"]=="passed" for o in tests.get("outcomes",[]))
        run.state.modules[0].tests_total=run.state.metrics.tests_total
        run.state.modules[0].tests_passed=run.state.metrics.tests_passed
        if good:
            run.state.metrics.lines_migrated=len((workspace/"candidate"/p["file"]).read_text(encoding="utf-8").splitlines())
        run.state.modules[0].status="green" if good else "failed"
        run.pending_status="done" if good else "failed"
        if not good: run.state.error=Error(code=raw.get("error",{}).get("code","live_verification_failed"),message="Live demo failed verification; no successful migration is claimed. Inspect retained evidence.")
        run.evidence.append("live_demo_verified",json.dumps(run.verification["live_demo"],sort_keys=True))
