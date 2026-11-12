---
id: HOSTME-014
title: Server init leaves the Let's Encrypt contact and rsync on the machine
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
type: bugfix
owns_paths:
- src/hostme/core/services.py
- src/hostme/providers/webinoly.py
test_paths:
- tests/unit/test_webinoly.py
- tests/unit/test_services.py
docs:
- docs/usage/webinoly.md
- docs/usage/servers-and-domains.md
- README.md
tools: []
worker_args: null
class: standard
decision: false
visual: null
depends_on: []
budget_usd: null
epic: E-007
spec_refs: []
checks:
- python3 scripts/check_command_docstrings.py
resident: null
tool: null
pr: null
---

Live case, fresh Ubuntu 26.04, 2026-11-12. server init installed Webinoly and stopped there. Two consequences on the first deploy: the certificate step failed with Please, enter a valid email address (Webinoly wants the Let's Encrypt contact once per server), and the transfer failed with bash: rsync: command not found - a minimal Ubuntu image ships no rsync.
Fix in server init: set the Let's Encrypt contact (from project settings, one value; fail with a clear message when it is not configured and no contact is set on the server) and make rsync presence a post-condition - install it or refuse with a message that names the missing tool. Same post-condition style the Webinoly install check already uses.

## Acceptance

- Given a bare server and no configured contact, When server init runs, Then it sets the contact and does not fail at the certificate step. [check: tests/unit/test_webinoly.py]
- Given a server without rsync, When server init runs, Then rsync is present afterwards or the command fails naming it. [check: tests/unit/test_services.py]

## How to test

Level: unit on the command sequence with the remote runner faked. Data: a server without a contact, a server with one, a server without rsync. Live check needs a bare Ubuntu image; the e2e set on a prepared server stays green.

## Basis

Reuse verify_install and the provider error style in the Webinoly provider; reuse the settings loading in services. Follow the post-condition pattern added for the Webinoly install step.

## Read first

- `docs/usage/webinoly.md`

## Out of scope

- Contact address policy: which address the owner wants is a setting, not a decision of this task.
- Installing anything else the product does not use.
