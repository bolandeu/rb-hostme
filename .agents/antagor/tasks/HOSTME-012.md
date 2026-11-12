---
id: HOSTME-012
title: Refuse to call a half-installed Webinoly a success
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
- src/hostme/providers/webinoly.py
- scripts/provision-server.sh
test_paths:
- tests/unit/test_webinoly.py
docs:
- docs/usage/webinoly.md
- docs/research/2026-09-08-webinoly-behaviour.md
tools: []
worker_args: null
class: standard
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

Live case from the sysadmin brief, Ubuntu 26.04 on NetAngels: the installer script weby downloads webinoly.tar, and on that host the download stops after about 12 KB (the full archive is 829440 bytes). tar reports Unexpected EOF, the extraction leaves two files in the install directory, no nginx and no php. weby has no set -e, so it prints installed successfully and then dies on app_purge: command not found. The same URL from another host returns the full archive, so this is a network fault on one machine, not geoblocking.
The product repeats the mistake: the install step trusts the exit code of the bash weby run and reports the server ready. The installer wrapper script in the repository has the same gap.
Fix: make the install step verify its post-condition on the server before it returns - the webinoly command, nginx and php are present, otherwise raise the provider error naming the incomplete install and the truncated-download cause. The wrapper script runs the same verification and exits non-zero with a loud message. The truncated-download fact goes into the research note; the verified post-condition into the usage doc.

## Acceptance

- Given a server where the Webinoly install left no nginx, no php and no webinoly command, When the install step returns, Then it raises a provider error that says the install is incomplete. [check: tests/unit/test_webinoly.py]
- Given a server where the installer printed success and the commands are present, When the install step returns, Then it reports success and no error is raised. [check: tests/unit/test_webinoly.py]

## How to test

Level: unit, on the command strings and the verification decision, with the remote runner faked - the same style the adapter tests already use. Data: one successful install output and one truncated install where the commands are absent. A live run needs a clean VPS and stays out of this task.

## Basis

Reuse install, is_installed and WebinolyError in the webinoly provider; the verification is one more remote command in the same install step. Follow the existing tests around install in the unit test file for the fake-runner style.

## Read first

- `docs/research/2026-09-08-webinoly-behaviour.md`

## Out of scope

- Finding out why one VPS truncates the download.
- Retrying the download or carrying the archive from another host: the workaround the sysadmin used stays manual.
- Changing what Webinoly does to a server.
