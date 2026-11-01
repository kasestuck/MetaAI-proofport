"""Only explicit authored, source-byte-bound PHP offline candidates."""

from hashlib import sha256
import json

from backend.php.protocol import relative_php


OLD_COMMAND = """<?php
namespace ProofportPhpDemo;

function constant_banner() { return shell_exec('printf proofport-safe'); }
"""
NEW_COMMAND = """<?php
namespace ProofportPhpDemo;

function constant_banner() {
    $process = proc_open(['printf', 'proofport-safe'], [0 => ['file', '/dev/null', 'r'], 1 => ['pipe', 'w'], 2 => ['file', '/dev/null', 'w']], $pipes);
    if (!is_resource($process)) throw new \\RuntimeException('command unavailable');
    $output = stream_get_contents($pipes[1]); fclose($pipes[1]);
    if (proc_close($process) !== 0) throw new \\RuntimeException('command failed');
    return $output;
}
"""


def load_manifest(path, original):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("mode") != "explicit_php_fixture_patches_not_ai" or not isinstance(data.get("files"), dict) or not data["files"]:
        raise ValueError("Explicit non-AI PHP migration fixture required.")
    for name, item in data["files"].items():
        relative_php(name)
        source = original / name
        if not source.is_file() or sha256(source.read_bytes()).hexdigest() != item.get("sha256"):
            raise ValueError("PHP fixture source hash mismatch.")
        if not isinstance(item.get("candidates"), list) or not 1 <= len(item["candidates"]) <= 5 or any(not isinstance(c, str) or not c or len(c.encode()) > 262144 for c in item["candidates"]):
            raise ValueError("Bounded authored fixture candidates required.")
    return data


def apply_candidate(manifest, working, iteration):
    for name, item in manifest["files"].items():
        if iteration >= len(item["candidates"]): raise ValueError("No authored repair candidate; no model fallback.")
        (working / name).write_bytes(item["candidates"][iteration].encode("utf-8"))


def constant_command_policy(old, new, proposal):
    # Finite allowlist, never trust behavior_impact or warning disappearance alone.
    return (old.replace('\r\n','\n') == OLD_COMMAND and new.replace('\r\n','\n') == NEW_COMMAND and proposal.get("policy") == "constant_argv"
            and proposal.get("behavior_impact") == "preserves" and not proposal.get("review_areas"))
