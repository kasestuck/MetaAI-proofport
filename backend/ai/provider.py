"""LLMClient boundary shared by adapters. No public or implicit live activation."""

import base64
from dataclasses import asdict, dataclass
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re

from backend.ai.models import ModelPatch
from backend.ai.prompts import PYTHON, PYTHON_REPAIR, PHP, PHP_MODULE, PHP_REPAIR, SECURITY, SECURITY_EVAL, SECURITY_EVAL_PY27, BOUNDARY
from backend.llm.client import LLMClient, ModelUnavailable, _unique_json_keys, _invalid_json_constant
from backend.llm.budget import LLMLimits
from backend.llm.context import measure, compact_failures, previous_excerpt, schema_without_titles


def _validate_trial_limits(limits):
    if (not isinstance(limits, LLMLimits) or limits.max_calls > 2
            or limits.max_input_tokens > 9216 or limits.max_output_tokens > 3072
            or limits.max_total_tokens > 24576 or limits.timeout_seconds > 30
            or limits.max_cost_usd > Decimal("0.05")):
        raise ModelUnavailable("Trial approval exceeds the two-call budget.", "live_not_authorized")


@dataclass(frozen=True)
class ModuleLiveApproval:
    """Operator-approved P8 scope; never created by API settings or environment."""
    file: str
    source_sha256: str

    def validate(self, client, language):
        limits = client.limits
        if (language != "python" or self.file != "legacy_shop/mathutils.py"
                or not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256)
                or not isinstance(limits, LLMLimits) or limits.max_calls > 3
                or limits.max_cost_usd > Decimal("0.05")):
            raise ModelUnavailable("Live approval exceeds the first-module scope/budget.", "live_not_authorized")


@dataclass(frozen=True)
class PHPModuleLiveApproval:
    """Explicit future operator approval, bound to the one P8.3 PHP module."""
    file: str
    source_sha256: str

    def validate(self, client, language):
        if (language != "php" or self.file != "src/legacy.php"
                or not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256)):
            raise ModelUnavailable("PHP approval exceeds the single-module scope/budget.", "live_not_authorized")
        _validate_trial_limits(client.limits)


@dataclass(frozen=True)
class SecurityLiveApproval:
    """Future P8.4 approval for one eval finding; never permits migration."""
    file: str
    source_sha256: str
    finding_id: str
    runtime_version: str = "2.7"

    def validate(self, client, language):
        if (language != "python" or self.file != "legacy_shop/config.py" or self.runtime_version != "2.7"
                or not re.fullmatch(r"[a-f0-9]{64}", self.source_sha256)
                or not re.fullmatch(r"B307-[a-f0-9]{24}", self.finding_id)):
            raise ModelUnavailable("Security approval scope differs from P8.4.", "live_not_authorized")
        _validate_trial_limits(client.limits)


class PrivateContext:
    def __init__(self, credential=""):
        self.credential = credential
        self.values = {}

    def protect(self, source):
        if not isinstance(source, str) or not source or len(source.encode()) > 262144:
            raise ModelUnavailable("Source context is absent or too large.", "model_context_invalid")
        if self.credential and self.credential in source:
            raise ModelUnavailable("Model credential detected in project context; no request sent.", "credential_in_prompt")
        pattern = r'''(?i)\b\w*(?:password|secret|api_key|token)\w*\b[^\r\n=]{0,20}=\s*(['"])((?:\\.|(?!\1)[^\r\n])*?)\1'''
        for match in re.finditer(pattern, source):
            value = match.group(2)
            if value and len(value) < 8:
                raise ModelUnavailable("Ambiguous short private literal requires manual context preparation.", "needs_review")
            if value and value not in self.values:
                self.values[value] = "__PROOFPORT_PRIVATE_%d__" % (len(self.values) + 1)
        return self.clean(source, placeholders=True)

    def clean(self, value, *, placeholders=False):
        if isinstance(value, str):
            for secret, marker in sorted(self.values.items(), key=lambda item: -len(item[0])):
                for form in (secret, json.dumps(secret)[1:-1], base64.b64encode(secret.encode()).decode()):
                    value = value.replace(form, marker if placeholders else "[REDACTED]")
            if self.credential:
                for form in (self.credential, json.dumps(self.credential)[1:-1], base64.b64encode(self.credential.encode()).decode()):
                    value = value.replace(form, "[REDACTED]")
            return value
        if isinstance(value, list): return [self.clean(x, placeholders=placeholders) for x in value]
        if isinstance(value, dict): return {k:self.clean(v, placeholders=placeholders) for k,v in value.items()}
        return value

    def restore(self, code, original, task):
        known = set(self.values.values())
        if any(marker not in known for marker in re.findall(r"__PROOFPORT_PRIVATE_\w+__", code)):
            raise ModelUnavailable("Unknown private-context placeholder.", "model_response_invalid")
        for secret, marker in self.values.items():
            if task == "translate" and code.count(marker) != self.clean(original, placeholders=True).count(marker):
                raise ModelUnavailable("Translation changed private-context bindings; manual review required.", "model_response_invalid")
            count = code.count(marker)
            if len(code.encode()) + count * (len(secret.encode()) - len(marker.encode())) > 262144:
                raise ModelUnavailable("Restored candidate exceeds the bounded file size.", "model_response_invalid")
            code = code.replace(marker, secret)
        return code


