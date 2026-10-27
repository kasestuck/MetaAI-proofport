"""Trusted Python 2.7/3.12 harness. Import/execute targets only inside Docker."""
from __future__ import print_function

import base64
import importlib
import io
import json
import os
import sys
import tempfile
import traceback
import unittest

PY2 = sys.version_info[0] == 2
TEXT = type(u'')
INTEGER = (int, type(1 << 100))


class HarnessFailure(Exception):
    pass


def text(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return TEXT(value)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def encode(value):
    if value is None:
        return {'t': 'none', 'v': None}
    if isinstance(value, bool):
        return {'t': 'bool', 'v': value}
    if isinstance(value, INTEGER):
        return {'t': 'int', 'v': value}
    if isinstance(value, float):
        return {'t': 'float', 'v': repr(value)}
    if isinstance(value, TEXT):
        return {'t': 'str', 'v': value}
    if isinstance(value, bytes):
        try:
            return {'t': 'bytes_or_text' if PY2 else 'bytes', 'v': base64.b64encode(value).decode('ascii')}
        except Exception:
            raise ValueError('Bytes could not be encoded')
    if isinstance(value, (list, tuple, set, frozenset)):
        tag = 'tuple' if isinstance(value, tuple) else ('set' if isinstance(value, (set, frozenset)) else 'list')
        items = [encode(item) for item in value]
        return {'t': tag, 'v': sorted(items, key=canonical) if tag == 'set' else items}
    if isinstance(value, dict):
        items = [[encode(key), encode(item)] for key, item in value.items()]
        return {'t': 'dict', 'v': sorted(items, key=lambda pair: canonical(pair[0]))}
    if hasattr(value, '__dict__'):
        return {'t': 'object', 'v': {'class': value.__class__.__name__, 'attrs': encode(vars(value))}}
    return {'t': 'object', 'v': {'class': value.__class__.__name__, 'repr': repr(value)}}


class Capture(object):
    def __init__(self):
        self.parts = []
        self.size = 0

    def write(self, value):
        value = text(value)
        self.size += len(value)
        if self.size > 200000:
            raise HarnessFailure('Harness capture exceeded 200000 characters')
        self.parts.append(value)

    def flush(self):
        pass

    def isatty(self):
        return False

    def getvalue(self):
        return u''.join(self.parts)


def safe_path(root, relative):
    path = os.path.abspath(os.path.join(root, relative))
    if not path.startswith(os.path.abspath(root) + os.sep):
        raise ValueError('Fixture path escapes its root')
    return path.encode('utf-8') if PY2 and isinstance(path, TEXT) else path


def resolve(value, saved, temp):
    if isinstance(value, dict):
        if set(value) == {'ref'}:
            return saved[value['ref']]
        if set(value) == {'file'}:
            return safe_path('/src', value['file'])
        if set(value) == {'temp'}:
            return safe_path(temp, value['temp'])
        if set(value) == {'bytes_b64'}:
            return base64.b64decode(value['bytes_b64'])
        if set(value) == {'unicode'}:
            return value['unicode']
        if set(value) == {'tuple'}:
            return tuple(resolve(item, saved, temp) for item in value['tuple'])
        return dict((resolve(k, saved, temp), resolve(v, saved, temp)) for k, v in value.items())
    if isinstance(value, list):
        return [resolve(item, saved, temp) for item in value]
    if PY2 and isinstance(value, TEXT):
        return value.encode('utf-8')
    return value


def attribute(path):
    parts = path.split('.')
    for count in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module('.'.join(parts[:count]))
            for part in parts[count:]:
                obj = getattr(obj, part)
            return obj
        except ImportError:
            if count == 1:
                raise


def execute_case(case):
    saved = {}
    temp = tempfile.mkdtemp(prefix='proofport-case-')
    outputs = []
    for setup in case.get('files', []):
        with open(safe_path(temp, setup['name']), 'wb') as stream:
            stream.write(setup['text'].encode('utf-8'))
    for step in case['steps']:
        stdout, stderr = Capture(), Capture()
        old_out, old_err, old_in = sys.stdout, sys.stderr, sys.stdin
        stdin = case.get('stdin', '')
        sys.stdout, sys.stderr = stdout, stderr
        sys.stdin = io.BytesIO(stdin.encode('utf-8')) if PY2 else io.StringIO(stdin)
        try:
            if 'attribute' in step:
                result = attribute(step['attribute'])
            else:
                if 'method' in step:
                    name, method = step['method'].split('.', 1)
                    func = getattr(saved[name], method)
                elif step.get('builtin') in ('bool', 'repr', 'len'):
                    func = {'bool': bool, 'repr': repr, 'len': len}[step['builtin']]
                else:
                    func = attribute(step['call'])
                args = resolve(step.get('args', []), saved, temp)
                kwargs = resolve(step.get('kwargs', {}), saved, temp)
                result = func(*args, **kwargs)
            if 'save' in step:
                saved[step['save']] = result
            outcome = {'value': encode(result)}
        except Exception as exc:
            if isinstance(exc, HarnessFailure):
                raise
            outcome = {'exception': {'type': type(exc).__name__, 'message': text(str(exc))}}
            if getattr(exc, 'errno', None) is not None:
                outcome['exception']['errno'] = exc.errno
        finally:
            sys.stdout, sys.stderr, sys.stdin = old_out, old_err, old_in
        outcome.update(stdout=stdout.getvalue(), stderr=stderr.getvalue())
        outputs.append(outcome)
    return {'id': case['id'], 'module': case['module'], 'steps': outputs}


class TestResult(unittest.TestResult):
    def __init__(self):
        unittest.TestResult.__init__(self)
        self.outcomes = []

    def addSuccess(self, test):
        unittest.TestResult.addSuccess(self, test)
        self.outcomes.append({'id': test.id(), 'status': 'passed'})

    def addFailure(self, test, err):
        unittest.TestResult.addFailure(self, test, err)
        self.outcomes.append({'id': test.id(), 'status': 'failed', 'reason': text(err[1])})

    def addError(self, test, err):
        unittest.TestResult.addError(self, test, err)
        self.outcomes.append({'id': test.id(), 'status': 'error', 'reason': text(err[1])})

    def addSkip(self, test, reason):
        unittest.TestResult.addSkip(self, test, reason)
        self.outcomes.append({'id': test.id(), 'status': 'skipped', 'reason': reason})


def main(request):
    sys.path.insert(0, '/src')
    os.chdir('/src')
    action = request.get('action', 'cases')
    if action == 'compile':
        errors = []
        for directory, dirs, files in os.walk('/src'):
            for filename in sorted(files):
                if filename.endswith('.py'):
                    path = os.path.join(directory, filename)
                    try:
                        with open(path, 'rb') as stream:
                            compile(stream.read(), path, 'exec')
                    except Exception as exc:
                        errors.append({'file': os.path.relpath(path, '/src'), 'type': type(exc).__name__, 'message': text(str(exc))})
        return {'errors': errors}
    if action == 'tests':
        result = TestResult()
        captured = Capture()
        old_out, old_err = sys.stdout, sys.stderr
        try:
            sys.stdout = sys.stderr = captured
            unittest.defaultTestLoader.discover('/src/tests').run(result)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        return {'tests_run': result.testsRun, 'outcomes': sorted(result.outcomes, key=lambda item: item['id']), 'output': captured.getvalue()}
    return {'cases': [execute_case(case) for case in request['cases']]}


if __name__ == '__main__':
    try:
        response = main(json.load(sys.stdin))
        response['python'] = list(sys.version_info[:3])
        print(json.dumps(response, sort_keys=True, ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({'harness_error': type(exc).__name__, 'message': text(str(exc))}))
        sys.exit(2)
