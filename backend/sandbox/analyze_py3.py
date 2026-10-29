"""Static Python 3 analyzer, run by the chosen interpreter inside Docker."""
import ast
import json
import os
import sys


def signature(node):
    args = node.args
    return {
        'posonly': [arg.arg for arg in getattr(args, 'posonlyargs', [])],
        'positional': [arg.arg for arg in args.args], 'kwonly': [arg.arg for arg in args.kwonlyargs],
        'vararg': args.vararg.arg if args.vararg else None, 'kwarg': args.kwarg.arg if args.kwarg else None,
        'defaults': [ast.dump(value, include_attributes=False) for value in args.defaults],
        'returns': ast.dump(node.returns, include_attributes=False) if node.returns else None,
    }


def analyze(root):
    modules, errors = [], []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d != '__pycache__')
        for filename in sorted(files):
            if not filename.endswith('.py'):
                continue
            path = os.path.join(directory, filename)
            relative = os.path.relpath(path, root).replace(os.sep, '/')
            try:
                with open(path, 'rb') as stream:
                    tree = ast.parse(stream.read(), filename=relative)
            except (SyntaxError, ValueError) as exc:
                errors.append({'file': relative, 'type': type(exc).__name__, 'line': getattr(exc, 'lineno', None)})
                continue
            name = relative[:-3].replace('/', '.')
            package_init = name.endswith('.__init__')
            if package_init:
                name = name[:-9]
            package = name if package_init else name.rpartition('.')[0]
            functions, classes, imports, deprecated = [], [], set(), []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append({'name': node.name, 'async': isinstance(node, ast.AsyncFunctionDef),
                                      'signature': signature(node), 'line': node.lineno})
                elif isinstance(node, ast.ClassDef):
                    classes.append({'name': node.name, 'line': node.lineno,
                                    'bases': [ast.dump(base, include_attributes=False) for base in node.bases],
                                    'methods': [{'name': method.name, 'async': isinstance(method, ast.AsyncFunctionDef), 'signature': signature(method)}
                                                for method in node.body if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))]})
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ''
                    if node.level:
                        parts = package.split('.') if package else []
                        parts = parts[:max(0, len(parts) - node.level + 1)]
                        base = '.'.join(parts + ([base] if base else []))
                    imports.add(base)
                    imports.update(base + '.' + alias.name for alias in node.names if alias.name != '*')
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('xrange', 'raw_input', 'unicode', 'basestring'):
                    deprecated.append({'line': node.lineno, 'kind': 'legacy_builtin', 'name': node.func.id,
                                       'note': 'Potential Python 2 dependency; a project-defined shim may exist.'})
                elif isinstance(node, ast.Attribute) and node.attr in ('iteritems', 'itervalues', 'has_key'):
                    deprecated.append({'line': node.lineno, 'kind': 'legacy_attribute', 'name': node.attr,
                                       'note': 'Potential obsolete dictionary API; receiver type is not proven.'})
            for imported in sorted(imports):
                if imported.split('.')[0] in ('imp', 'distutils', 'cgi', 'cgitb', 'telnetlib', 'pipes', 'lib2to3'):
                    deprecated.append({'line': None, 'kind': 'stdlib_review', 'name': imported,
                                       'note': 'Legacy/deprecated standard-library dependency; check the selected target and replacement.'})
            modules.append({'name': name, 'file': relative, 'functions': functions, 'classes': classes,
                            'imports': sorted(value for value in imports if value), 'deprecated': deprecated,
                            'is_test': relative.startswith('tests/') or filename.startswith('test_')})
    return {'python': list(sys.version_info[:3]), 'modules': modules, 'errors': errors,
            'project_executed': False}


if __name__ == '__main__':
    print(json.dumps(analyze('/src'), sort_keys=True))
