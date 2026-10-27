"""Trusted static analyzer, executed by the selected source interpreter in Docker."""
from __future__ import print_function

import ast
import json
import os
import sys


def analyze(root):
    modules = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d != '__pycache__')
        for filename in sorted(files):
            if not filename.endswith('.py'):
                continue
            path = os.path.join(directory, filename)
            relative = os.path.relpath(path, root).replace(os.sep, '/')
            with open(path, 'rb') as stream:
                tree = ast.parse(stream.read(), filename=relative)
            name = relative[:-3].replace('/', '.')
            if name.endswith('.__init__'):
                name = name[:-9]
            functions, classes, imports = [], [], []
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    functions.append({'name': node.name, 'args': [getattr(a, 'id', getattr(a, 'arg', None)) for a in node.args.args],
                                      'defaults': len(node.args.defaults)})
                elif isinstance(node, ast.ClassDef):
                    classes.append({'name': node.name, 'methods': [m.name for m in node.body if isinstance(m, ast.FunctionDef)]})
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ''
                    if node.level:
                        package = name.split('.')[:-1]
                        if filename == '__init__.py':
                            package = name.split('.')
                        base = '.'.join(package[:len(package) - node.level + 1] + ([base] if base else []))
                    imports.append(base)
                    imports.extend(base + '.' + alias.name for alias in node.names if alias.name != '*')
            modules.append({'name': name, 'file': relative, 'functions': functions, 'classes': classes,
                            'imports': sorted(set(imports)), 'is_test': relative.startswith('tests/') or filename.startswith('test_')})
    return {'python': list(sys.version_info[:3]), 'modules': modules}


if __name__ == '__main__':
    print(json.dumps(analyze('/src'), sort_keys=True))