class ModelSession:
    def __init__(self, client, language, *, evidence=None, live_approval=None, response_dir=None, case_feedback=False, compact_security=False):
        if not isinstance(client, LLMClient) or language not in {"python", "php"}:
            raise ModelUnavailable("Supply an explicit LLMClient and supported language.")
        # P8 adds an explicit single-module operator approval after the real
        # smoke. No environment variable or public API request creates it.
        if client.mode == "live" and isinstance(live_approval, (ModuleLiveApproval, PHPModuleLiveApproval, SecurityLiveApproval)):
            live_approval.validate(client, language)
        elif client.mode not in {"mock", "replay"} or live_approval is not None:
            raise ModelUnavailable("AI pipeline live execution remains disabled pending real smoke and separate authorization.", "live_disabled")
        if not isinstance(client.limits, LLMLimits):
            raise ModelUnavailable("AI orchestration requires a bounded per-run LLM client.", "budget_required")
        self.client, self.language, self.evidence = client, language, evidence
        self.mode = client.mode
        self.stopped = False
        self.private = PrivateContext(client._api_key)
        self.responses = []
        self.live_approval = live_approval
        self.response_dir = response_dir
        if type(case_feedback) is not bool or type(compact_security) is not bool:
            raise ModelUnavailable("Context controls need explicit boolean opt-ins.", "model_context_invalid")
        self.case_feedback = case_feedback
        self.compact_security = compact_security

    def request(self, task, file, source, *, previous=None, failures=None, finding=None):
        if self.stopped: raise ModelUnavailable("Model response session stopped; no automatic retry.", "model_session_stopped")
        if self.client.mode != self.mode or (self.mode == "live" and self.live_approval is None):
            raise ModelUnavailable("Live/session mode switch is not authorized.", "live_disabled")
        path = PurePosixPath(file)
        suffix = ".php" if self.language == "php" else ".py"
        if (not isinstance(file, str) or path.is_absolute() or "\\" in file or ":" in file
            or any(p in {"", ".", "..", "tests", "vendor"} or p.startswith(".") for p in file.split("/"))
            or path.name.startswith("test_") or path.suffix != suffix):
            raise ModelUnavailable("Model target must be a single application source file.", "model_target_invalid")
        if task not in {"translate", "security"} or (task == "security" and not finding):
            raise ModelUnavailable("Invalid model task binding.", "model_context_invalid")
        binding = {"task":task, "language":self.language, "file":file, "source_sha256":sha256(source.encode()).hexdigest(),
                   "finding_id":finding["id"] if finding else None}
        if self.mode == "live":
            self.live_approval.validate(self.client, self.language)
            security = isinstance(self.live_approval, SecurityLiveApproval)
            if (task != ("security" if security else "translate") or file != self.live_approval.file
                    or binding["source_sha256"] != self.live_approval.source_sha256
                    or security and binding["finding_id"] != self.live_approval.finding_id):
                raise ModelUnavailable("Request is outside the approved module binding.", "live_not_authorized")
        redacted = self.private.protect(source)
        context = {**binding, "source_version":"2.7" if self.language == "python" else "7.4", "target_version":"3.12" if self.language == "python" else "8.3",
                   "source":redacted, "previous": self.private.protect(previous) if previous else None,
                   "failures": self.private.clean(failures), "schema":ModelPatch.model_json_schema()}
        if isinstance(self.live_approval, SecurityLiveApproval):
            context["target_version"] = self.live_approval.runtime_version
        if task == 'security': context['source_version'] = context['target_version']
        if finding:
            context["finding"] = self.private.clean({k:finding[k] for k in ("id","file","line","scope","scanner_test","cwe","severity","confidence","description") if k in finding})
        detailed_repair = task == "translate" and previous is not None and self.case_feedback
        if task == "security":
            instructions = SECURITY
            if finding.get('scanner_test') == 'B307' and file == 'legacy_shop/config.py':
                instructions += SECURITY_EVAL
                if context['target_version'] == '2.7': instructions += SECURITY_EVAL_PY27
        elif self.language == "python": instructions = PYTHON_REPAIR if detailed_repair else PYTHON
        else: instructions = PHP_REPAIR if detailed_repair else PHP_MODULE if self.case_feedback else PHP
        system = instructions + "\n" + BOUNDARY
        if task == 'security' and previous and self.compact_security:
            context['schema'] = schema_without_titles(context['schema'])
            context['failures'] = self.private.clean(compact_failures(failures))
            rendered = json.dumps(context,sort_keys=True,ensure_ascii=True,separators=(',',':'))
            if not measure(system,rendered,self.client.limits.max_input_tokens)['within_allowance']:
                context['previous'] = None
                context['previous_excerpt'] = self.private.clean(previous_excerpt(previous,finding))
                context['context_reduction'] = 'Full original retained; previous candidate replaced by labelled diagnostic excerpts. Generate a complete file from original; do not splice excerpts.'
            rendered = json.dumps(context,sort_keys=True,ensure_ascii=True,separators=(',',':'))
            if self.evidence:
                self.evidence.append('model_context_budget',json.dumps({**measure(system,rendered,self.client.limits.max_input_tokens),
                    'reduction':context.get('context_reduction','compact_observations_full_previous')},sort_keys=True))
        else:
            rendered = json.dumps(context,sort_keys=True,ensure_ascii=True)
        count = len(self.client.attempts)
        try:
            text = self.client.complete(system, rendered, json_mode=True)
            if self.response_dir is not None:
                # Preserve returned content, including schema-invalid candidates,
                # only after credential/private-context redaction. Never execute it.
                record = {"mode":self.mode, "prompt_hash":self.client.attempts[-1].prompt_hash,
                          "response":self.private.clean(text), **binding}
                target = self.response_dir / ("response_%02d.json" % len(self.client.attempts))
                with target.open("x", encoding="utf-8") as stream:
                    json.dump(record, stream, sort_keys=True, ensure_ascii=True, indent=2)
                if self.evidence:
                    self.evidence.append("model_response_saved", json.dumps({"file":target.name,
                        "sha256":sha256(target.read_bytes()).hexdigest(), "prompt_hash":record["prompt_hash"], "mode":self.mode}, sort_keys=True))
            data = json.loads(text, object_pairs_hook=_unique_json_keys, parse_constant=_invalid_json_constant)
            if self.private.clean(data, placeholders=True) != data:
                raise ModelUnavailable("Sensitive model response withheld.", "model_sensitive_response")
            patch = ModelPatch.model_validate(data)
            if any(getattr(patch,k) != v for k,v in binding.items()):
                raise ModelUnavailable("Response binding differs from request.", "model_response_invalid")
            code = self.private.restore(patch.proposed_code, source, task)
            metadata = {**binding, "mode":self.client.mode, "explanation":patch.explanation,
                        "behavior_impact":patch.behavior_impact, "confidence":patch.confidence,
                        "review_areas":patch.review_areas, "proposed_sha256":sha256(code.encode()).hexdigest()}
            self.responses.append(self.private.clean(metadata))
            return patch.model_copy(update={"proposed_code":code})
        except ModelUnavailable:
            self.stopped = True
            raise
        except Exception:
            self.stopped = True
            raise ModelUnavailable("Invalid structured model response; no candidate/fallback accepted.", "model_response_invalid") from None
        finally:
            if self.evidence:
                for attempt in self.client.attempts[count:]:
                    self.evidence.append("model_response", json.dumps({**asdict(attempt), "mode":self.client.mode, "provider_called":self.mode == "live"}, sort_keys=True))


