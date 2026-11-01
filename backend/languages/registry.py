"""Stateless adapter selection and conservative additive discovery metadata."""

from backend.languages.base import AdapterError, LanguageAdapter
from backend.languages.runtimes import php_runtimes


def project_language(source, files):
    languages = sorted({language for path in files for language, suffixes in
                        (("python", {".py"}), ("php", {".php", ".phtml"})) if path.suffix.lower() in suffixes})
    language = languages[0] if len(languages) == 1 else "mixed" if languages else "unknown"
    return {"language": language, "languages": languages, "source_version": None, "target_version": None,
            "supported_operations": ["migration", "audit", "compatibility"] if language == "python" else [],
            "readiness": {"can_start": False, "requires_preflight": True,
                          "reason": "preflight_required" if language == "python" else "php_operations_not_implemented" if language == "php" else "language_requires_review"}}


class LanguageRegistry:
    def __init__(self, adapters=None, *, root=None):
        self.root = root
        if adapters is None:
            from backend.languages.python import PythonAdapter
            from backend.languages.php import PHPAdapter
            adapters = [PythonAdapter(), PHPAdapter()]
        self.adapters = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter):
        if not isinstance(adapter, LanguageAdapter) or not adapter.language or adapter.language in self.adapters:
            raise ValueError("Register a unique language adapter implementing the common interface.")
        self.adapters[adapter.language] = adapter

    def get(self, language):
        if language not in self.adapters:
            raise AdapterError("unsupported_language", "No adapter is registered for the selected language.")
        return self.adapters[language]

    def snapshot(self, python_capabilities=None, *, probe=None, docker=None):
        entries = {}
        for language in self.adapters:
            entry = {"language": language, "configured": True, "available": False, "verified": False,
                     "runtimes": [], "supported_operations": [], "available_profiles": {"cases": [], "fixture": []},
                     "readiness": {"can_start": False, "reason": "operations_not_implemented"}}
            if language == "python" and python_capabilities:
                caps = python_capabilities
                runtimes = caps.get("runtimes", [])
                verified = {r["version"] for r in runtimes if r.get("available") is True and r.get("verified") is True}
                sources = {r["version"] for r in runtimes if r.get("source") and r["version"] in verified}
                targets = {r["version"] for r in runtimes if r.get("target") and r["version"] in verified}
                scanner = caps.get("scanner", {}).get("available") is True
                operations = caps.get("operations", {})
                supported = []
                for op, policy in operations.items():
                    ready = any(pair[0] in sources and pair[1] in targets for pair in policy.get("pairs", [])) if op != "audit" else any(v in sources for v in policy.get("source_versions", []))
                    if ready and (scanner or op == "compatibility"):
                        supported.append(op)
                entry.update(available=any(r.get("available") is True for r in runtimes), verified=bool(verified),
                             runtimes=[{**r, "language": "python"} for r in runtimes], supported_operations=supported,
                             source_versions=[r["version"] for r in runtimes if r.get("source") and r["version"] in verified],
                             target_versions=[r["version"] for r in runtimes if r.get("target") and r["version"] in verified],
                             readiness={"can_start": bool(supported), "requires_preflight": True, "reason": "preflight_required" if supported else "verified_runtime_required"},
                             verification_scope="Existing Python runtime receipts and operation adapters; project checks still required.")
                entry.pop("available_profiles")
                entry["profiles_endpoint"] = "/api/v1/projects"
            elif language == "php":
                states = php_runtimes(probe, docker=docker)
                from backend.php.receipts import supported
                readiness = supported(self.root, states) if self.root else {}
                operations = [op for op in ("migration", "audit", "compatibility") if readiness.get(op)]
                for state in states:
                    state["verified"] = bool(readiness.get("migration"))
                    if state["verified"]: state["reason"] = "owned_demo_e2e_verified"
                entry.update(runtimes=states,
                             available=bool(operations), verified=bool(readiness.get("receipt_valid")), supported_operations=operations,
                             source_versions=["7.4", "8.3"] if readiness.get("migration") else [], target_versions=["8.3"] if readiness.get("migration") else [],
                             configured_source_versions=[r["version"] for r in states if r["source"]],
                             configured_target_versions=[r["version"] for r in states if r["target"]],
                             planned_pairs=[["7.4", "8.3"]], lexical_analysis_available=True,
                             operations={"migration": {"pairs": [["7.4", "8.3"]], "execution_modes": ["offline_fixtures"]},
                                         "audit": {"source_versions": ["7.4", "8.3"], "execution_modes": ["offline"], "static_only": True},
                                         "compatibility": {"pairs": [["7.4", "8.3"]], "execution_modes": ["offline"], "verification_levels": ["syntax", "tests", "behavior"]}},
                             verification_scope="Owned fixture E2E and finite inputs; project-specific preflight still required. Static security findings are potential risks.",
                             readiness={"can_start": bool(operations), "requires_preflight": True, "reason": "preflight_required" if operations else "php_e2e_verification_required"})
                if operations: entry.pop("available_profiles")
                entry["profiles_endpoint"] = "/api/v1/projects"
            entries[language] = entry
        return entries
