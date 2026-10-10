# Shared symbol index and role-specific views

This draft builds on the opt-in repo-map features in PR #6. Existing prompts,
CLI behavior, map generation and JAE installation remain unchanged.

## API

```python
index = repo_map.build_symbol_index(
    ["service/api.py", "client/view.js"],  # caller-authorized/tracked relative files
    max_files=128,
    max_file_bytes=1024 * 1024,
    max_total_bytes=8 * 1024 * 1024,
    max_symbols_per_file=2048,
)
planner = index.view("planner", max_symbols=256)
executor = index.view("executor", max_symbols=512)
```

Extraction runs once. Both outputs carry the same `snapshot_id`, selected file
content hashes, relative paths and extraction coverage. Planner receives
locations of definitions; executor receives definitions and lexical references.
Source bodies and absolute workspace paths are excluded. Symbols themselves
are code-derived data and must still follow the caller's access policy.
Lines are one-based; lexer references without a location use JSON null.

The snapshot ID hashes retained symbols, paths, coverage and file contents. It
is not a Git SHA, repository identity, user identity or authorization credential.
Identical contents/extraction across clones produce identical IDs. The caller
must bind task, repository and revision separately. This API does not wire an
index into the JAE planner or executor.

## Freshness and limits

The legacy mtime-only cache is bypassed. If the opt-in shared symbol cache is
available it is reused, since its keys include file content; otherwise selected
files are parsed directly with the existing Aider parser/query/lexer machinery.
Files are hashed before and after extraction and all selected files are checked
again after construction. Every view validates current selected contents;
changes, deletions or symlink replacement raise `StaleSymbolIndex`. Rebuild on
that exception. `index.validate()` returns changed paths without source bodies.

Reject absolute paths, traversal and symlink files/directories. The root is the
trusted caller-provided workspace. This is not a security sandbox against a
concurrent adversary replacing directories between checks. Workspace isolation
and authorization remain external responsibilities.

Limits bound selected files, file bytes, total bytes, tag enumeration and output
symbol count. Excess file/byte selection fails explicitly; caller narrows scope.
Tag truncation is marked per file. View truncation reports `omitted_symbols`
from retained tags, not the number of unknown/unparsed symbols. Input enumeration
is bounded even if duplicate paths are supplied indefinitely. These are not token
or wall-clock limits; apply a tokenizer/timeout in the consuming service.

## Honest coverage and next integration

`extracted` means existing Aider machinery emitted symbols, not that extraction
is complete. `truncated` means the extraction cap was reached; `unknown` covers
empty output (unsupported language, empty file, parser failure or no matches).
Read errors propagate; do not silently turn them into successful empty indexes.

Definitions are not proven public APIs or contracts. References are lexical
candidates, not resolved call edges. DI/codegen/import resolution and signatures
are future layers. No tests are guessed from filenames. Only selected files are
validated; new files elsewhere do not invalidate the index. A downstream planner
must bind a repository snapshot and request another scope when context is missing.

Fallback: on failed construction or stale data, reselect/rebuild; if still
unavailable, preserve the existing map/read-file path and report unavailable
index coverage. Do not accept partial extraction as proof of task completion.
The default stays unchanged until a separate integration decision.

## Validation

Ten stdlib tests cover shared views, bounded inputs/output, same-mtime edits,
mutation during extraction, deletion, symlinks, traversal, unknown coverage and
clone-stable identifiers. Two full-dependency integration tests exercise real
Python/JavaScript queries, the legacy-cache bypass and shared cache reuse.
No paid model or live Serper benchmark is involved.
