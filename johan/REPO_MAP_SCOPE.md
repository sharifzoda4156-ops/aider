# Generic repo-map scope ranking (opt-in)

`AIDER_REPO_MAP_SCOPE` accepts `auto` or a JSON array of repository-relative
paths, e.g. `["service", "shared/contracts"]`. Embedders can pass `scope_paths`
directly to RepoMap. Unset or an explicit empty array keeps existing ordering.
No project names, user IDs, platform-specific folder layouts or task text are
hardcoded. Invalid/traversing/absolute paths fail configuration. No manifest
scripts or package managers execute. No JAE settings/pin or services change.

Explicit scopes can be files or directory prefixes with component boundaries:
`src/api` does not match `src/api-old`. Multiple scopes are allowed, up to 64.
Windows relative separators normalize to `/`; drive/UNC paths are rejected.

Auto mode starts from existing chat files and explicitly mentioned file paths.
For each known seed it chooses the nearest directory with a common package
manifest. Supported marker names cover JavaScript, Python, Rust, Go, JVM, Swift,
.NET, CMake, Ruby, PHP and Dart. These are boundary hints, not a full workspace
parser: workspace glob definitions, dependency aliases and DI/codegen are not
resolved. Without a nested marker, use the seed's directory; for a flat repo use
the exact seed file. Missing seeds or no matching tags preserve the global rank.

Within each group the existing graph ranking is preserved. Groups interleave
three scoped tags to one global tag, then append any remainder. No candidate is
removed; out-of-scope dependencies remain available. This ratio is by tags, not
tokens: actual rendered coverage depends on token budget and symbol lengths.
Upstream important-file prioritization remains in effect. This is a relevance
heuristic, not access control or proof that all necessary dependencies are shown.

Map-cache keys include scopes and auto-mode seed paths. Manual-refresh mode still
requires force refresh/reconstruction when callers mutate settings. Scope metrics
are available in `last_scope_metrics` after a fresh ranking, printed in verbose
mode without paths/source text. A cached map has no new ranking metrics.

The planner decides scope through reading/search; Aider does not infer an entire
task's intent from arbitrary prose here. Each RepoMap owns one repo: an external
multirepo planner must bind scopes to repository identity/revision before passing
paths. This PR does not add that planner protocol or a shared index service.

Tests (stdlib, no model calls):

```sh
python -m unittest discover -s tests/basic -p test_repomap_scope.py -v
```

Tests cover unrelated layouts, nested boundaries, flat/no-manifest repos, missing
scope, Windows separators, stable global reachability and production ranking/cache
methods with parser/ranker dependencies replaced. Full upstream graph/parser and
live acceptance tests are not run locally. No quality/cost gain is claimed yet.

Keep this PR separate from budget #3 and symbol-cache #4; reconcile their small
repomap.py imports/initialization changes and run all tests together before pinning.
Follow-up: language-aware import edges, observed task-specific scope expansion,
distinct planner/executor views and real cold/warm/token-to-success benchmarks.
