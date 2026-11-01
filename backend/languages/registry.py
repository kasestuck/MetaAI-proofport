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
    def __init__(self, adapters=None):
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
                entry.update(runtimes=states,
                             source_versions=[], target_versions=[],
                             configured_source_versions=[r["version"] for r in states if r["source"]],
                             configured_target_versions=[r["version"] for r in states if r["target"]],
                             planned_pairs=[["7.4", "8.3"]], lexical_analysis_available=True,
                             readiness={"can_start": False, "reason": "php_operations_not_implemented"})
            entries[language] = entry
        return entries
