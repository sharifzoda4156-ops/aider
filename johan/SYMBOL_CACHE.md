# Shared symbol cache (opt-in)

Set `AIDER_SYMBOL_CACHE_DIR` to a private trusted directory outside every scanned
repository. Unset preserves the upstream cache. No JAE configuration, installation
pin or live service is changed. Paths within the current repository are rejected.

Keys hash decoded content, language, query text, basename, parser/lexer package
versions, schema and extractor implementation. Equal content can reuse extracted
symbols across clones/worktrees; dirty files use actual content even if mtime did
not change. Paths are rebound to the current clone on each hit. Basename changes
conservatively miss because parser/lexer detection can depend on filename.

Only validated JSON line/name/kind records are persisted in SQLite, not source
text, paths or pickle. Symbol metadata is still private: callers must control
access to this directory. Cache input is trusted, not an agent-controlled repo.
This reduces parsing, not file-reading/hash costs. It does not cache repo maps
or dependency graphs, and is not yet a shared planner/executor index service.

Nonempty extraction results are stored only if content is unchanged afterwards.
Empty results are not stored to avoid persisting transient parser failure. Cache
read/write errors fall back to extraction; setup failure uses the legacy cache.
Mid-read edits remain possible, as upstream: this is not snapshot isolation.

SQLite transactions support concurrent writers with a one-second lock timeout.
Connections close after each operation. LRU retains up to 64 MiB of JSON payload,
with a 2 MiB entry ceiling; these are logical limits, not filesystem hard quotas.
SQLite pages/indexes add overhead. The cache is disposable; remove it while Aider
is stopped. `RepoMap.symbol_cache.stats` exposes hits/misses/writes/errors.

Validation (no model calls):

```sh
python -m unittest discover -s tests/basic -p test_symbol_cache.py -v
```

Real SQLite and the production get_shared_tags method are exercised with symbol
extraction replaced. Tests cover clone rebinding, identical-mtime edits, key
invalidation, restart, corrupt entries, eviction, concurrency and mid-parse edits.
Actual tree-sitter extraction and upstream tests need Aider dependencies and are
not run locally. Speed/quality improvements require cold/warm project benchmarks.

Separate from budget PR #3: both modify repomap.py initialization/imports. Reconcile
and test together before changing the JAE pin. Future tasks: precise imports and
symbols, task-specific ranking, planner/executor views and bounded scope expansion.
