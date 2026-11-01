"""Thin delegation to the existing Docker-only Python implementations."""

from pathlib import Path

from backend.core.analyzer import analyze_python
from backend.core.security import findings_for, scan
from backend.core.versions import VersionRegistry
from backend.languages.base import AdapterError, AnalysisResult, SecurityResult, inventory


def _python_only(source):
    _, files = inventory(source)
    if any(p.suffix.lower() in {".php", ".phtml"} for p in files) and not any(p.suffix == ".py" for p in files):
        raise AdapterError("language_mismatch", "PHP-only projects cannot use the Python analyzer or Bandit adapter.")


class PythonAdapter:
    language = "python"

    def analyze(self, source: Path, *, source_version=None, target_version=None, runner=None, evidence=None):
        # Callers provide the prepared project directory, exactly as the current
        # universal worker does (including copies of single-file inputs).
        if runner is None or source_version is None or not Path(source).is_dir():
            raise AdapterError("python_analysis_context_required", "Python analysis requires a prepared directory, Docker runner and explicit verified source version.")
        _python_only(source)
        runtime = VersionRegistry(runner).select(source_version)
        data = analyze_python(runner, source, runtime["image_id"], source_version, target_version)
        if evidence:
            evidence.append("language_analysis", "Python adapter delegated to the existing source-interpreter Docker analyzer.")
        return AnalysisResult("python", source_version, target_version, data,
                              limitations=("Analysis alone does not verify tests or behavior.",))

    def compatibility(self, run, run_id, root, settings):
        # Preserve RunSpec, working copies, image pins, shared gate, evidence and
        # finalizer. No duplicated interpreter/test/comparator pipeline.
        from backend.core.universal import execute
        return execute(run, run_id, root, settings, "compatibility")

    def security_findings(self, runner, source, evidence):
        _python_only(source)
        data = scan(runner, source, evidence)
        _, details = findings_for(data)
        return SecurityResult("python", tuple(details), "partial" if data.get("errors") else "parsed_files_only",
                              ("Bandit warnings are potential risks; a clean scan does not prove safety.",))