def failure_summary(checks):
    """Only check status/IDs/locations, never golden answers or raw source errors."""
    result = {}
    for stage in ("syntax", "golden", "existing_tests"):
        check = checks.get(stage, {})
        result[stage] = {"ran":check.get("ran"), "passed":check.get("passed")}
    result["mismatched_cases"] = [c["id"] for c in checks.get("golden", {}).get("comparisons", []) if not c.get("matches")][:64]
    result["failed_tests"] = [c["id"] for c in checks.get("existing_tests", {}).get("outcomes", []) if c.get("status") != "passed"][:128]
    return result


class StructuredTranslator:
    def __init__(self, session):
        self.session, self.client = session, session.client
        self.mode = "model_" + self.client.mode

    def translate(self, relative, source, previous=None, failures=None):
        # Generic adapters keep status/ID feedback. Only explicit P8 case
        # feedback may include bounded expected/actual observations.
        if failures and (not isinstance(failures, dict) or not {"syntax","golden","existing_tests"} <= set(failures)):
            failures = {"verification_failed": True, "repair_requested": True}
        if isinstance(failures, dict) and not self.session.case_feedback and "failing_cases" in failures:
            failures = {k:v for k,v in failures.items() if k != "failing_cases"}
        patch = self.session.request("translate", relative, source, previous=previous, failures=failures)
        if patch.behavior_impact != "preserves" or patch.review_areas:
            raise ModelUnavailable("Translation declares semantic/API/configuration changes; needs_review.", "needs_review")
        return patch.proposed_code

    def close(self):
        self.client.close()
