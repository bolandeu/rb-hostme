---
id: HOSTME-IDEA-013
title: 'Manual check: hostme from an agent shell, no TTY'
created: '2026-11-11T13:31:35+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: taken
triage:
  serves: []
  risks: []
  why: The agent contract is what every foreign project relies on; a hang without
    TTY would surface only in someone else's project.
  score: 3.0
  route: task
  at: '2026-11-11T13:31:38+00:00'
task: HOSTME-010
taken_project: hostme
linked: true
---

Left over from TODO.md line 103: run hostme from a Claude Code (or script) call with no interactive shell and confirm it does not hang and returns sane JSON and an exit code. The living doc docs/usage/agent-contract.md states the contract; nothing checks it live.
