---
id: HOSTME-011
title: Pin typer below 0.29 so a fresh install starts
status: done
attempts: 0
blocked: false
blocked_reason: null
phase: null
tests_hash: null
publish_stage: null
created_by: architect
approved_by: human
approved_words: Запускай
worker: pi
type: bugfix
owns_paths:
- pyproject.toml
- uv.lock
test_paths:
- tests/unit/test_cli.py
docs: none
tools: []
worker_args: null
class: mechanical
decision: false
visual: null
depends_on: []
budget_usd: null
epic: E-005
spec_refs: []
checks:
- python3 scripts/check_command_docstrings.py
resident: null
tool: null
pr: null
---

Facts from the sysadmin brief: on homeserver a clean uv tool install pulled typer 0.29.1 and hostme 0.6.x died on import with TypeError: TyperOption.__init__() missing 1 required keyword-only argument: type_descriptor. Older 0.6.1 died the same way because a forced reinstall rebuilds the dependencies. The code builds TyperOption with the argument list of typer 0.27.x.
Fix: give the typer requirement an upper bound (below 0.29) and refresh the lock. Do not touch the skill command code in this task.

## Acceptance

- Given the pinned requirement, When the wheel is installed into a clean environment, Then hostme --help exits 0 and typer resolves to 0.27.x. [check: tests/unit/test_cli.py]

## How to test

Level: packaging, not unit. Seam: the installed console script. Build the wheel, install it into a clean environment with no constraint file, run hostme --help, report the resolved typer version in the result.

## Out of scope

- Porting the code to the typer 0.29 option API.
- The constraint file the sysadmin keeps on homeserver: that machine stays with the sysadmin.
