"""Generic, optional scope ranking. No project-specific paths or manifest execution."""
import json
import os
from pathlib import PurePosixPath

MARKERS = frozenset(('package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod',
                     'pom.xml', 'build.gradle', 'build.gradle.kts', 'Package.swift',
                     'CMakeLists.txt', 'composer.json', 'Gemfile', 'pubspec.yaml'))


def normalize_path(path):
    if not isinstance(path, str):
        raise ValueError('scope paths must be strings')
    path = path.replace('\\', '/').rstrip('/')
    parts = path.split('/')
    if not path or len(path) > 2048 or path.startswith('/') or ':' in path or any(
        p in ('', '.', '..') for p in parts
    ) or any(ord(c) < 32 for c in path):
        raise ValueError('scope must be a repository-relative path without traversal')
    return path


def read_scope(value=None):
    if value is None:
        value = os.environ.get('AIDER_REPO_MAP_SCOPE')
    if value is None:
        return ()
    if value == 'auto':
        return 'auto'
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise ValueError('AIDER_REPO_MAP_SCOPE must be auto or a JSON array of paths') from None
    if not isinstance(value, (list, tuple)) or len(value) > 64:
        raise ValueError('scope must contain at most 64 relative paths')
    return tuple(sorted(set(normalize_path(p) for p in value)))


def contains(scope, path):
    return path == scope or path.startswith(scope + '/')


def infer_scope(files, seeds):
    """Nearest manifest directory; otherwise seed directory, or exact flat file.

    Manifest filenames are boundary hints, not parsed workspace/dependency graphs.
    Root manifests do not narrow a repo. Unknown seeds cannot narrow it either.
    """
    files = set(files)
    boundaries = {str(PurePosixPath(p).parent) for p in files
                  if PurePosixPath(p).name in MARKERS or p.endswith(('.csproj', '.fsproj'))}
    boundaries.discard('.')
    scopes = set()
    for seed in sorted(set(seeds).intersection(files)):
        candidates = [b for b in boundaries if contains(b, seed)]
        if candidates:
            scopes.add(max(candidates, key=lambda b: (len(b.split('/')), b)))
        else:
            parent = str(PurePosixPath(seed).parent)
            scopes.add(seed if parent == '.' else parent)
    return tuple(sorted(scopes))


def scope_rank(tags, scopes):
    """Stable 3:1 scoped/global interleave; never removes tags or global reachability."""
    tags = list(tags)
    if not scopes:
        return tags, dict(applied=False, scoped_tags=0, global_tags=len(tags), reason='no-scope')
    inside, outside = [], []
    for tag in tags:
        path = tag[0].replace('\\', '/')
        (inside if any(contains(s, path) for s in scopes) else outside).append(tag)
    if not inside:
        return tags, dict(applied=False, scoped_tags=0, global_tags=len(tags), reason='scope-not-found')
    out = []
    i = j = 0
    while i < len(inside) or j < len(outside):
        out.extend(inside[i:i + 3]); i += 3
        out.extend(outside[j:j + 1]); j += 1
    return out, dict(applied=True, scoped_tags=len(inside), global_tags=len(outside), reason='ranked')
