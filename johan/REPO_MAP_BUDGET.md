# Optional repo-map hard limit

Set `AIDER_REPO_MAP_TOKEN_LIMIT=8192` in a controlled experiment, or pass
`map_token_limit=8192` directly to `RepoMap`. The environment is read at map
construction. Unset preserves existing behavior; zero disables the map.
Invalid or negative values fail configuration instead of silently raising cost.
No JAE configuration, install pin or live service is changed by this PR.

The existing `map_tokens` and no-files multiplier remain the ranking inputs.
The limit bounds the effective ranking budget AND the returned map text,
including `repo_content_prefix`, using the actual model tokenizer. This matters
because ranking uses token estimates and allows tolerance. If necessary, remove
trailing whole lines; never cut a line into partial source text. This can leave
a partial file section, since the map is an outline rather than compilable code.
If even the prefix plus one line cannot fit, return no map.

`last_map_metrics` records base/effective budget, hard limit, actual tokens,
clipping, number of files considered and elapsed milliseconds. It contains no
paths or code. With verbose mode these metrics are printed; without it they are
available to an embedding caller. Elapsed time includes rendering and token
counting, not model inference. No cache-hit attribution is claimed.

This limits only repo-map text: full files, chat history, system messages and
other context are not covered. It is not a complete context-window or monetary
budget. Model-window reservation remains the upstream heuristic. No claim of
better task success or lower total cost is made before live comparisons.

Offline regression command (stdlib only):

```sh
python -m unittest discover -s tests/basic -p test_repomap_budget.py -v
```

Tests execute the real get_repo_map method with the ranking/parser boundary
replaced, and a deterministic tokenizer. Full upstream parser/tokenizer tests
still require Aider dependencies; no paid provider call is needed.

Next separate steps: task-specific ranking, content-addressed reusable index,
different planner/executor views and search-based scope expansion. Compare
quality, total tokens to accepted result, failure rate and cold/warm map time
across multiple tasks before choosing a production limit.
