---
id: HOSTME-016
title: Ruff format the Webinoly provider after HOSTME-013
status: publish
attempts: 0
blocked: true
blocked_reason: environment_broken
phase: null
tests_hash: null
publish_stage: gate
created_by: architect
approved_by: human
worker: pi
type: chore
owns_paths:
- src/hostme/providers/webinoly.py
test_paths:
- tests/unit/test_webinoly.py
docs: none
tools: []
worker_args: null
class: mechanical
decision: false
visual: null
depends_on: []
budget_usd: null
epic: E-006
spec_refs: []
checks:
- python3 scripts/check_command_docstrings.py
resident: null
tool: null
pr: null
---

HOSTME-013 was merged with src/hostme/providers/webinoly.py not formatted: the commit has a single blank line between top-level definitions where ruff format wants two, so ruff format --check reports 1 file would be reformatted and the publish gate fails before the tag. Run ruff format on that file only and commit. No behavior change: the diff is blank lines. Do not reformat other files.

## Acceptance

- Given the provider as committed, When ruff format runs, Then a second run changes nothing and the unit tests pass. [check: tests/unit/test_webinoly.py]

## How to test

Level: the gate itself. Seam: uv run ruff format --check src/hostme/providers/webinoly.py, then the project checks. Data: the file as committed on main.

## Out of scope

- Any other file, and any change to code inside the file.
