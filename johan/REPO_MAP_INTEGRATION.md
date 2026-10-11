# Integrated candidate: budget, reusable symbols and generic scope

Combines draft PRs #3, #4 and #5 without merging johan or changing JAE's pin.
RepoMap constructor, imports and methods are reconciled in one source file.
All three features remain opt-in. Existing standalone documentation applies.

Local: 22 stdlib regressions and Python compilation. Full dependencies could
not be installed in the execution environment (pip could not resolve diskcache).
Real parser/tokenizer tests are added but their local execution is unverified.
The existing Johan CI installs Aider and runs tests/basic on Python 3.12/3.13;
that includes the new integration tests. Do not call the candidate validated
until CI and the existing JAE smoke actually succeed.

Real integration covers Python and JavaScript symbol extraction, tiktoken
counting of returned map including prefix, scope ranking, reuse across clones,
path rebinding, same-mtime edits, disabled defaults and cache-directory rejection.
There are no paid model calls. Tokenizer vocabulary retrieval may require network.

No live speed/success/cost improvements have been measured. Missing cache and
scope metrics mean not observed, not zero. The logical cache payload limit is
not a filesystem quota; the repo-map ceiling is not a whole-request ceiling.

If this combined PR is accepted, it supersedes implementation PRs #3–#5;
do not also merge those separately. A subsequent JAE integration should update
the install pin deliberately, keep settings disabled, run install/runtime smoke,
then compare feature settings on the same tasks and source revisions. Defaults
should change only after observed acceptance, total-cost and timing results.
