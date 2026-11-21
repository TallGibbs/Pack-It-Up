"""Which model did which job: a SQLite copy of every run's call log and Decisions API answers.

The run folders stay the source of truth. `store.sync()` copies `runs/<run_id>/calls.jsonl`,
`questions.json`, `status.json`, `manifest.json` and the perception files into `.cache/analysis.db`
(git-ignored), re-reading a run only when one of its files changed. `api.py` serves summaries to
`frontend/models.html`; `python -m backend.analysis` prints them.

Read-only: nothing here calls a model or writes into a run folder.
"""
