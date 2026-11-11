---
id: HOSTME-002
title: TODO.md items become ideas; the done ones go
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
- README.md
test_paths: []
docs:
- TODO.md
- AGENTS.md
- README.md
tools: []
worker_args: null
class: mechanical
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

TODO.md (254 lines) is the implementation plan and progress backlog kept as a file; the layout check refuses it. Read all of it.
- Each unfinished item ("-" not struck, phase checkboxes open) -> one idea: antagor idea add --title ... --text ... --why it is still wanted; keep the phase name in the text. List the new ids in your report.
- Each finished item: check it against the code before you believe it (grep the command, the provider, the config key). Finished and in git -> nothing to keep; it goes on the dropped list with the reason "done, history in git".
- A statement that is a rule of work for the repository (how releases go, how Webinoly is checked, where secrets live) -> the living doc AGENTS.md already holds most of it: add what is missing there, do not start a new file.
Then delete TODO.md and fix every pointer to it (AGENTS.md, README.md, code docstrings, .agents/antagor/ files).
The report is a table: each TODO item -> idea id / living doc / dropped with reason. Nothing is deleted before the Human sees that table.

## Read first

- `.agents/antagor/antagor.toml`

## Out of scope

- No code or CLI behaviour change.
- Do not edit .agents/antagor/antagor.toml.
- Delete nothing before the Human reads the table: the deletion is this task's last step and the report lists each dropped item.
