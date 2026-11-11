---
id: HOSTME-001
title: 'TODO.md: open items become ideas, the file goes'
status: ideas
attempts: 0
blocked: false
blocked_reason: null
phase: null
tests_hash: null
publish_stage: null
created_by: architect
approved_by: null
worker: pi
type: docs
owns_paths:
- TODO.md
- AGENTS.md
test_paths: []
docs:
- TODO.md
tools: []
worker_args: null
decision: false
visual: null
depends_on: []
budget_usd: null
epic: E-001
spec_refs: []
checks: manual
resident: null
tool: null
pr: null
---

TODO.md is a plan kept as a file, which the doc kinds no longer allow. Read it, and for each open item add one idea with `antagor idea add` (or link it to an existing idea, epic or task when it is the same work). Items already done stay in git history. Delete TODO.md, and fix the links to it in AGENTS.md so no tracked .md points to a gone file. Report: each item of TODO.md -> the idea, epic or task it became.

## Acceptance

- Given the open items of TODO.md, when the task ends, then each one is an idea, an epic or a task, and the report names the item and its number [check: manual]
- Given TODO.md is deleted, when the task ends, then `rg -l 'TODO.md'` finds no tracked .md file [check: manual]

## Out of scope

- No code change
- No idea for work that already has a task or an epic
