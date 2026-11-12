---
id: HOSTME-007
title: 'E2E through the CLI: smoke rewrite and a PHP site'
status: queue
attempts: 0
blocked: false
blocked_reason: null
phase: null
tests_hash: null
publish_stage: null
created_by: architect
approved_by: human
approved_words: нет на этой сносим на чистую где только что делали
worker: pi
type: chore
owns_paths:
- tests/e2e/
test_paths:
- tests/e2e/
docs: none
tools: []
worker_args: null
class: standard
decision: false
visual: null
depends_on: []
budget_usd: null
epic: E-003
spec_refs: []
checks: manual
resident: null
tool: null
pr: null
translation: 'E2E через сам CLI: смоук переписать на вызов hostme в subprocess, добавить
  PHP-сайт (curl проверяет вывод, а не исходник). Нужен живой тестовый сервер и базовый
  домен.'
---

The e2e tests call hostme.providers directly (tests/e2e/test_webinoly_smoke.py, test_webinoly_adapter.py), so the CLI surface is untested end to end: `_translate_argv` grammar, the guard on every command, exit codes and `--json` output can break silently.

What must work from the user's side: the same deploy that a foreign project does through the CLI is the thing under test.

Needs a live test server (the Human prepares it; see the epic card «Infrastructure»): a registered server, the base domain that points at it, and the two env vars HOSTME_E2E_HOST / HOSTME_E2E_USER.

Work:
- rewrite test_webinoly_smoke.py so it runs the `hostme` CLI in a subprocess instead of importing providers;
- add an e2e for a PHP site: a folder with a .php file, deploy it through the CLI, curl the URL and assert the PHP output, not the source;
- keep the `-m e2e` marker and the skip when the env vars are missing, exactly as tests/conftest.py does today.

## Basis

Keep tests/conftest.py env-var gate and the -m e2e marker; reuse the deploy/teardown grammar from src/hostme/cli.py.

## Read first

- `tests/conftest.py`
- `src/hostme/cli.py`
- `docs/usage/agent-contract.md`

## Out of scope

- No product code change; if the CLI turns out broken, report it and stop.
- The clean-server test (its own task).
