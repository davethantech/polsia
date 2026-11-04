"""Tenant-scoped, self-hosted software proposal factory.

This module treats generated code as *untrusted data*. It never calls a shell,
executes generated code, changes a Git repository, or deploys a service.
Its validations are syntax checks, not security proofs or runnable tests.
"""
import ast
import hashlib
import json
import posixpath
import re

from . import providers

MAX_SOURCE_FILES = 10
MAX_SOURCE_BYTES = 20000
MAX_FILE_BYTES = 8000
MAX_CHANGED_FILES = 5
MAX_CHANGE_BYTES = 16000
MAX_GOAL_LENGTH = 1200
ALLOWED_EXTENSIONS = frozenset({'.py', '.json', '.js', '.ts', '.html', '.css', '.md', '.txt', '.yaml', '.yml'})
PATH_PART = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')
PROTECTED_SEGMENTS = frozenset({'.git', '.github', 'node_modules', '.venv', '__pycache__',
                                '.ssh', 'secrets', 'credentials', 'private'})
PROTECTED_NAMES = frozenset({'id_rsa', 'id_ed25519', '.env', '.env.local', '.npmrc',
                             'Dockerfile', 'compose.yaml', 'docker-compose.yml'})


def checked_path(path):
    if not isinstance(path, str) or not path or len(path) > 180 or '\\' in path:
        raise ValueError('Invalid source path')
    if path.startswith('/') or path.endswith('/') or '//' in path or '\x00' in path:
        raise ValueError('Invalid source path')
    parts = path.split('/')
    if any(p in ('', '.', '..') or not PATH_PART.fullmatch(p) for p in parts):
        raise ValueError('Unsafe source path')
    if any(p.lower() in PROTECTED_SEGMENTS or p.startswith('.') for p in parts):
        raise ValueError('Protected source path')
    if parts[-1].lower() in PROTECTED_NAMES or 'secret' in parts[-1].lower() or 'token' in parts[-1].lower():
        raise ValueError('Secret/configuration file cannot be sent to the model')
    if posixpath.splitext(parts[-1])[1].lower() not in ALLOWED_EXTENSIONS:
        raise ValueError('Unsupported source extension')
    return path


def _check_text(content, limit):
    if not isinstance(content, str) or not content or len(content.encode('utf-8')) > limit:
        raise ValueError('Invalid source contents or size')
    if '\x00' in content:
        raise ValueError('Binary source is not supported')
    return content


def validate_snapshot(files):
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_SOURCE_FILES:
        raise ValueError('Supply 1–10 source files')
    result = {}
    for path, content in files.items():
        checked_path(path)
        _check_text(content, MAX_FILE_BYTES)
        result[path] = content
    if sum(len(value.encode('utf-8')) for value in result.values()) > MAX_SOURCE_BYTES:
        raise ValueError('Source snapshot exceeds 20 KB')
    return result


def syntax_result(path, content):
    if path.endswith('.py'):
        try:
            ast.parse(content, filename=path)
            return {'checked': True, 'valid': True, 'validator': 'python_ast'}
        except (SyntaxError, ValueError) as exc:
            return {'checked': True, 'valid': False, 'validator': 'python_ast',
                    'reason': 'invalid_python_syntax', 'line': getattr(exc, 'lineno', None)}
    if path.endswith('.json'):
        try:
            json.loads(content)
            return {'checked': True, 'valid': True, 'validator': 'json_parser'}
        except (ValueError, TypeError):
            return {'checked': True, 'valid': False, 'validator': 'json_parser',
                    'reason': 'invalid_json'}
    return {'checked': False, 'valid': None, 'validator': None}


def sha256(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def inspect(files):
    snapshot = validate_snapshot(files)
    entries = []
    for path, content in sorted(snapshot.items()):
        entries.append({'path': path, 'bytes': len(content.encode('utf-8')),
                        'sha256': sha256(content), 'syntax': syntax_result(path, content)})
    return {'files': entries, 'total_bytes': sum(e['bytes'] for e in entries),
            'syntax_failures': sum(e['syntax']['valid'] is False for e in entries),
            'verification': 'syntax_only_no_execution'}


def validate_goal(goal):
    if not isinstance(goal, str) or not 10 <= len(goal.strip()) <= MAX_GOAL_LENGTH:
        raise ValueError('Engineering goal must be 10–1200 characters')
    return goal.strip()


def validate_proposal(proposal, snapshot):
    if not isinstance(proposal, dict) or set(proposal) != {'summary', 'files', 'limitations'}:
        raise ValueError('Local model returned an invalid proposal')
    summary = proposal['summary']
    limitations = proposal['limitations']
    if not isinstance(summary, str) or not 5 <= len(summary) <= 700:
        raise ValueError('Invalid proposal summary')
    if not isinstance(limitations, str) or len(limitations) > 700:
        raise ValueError('Invalid proposal limitations')
    items = proposal['files']
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_CHANGED_FILES:
        raise ValueError('Expected 1–5 changed files')
    seen = set()
    changes = []
    total = 0
    for item in items:
        if not isinstance(item, dict) or set(item) != {'path', 'content'}:
            raise ValueError('Invalid proposed file object')
        path = checked_path(item['path'])
        if path in seen:
            raise ValueError('Duplicate proposed path')
        seen.add(path)
        content = _check_text(item['content'], MAX_FILE_BYTES)
        total += len(content.encode('utf-8'))
        if total > MAX_CHANGE_BYTES:
            raise ValueError('Proposed changes exceed 16 KB')
        if snapshot.get(path) == content:
            raise ValueError('Unchanged file in proposed changes')
        syntax = syntax_result(path, content)
        if syntax['valid'] is False:
            raise ValueError('Proposed source did not pass '+syntax['validator'])
        changes.append({'path': path, 'content': content, 'old_sha256': sha256(snapshot[path]) if path in snapshot else None,
                        'new_sha256': sha256(content), 'syntax': syntax})
    return {'summary': summary, 'limitations': limitations, 'changes': changes,
            'verification': 'python_json_syntax_checked_other_formats_unchecked_no_tests_run',
            'executed': False, 'deployed': False, 'source_sha256': {
                path: sha256(source) for path, source in sorted(snapshot.items())}}


def propose(inputs, reserve_call, record_call):
    goal = validate_goal(inputs.get('goal'))
    snapshot = validate_snapshot(inputs.get('files'))
    model = providers.require_configured()
    reserve_call(model)
    try:
        response = providers.generate_code(goal, snapshot)
        proposal = validate_proposal(response['content'], snapshot)
        record_call('completed', response['usage'])
    except Exception:
        record_call('failed', {'input_tokens': None, 'output_tokens': None})
        raise
    proposal['model'] = response['model']
    proposal['model_usage'] = response['usage']
    return proposal
