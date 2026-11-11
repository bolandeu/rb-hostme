---
id: HOSTME-009
title: 'Ambiguous server resolve: decide, test, document'
status: done
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
type: feature
owns_paths:
- src/hostme/config.py
- docs/usage/servers-and-domains.md
test_paths:
- tests/unit/test_config.py
docs:
- docs/adr/
- docs/usage/servers-and-domains.md
tools: []
worker_args: null
class: standard
decision: true
visual: null
depends_on: []
budget_usd: null
epic: E-004
spec_refs: []
checks:
- python3 scripts/check_command_docstrings.py
resident: null
tool: null
pr: null
translation: 'Неоднозначный резолв сервера: решить правило (первый по списку или внятная
  ошибка с двумя именами), закрыть юнит-тестами оба случая, записать решение в ADR
  и одной строкой в docs/usage/servers-and-domains.md.'
---

resolve_server has tests for explicit --server, a known site domain and one base-domain suffix match, but none for the ambiguous cases: two servers that both claim the same base domain, and two base domains that both match a new subdomain. Today the first match wins by list order and nothing says so.

What must work from the user's side: a deploy never goes to a surprise server, and the doc answers «which server wins» before the user asks.

Work:
- decide the rule (keep first match by list order, or refuse the ambiguity with a clear error naming both servers) and write the decision in the ADR of this task;
- unit tests for both ambiguous cases;
- one line in docs/usage/servers-and-domains.md stating the rule.

## Acceptance

- Given two servers that claim the same base domain, When a deploy resolves a domain under it, Then the behaviour is the decided one and a unit test asserts it, naming both servers. [check: tests/unit/test_config.py]
- Given two base domains that both match a new subdomain, When the server is resolved, Then the same rule applies and a unit test asserts it. [check: tests/unit/test_config.py]
- Given docs/usage/servers-and-domains.md, When a reader looks for the rule, Then one sentence states it in the same order as the code. [check: python3 scripts/check_command_docstrings.py]

## How to test

level: unit; seam: config.resolve_server with two servers and overlapping base domains; data: a temp servers.yaml written by the test.

## Basis

Follow the resolution order already documented (--server, then a known site domain, then the base-domain suffix) and the ADR format in docs/adr/README.md.

## Read first

- `docs/usage/servers-and-domains.md`
- `tests/unit/test_config.py`
- `scripts/check_command_docstrings.py`

## Out of scope

- No new CLI command and no change to the documented order of the three steps.
- No server or deploy e2e: the earlier e2e tasks own that.
