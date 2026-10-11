# Opt-in definition priority: review and deferred comparison

## Versions and scope

Base: #8, branch `codex/symbol-index-completeness`, commit
`d5b99b11d86e8d5f7a939081f68bbb86e34ceea4`. Base CI run 38110950642
succeeded on Python 3.12/3.13: 529 passed, 1 skipped and smoke on each.
Candidate: immutable head recorded in the new draft PR and coordinator report.

Dependencies: #6 (`0b532f3bd295a1025273cffaa89fba9bd2dc500c`) → #7
(`e4603def16ceb1f231623a4848abf761701b821d`) → #8 (base above) → this draft.
Reported production baseline remains `v0.86.2+johan.3`,
`005aaafc43509c199ba4e54bb2bd7285f42b9494`; actual VPS runtime is not inspected.
#6 brings opt-in token ceiling/cache/scope, #7 structured index views, #8 bounds
shared-cache adapter enumeration and avoids storing truncated prefixes.

This change is only an opt-in executor projection. It does not change extraction,
index/cache invalidation, ordinary repo maps, planner defaults, CLI, backend,
systems, production pin/flags, databases or deployments. No merge, tag, release,
activation or paid-model/Serper/agent benchmark is performed.

## Problem and behavior

An early file's lexical references can consume the global view cap before a
definition in the same file or a later file is selected. A synthetic base case
retains two definitions but its cap=2 default executor view selects two refs
and zero definitions. That source-order policy remains the default.

Explicit `index.view("executor", max_symbols=2, prefer_definitions=True)` reserves
the existing global count budget for retained definitions across selected files
before using the remainder for lexical references. At that cap, both definitions
are selected in the regression fixture. This is a projection invariant, not an
end-to-end task-quality or cost result.

Documentation/defaults and limitations: [SYMBOL_INDEX_VIEWS.md](SYMBOL_INDEX_VIEWS.md).
Definitions are not proven contracts; references are not resolved call edges.
No additional parsing, file expansion or inference about public visibility occurs.

## Offline reproduction

Local environment: Linux 6.18.44 x86_64, Python 3.12.14, pip 26.2.1, Git 2.51.1.
No full parser/pytest dependencies installed locally; real parsing is checked in CI.
Tests use synthetic tags and temporary fixtures, with no external model calls.

```sh
python -m unittest tests.basic.test_symbol_view_priority tests.basic.test_symbol_cache tests.basic.test_symbol_index tests.basic.test_repomap_budget tests.basic.test_repomap_scope
python -m py_compile aider/symbol_index.py tests/basic/test_symbol_view_priority.py tests/basic/test_symbol_index_integration.py
git diff --check
```

Observed locally: 50 tests passed; compilation and whitespace check passed.
Nine new unit regressions include default-output compatibility, multi-file
definition preference, leftover refs, definition overflow, unknown locations,
empty/truncated extraction, duplicate identity, freshness and invalid options.
The inherited tests cover budget, shared-cache bounds and same-mtime invalidation.
One new integration test uses real Python/JavaScript extraction, then verifies
projection without reparse, the same snapshot, omission count and exact names.
Full CI commands remain `pip install pytest`, `pip install .`,
`pytest tests/basic` with `AIDER_ANALYTICS=false`, then
`python johan/jae_smoke.py`; only the test-only PR base filter includes #8 now.
Exact candidate CI versions, SHA and results are recorded in the report/PR.

## Future comparison, deferred

Keep the matched tasks/models/budgets/environment and independent acceptance
protocol in [SYMBOL_INDEX_COMPARISON_PROTOCOL.md](SYMBOL_INDEX_COMPARISON_PROTOCOL.md).
Do not start a paid comparison without separate authorization. Add these arms:

| Comparison | Attribution |
| --- | --- |
| Production → full candidate | Accumulated #6/#7/#8 and this opt-in projection, with explicit absent-capability fallback |
| #7 → full candidate | Both additions from this executor (#8 bounds plus definition priority) |
| #8 → this candidate | Isolates this projection code; use identical settings/selection and `prefer_definitions=False` as the compatibility control |
| Same candidate, False → True | Isolates the enabled policy on one frozen retained index and a separately frozen downstream consumer |

Pre-register selected paths and the existing index limits (128 files, 1 MiB/file,
8 MiB total, 2048 enumerated tags/file) and view cap=256, plus any smaller
task-specific caps. Never silently enlarge them for the treatment arm. Pair
cache OFF/ON-cold/ON-warm states and priming sequences separately. Pin parser,
query and tokenizer identities. The policy is deterministic on a fixed retained
index; inherited parser capture order can vary between separate builds. Preserve
raw snapshots only in an authorized private experiment, not source-bearing reports.

Freeze the same provider/model/version, prompts, task revisions, environment,
retry policy, total token/cost/time caps and acceptance tests. Current CLI does
not auto-consume structured views; any future consumer must be reviewed/frozen
separately. No gain is expected in a default profile that never uses this API.
Production/#7/#8 lack the new option: report absence honestly and preserve their
existing source-order path instead of fabricating support or changing their code.

Measure independent goal acceptance, edit correctness/regressions, all tokens
and known cost through success including retries/planning/judging, wall time,
and context completeness. Record definition/ref retention, relevant evidence
coverage, extraction unknown/truncation and projection omissions. Zero projection
omissions do not establish extraction completeness. Keep capped/failed tasks in
the denominator; unknown cost is unknown. Symbol count equality does not imply
equal tokens or cost. Definition preference can displace useful references or
favor an early definition-heavy file, so task success/time/cost remain unmeasured.
