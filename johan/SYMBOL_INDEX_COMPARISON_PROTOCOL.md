# Deferred comparison protocol: bounded shared-cache extraction

No comparative agent run was performed. Offline regression results establish
the enumeration/caching invariant; they do not establish task success, token
savings, lower cost or faster execution.

## Fixed versions

| Arm | Commit | Meaning |
| --- | --- | --- |
| Production baseline, reported pin | `005aaafc43509c199ba4e54bb2bd7285f42b9494` | Tag `v0.86.2+johan.3`; actual VPS runtime not inspected |
| Inherited #6 | `0b532f3bd295a1025273cffaa89fba9bd2dc500c` | Opt-in rendered-map token ceiling, content-addressed shared symbols, generic scope |
| Pre-change #7 | `e4603def16ceb1f231623a4848abf761701b821d` | Selected-file content-bound index, planner definitions and executor lexical references |
| Candidate | The immutable head SHA recorded in this draft PR and coordinator report | #6/#7 plus bounded cache-adapter tag enumeration and no partial cache writes |

The draft targets the actual #7 branch, `codex/symbol-index-views`. Dependencies
are #6 then #7. None is claimed installed. Capture `git rev-parse HEAD` after
checkout and use detached immutable commits, never floating branch names.

## Offline reproduction

Local environment: Linux 6.18.44 x86_64, Python 3.12.14, pip 26.2.1, Git 2.51.1.
No parser/pytest packages were installed locally. The stdlib tests compile the
actual production methods through AST, use synthetic tag streams and a real
temporary SQLite cache; they do not substitute a reimplementation of those
methods. Fixtures are synthetic and repository source bodies are not exported.

From the candidate repository root:

```sh
python -m unittest tests.basic.test_symbol_cache tests.basic.test_symbol_index tests.basic.test_repomap_budget tests.basic.test_repomap_scope
python -m py_compile aider/repomap.py aider/symbol_index.py aider/symbol_cache.py tests/basic/test_symbol_cache.py tests/basic/test_symbol_index_integration.py
git diff --check
```

Observed: 41 tests passed; compilation and whitespace check passed.
Reproduce the pre-fix failure with candidate tests against unchanged #7 code:

```sh
git worktree add --detach ../aider-base-repro e4603def16ceb1f231623a4848abf761701b821d
cp tests/basic/test_symbol_cache.py ../aider-base-repro/tests/basic/test_symbol_cache.py
cd ../aider-base-repro
python -m unittest tests.basic.test_symbol_cache.TestBoundedSharedSymbols.test_miss_bounds_enumeration_and_never_caches_partial_tags tests.basic.test_symbol_cache.TestBoundedSharedSymbols.test_duplicate_tags_still_count_toward_enumeration_limit
```

Observed on #7: both fail because extraction requests a fourth tag when cap=2
allows only two plus one lookahead. No existing executor branch was modified.
On candidate the same invariants pass, including the default cap of 2048.
Exact-cap nonempty extraction is cacheable; empty extraction is `unknown`.

Full dependency validation belongs to `Johan fork CI`: Ubuntu runner,
Python 3.12/3.13, `AIDER_ANALYTICS=false`, `pip install pytest`, `pip install .`,
`pytest tests/basic`, then `python johan/jae_smoke.py`. The smoke does not activate
JAE or deploy anything. Its definition was reviewed before running; no external
model is invoked. Exact runner/tool/parser versions and test counts are in the
CI job logs linked by the report. Only the pull-request base filter was extended
to include #7; test commands and push/tag/release behavior are unchanged.

## Future matched comparison, only after separate authorization

1. Freeze a language/structure-diverse task set and task base revisions before
   looking at results. Include small projects, monorepos, duplicate-heavy files,
   unsupported languages and tasks requiring definitions across selected files.
   Define acceptance from each goal independently of the produced diff. Use an
   evaluator blind to arm; fixtures alone are not task acceptance.
2. Pin identical model/provider/version, prompts, tool harness, task snapshots,
   environment/container image, tokenizer, sampling settings, retry policy,
   task token/cost/time caps and test commands across each paired comparison.
   Record all versions and sanitized run IDs. Randomize arm order; use repeated
   matched runs rather than one lucky result. Keep a separate baseline test run
   to identify preexisting failures. Do not execute user hooks/build scripts for
   indexing; any future task tests need their own authorized sandbox policy.
3. Pre-register a settings manifest. Run a default profile with token limit,
   cache and scope disabled and no structured-index consumer: this patch should
   have no direct effect there. Run explicit opt-in profiles separately. For
   #7 versus candidate use identical selected paths, `max_files=128`,
   `max_file_bytes=1048576`, `max_total_bytes=8388608`,
   `max_symbols_per_file=2048`, view cap=256, and the same roles/fallback policy.
   Freeze any task-specific narrower limits or scope selections in advance.
   Distinguish shared-cache OFF, ON/cold and ON/warm using private isolated
   directories per arm, with identical priming sequences. Record cache failures,
   truncation and unavailable results; do not erase them from the denominator.
4. Compare **production to complete candidate** to measure the accumulated
   package/configuration treatment (#6, #7 and this patch). For an opt-in map
   profile, a proposed token ceiling is 8192, same requested map budget and
   context-window settings; scope paths are chosen from each task's manifest,
   without product-specific rules. Record which baseline capabilities are
   absent and the common read/search fallback. Do not fabricate symbol support
   in production. Any new harness consuming #7's API must be separately reviewed
   and frozen for all arms; current ordinary CLI does not auto-consume that API.
5. Compare **#7 to candidate** with that same explicit index/cache profile to
   isolate this patch. The parser/query identities must match; the existing
   implementation hash intentionally produces different cache namespaces.
   This patch caps enumeration and may avoid caching large results, so repeated
   cold parsing is a possible tradeoff. End-to-end improvement is a hypothesis.
   Cache OFF and default profiles are controls, not evidence of an active gain.
6. Report independent goal acceptance, correctness of edits and regressions;
   input/output tokens and known cost **through success including retries**,
   planning, tools and judging; wall time through success and non-overlapping
   stages; context completeness at both extraction and projection layers.
   Unknown cost is unknown, failed/capped tasks remain visible, and unsuccessful
   tasks do not get zero cost or imaginary success time. Report paired success
   rates, distributions/uncertainty and censored failures, not only averages of
   successful runs. Record context's selected files, byte/tag caps, truncation,
   retained/projection omission counts, unknown/unavailable and acceptance-relevant
   evidence coverage. `omitted_symbols` counts retained tags excluded from views,
   not all unparsed symbols. Do not interpret lexical references as resolved calls
   or definitions as proven public contracts.

This work changes only Aider. Backend/systems integration, production pin,
flags, VPS, databases, release/tag/merge/deployment and paid model/Serper runs
were not performed. Future comparison is deferred and does not block draft review.
