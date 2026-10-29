"""Conservative code/context checks independent of provider confidence."""

import ast
from copy import deepcopy
import re
import shlex


PROTECTED = {"B307", "B102", "B608", "B105", "B106", "B107", "B324", "B301"}


def _dump(node):
    return ast.dump(node, include_attributes=False)


def public_api(source):
    result = {}
    def visit(nodes, prefix=""):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (not node.name.startswith("_") or (node.name.startswith("__") and node.name.endswith("__"))):
                result[prefix + node.name] = (_dump(node.args), [_dump(d) for d in node.decorator_list], _dump(node.returns) if node.returns else None)
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                result[prefix + node.name] = [_dump(base) for base in node.bases]
                visit(node.body, prefix + node.name + ".")
    visit(ast.parse(source).body)
    return result


def constant_argv_only(source):
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"]
    return bool(calls) and all(
        node.func.attr == "check_output" and len(node.args) == 1 and isinstance(node.args[0], ast.List)
        and all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in node.args[0].elts)
        and node.args[0].elts and node.args[0].elts[0].value == "/usr/bin/printf"
        and all(re.fullmatch(r"[A-Za-z0-9_-]+", arg.value) for arg in node.args[0].elts[1:])
        and len(node.keywords) == 1 and node.keywords[0].arg == "shell"
        and isinstance(node.keywords[0].value, ast.Constant) and node.keywords[0].value.value is False
        for node in calls
    )


def constant_shell_to_argv(before, after, line=None, column=None):
    tree, target = ast.parse(before), ast.parse(after)
    candidates = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                  and node.func.value.id == "subprocess" and node.func.attr == "check_output"
                  and (line is None or node.lineno == line)
                  and (column is None or node.col_offset == column)
                  and len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
                  and isinstance(node.args[0].value, str) and re.fullmatch(r"/usr/bin/printf(?: [A-Za-z0-9_-]+)+", node.args[0].value)
                  and len(node.keywords) == 1 and node.keywords[0].arg == "shell"
                  and isinstance(node.keywords[0].value, ast.Constant) and node.keywords[0].value.value is True]
    if line is not None and len(candidates) != 1:
        return False  # Ambiguous source locations never authorize an automatic fix.
    for call in candidates:
        expected = deepcopy(tree)
        for node in ast.walk(expected):
            if isinstance(node, ast.Call) and (node.lineno, node.col_offset) == (call.lineno, call.col_offset) and _dump(node) == _dump(call):
                node.args = [ast.List(elts=[ast.Constant(value=arg) for arg in shlex.split(call.args[0].value)], ctx=ast.Load())]
                node.keywords = [ast.keyword(arg="shell", value=ast.Constant(value=False))]
                break
        if _dump(expected) == _dump(target) and constant_argv_only(after):
            return True
    return False


def review_reasons(finding, proposal, before, after):
    reasons = []
    if proposal.behavior_impact != "preserves":
        reasons.append("Provider explicitly declares changed or unknown behavior.")
    if proposal.review_areas:
        reasons.append("Compatibility review: " + ", ".join(proposal.review_areas))
    if finding["scanner_test"] in PROTECTED:
        reasons.append("Eval/query/credential/crypto/serialization semantics require manual review.")
    if public_api(before) != public_api(after):
        reasons.append("Public signatures, defaults, decorators or class bases changed.")
    if finding["scanner_test"] != "B602" or not constant_shell_to_argv(before, after, finding.get("line"), finding.get("column")):
        reasons.append("No independently supported behavior-preserving transformation for this patch.")
    return reasons
