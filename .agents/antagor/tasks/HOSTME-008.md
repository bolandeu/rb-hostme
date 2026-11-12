---
id: HOSTME-008
title: 'E2E from zero: server add, server init, deploy, SSL'
status: in_review
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
- tests/conftest.py
test_paths:
- tests/e2e/
docs: none
tools: []
worker_args: null
class: standard
decision: false
visual: null
depends_on:
- HOSTME-007
budget_usd: null
epic: E-003
spec_refs: []
checks: manual
resident: null
tool: null
pr: null
translation: 'E2E с нуля: server add, server init (Webinoly ставится впервые), деплой
  статики и проверка HTTPS. Требует чистый VPS, ключ и домен с A-записью на него.'
---

`hostme server init` (Webinoly install + enable sftp) never runs in a test: every e2e assumes Webinoly is already installed on the server. So the one path a new user walks first — `server add`, `server init`, deploy, SSL — is untested from zero.

Needs a clean server (the Human prepares it, see the epic card «Infrastructure»): an untouched Ubuntu LTS VPS with the SSH key and passwordless sudo, plus a domain or subdomain whose A record already points at it, because Let's Encrypt validates over HTTP-01.

Work: an e2e marked `-m e2e` that registers the server (`hostme server add`), runs `hostme server init`, adds the base domain, deploys a static folder and checks the site answers over HTTPS. Env vars: HOSTME_E2E_HOST, HOSTME_E2E_USER, HOSTME_E2E_BASE_DOMAIN, HOSTME_E2E_SSH_KEY.

## Basis

Follow the existing e2e style and the -m e2e marker; use the CLI for every step.

## Read first

- `tests/conftest.py`
- `src/hostme/core/services.py`
- `docs/usage/servers-and-domains.md`

## Out of scope

- Preparing the VPS or its DNS: the Human does that before the run.
- No product code change; a failure becomes its own bugfix task.
