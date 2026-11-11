---
id: HOSTME-010
title: 'Agent-shell run: record the contract in action'
status: queue
attempts: 0
blocked: false
blocked_reason: null
phase: null
tests_hash: null
publish_stage: null
created_by: architect
approved_by: human
approved_words: Гоняй 04. 04.
worker: pi
type: chore
owns_paths:
- docs/usage/agent-contract.md
test_paths:
- none
docs:
- docs/usage/agent-contract.md
tools: []
worker_args: null
class: mechanical
decision: false
visual: null
depends_on: []
budget_usd: null
epic: E-004
spec_refs: []
checks: manual
resident: null
tool: null
pr: null
translation: 'Прогон без TTY из агентской оболочки: hostme --help, hostme list --json,
  hostme help --json, деплой с --json, teardown без --confirm (ожидаем отказ). Записать
  версию, команды, ответы и коды выхода в docs/usage/agent-contract.md.'
---

The agent contract (docs/usage/agent-contract.md) promises: no questions, --json output, exit codes, and no hang without a TTY. No test or record proves a real run from an agent shell.

What the Human must see: a short record in the doc's own words that the check was run, with the hostme version, the commands and the answers.

Work: run from a non-interactive shell (no TTY, no controlling terminal) at least: `hostme --help`, `hostme list --json`, `hostme help --json`, a deploy with --json on a throwaway path, and a teardown without --confirm expecting the refusal. Capture the exit codes. If anything hangs or answers nonsense, report it and stop: that becomes its own bugfix task. Otherwise add the record under a «Проверено» heading in the contract doc.

## Read first

- `tests/conftest.py`
- `src/hostme/cli.py`

## Out of scope

- No code change; a hang or a wrong answer becomes its own bugfix task.
- No automation of the run in CI.
