---
id: HOSTME-002
title: PRD.md and the three reference docs become living docs
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
- PRD.md
test_paths: []
docs:
- PRD.md
- WILDCARD-SSL.md
- docs/surge-cli.md
- docs/webinoly.md
tools: []
worker_args: null
decision: false
visual: null
review: true
depends_on: []
budget_usd: null
epic: E-001
spec_refs: []
checks: manual
resident: null
tool: null
pr: null
---

PRD.md is a spec, but it also holds a plan: the phased plan and the open questions.
The four docs are already declared living by the Architect on main; do not touch the Antagor config.
In PRD.md drop what is a plan rather than a spec: the phased plan and the open questions; an item that is still real becomes an idea with `antagor idea add`, and the PRD keeps no backlog.
Run `antagor layout check` at the end.

## Acceptance

- Given the four docs, when the task ends, then `antagor layout check` lists no docs to sort [check: manual]
- Given PRD.md, when the task ends, then it holds no phase plan and no open questions, and each item that left is an idea or is named as dead in the report [check: manual]

## Read first

- `AGENTS.md`

## Out of scope

- No rewrite of the technical facts of webinoly.md, surge-cli.md or WILDCARD-SSL.md
- No code change
- No edit of the Antagor config
