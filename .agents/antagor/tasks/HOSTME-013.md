---
id: HOSTME-013
title: Switch a live site between HTML and PHP from the config command
status: publish
attempts: 0
blocked: true
blocked_reason: environment_broken
phase: null
tests_hash: null
publish_stage: gate
created_by: architect
approved_by: human
approved_words: Все согласовано.
worker: pi
type: feature
owns_paths:
- src/hostme/commands/site.py
- src/hostme/core/services.py
- src/hostme/providers/webinoly.py
- tests/snapshots
- src/hostme/commands/doctor.py
- src/hostme/core/doctor.py
- src/hostme/data/SKILL.md
test_paths:
- tests/unit/test_services.py
- tests/unit/test_webinoly.py
- tests/e2e
- tests/unit/test_cli.py
- tests/unit/test_data_dirs.py
- tests/unit/test_doctor.py
docs:
- docs/usage/webinoly.md
- docs/usage/product.md
- docs/adr
tools: []
worker_args: null
class: standard
decision: true
visual: null
depends_on: []
budget_usd: null
epic: E-006
spec_refs: []
checks:
- python3 scripts/check_command_docstrings.py
resident: null
tool: null
pr: null
---

Facts from the live case (2026-11-12, net-angel-vps, bolandau.ru): Webinoly has no in-place type switch; the sysadmin had to remove the site, create it again with the PHP flag, and re-attach SSL by hand. The removal keeps the certificate only when revocation is off, and it takes the whole site directory with it - content, placeholder index, CORS snippet, redirects, custom nginx snippet. So a naive implementation loses data.
Add the flags to the existing per-domain config command: --php and --html. Sequence in the provider: snapshot the site directory, remove the site without revoking the certificate, create it again with the new type, restore the snapshot into the releases layout, re-attach the existing certificate, then verify the post-condition. Any failure on the way restores the previous type and content.
A site that already has the requested type: change nothing, report it, exit 0. The switch needs the confirmation gate: the site is down between removal and verification.

## Acceptance

- Given a live HTML site with content and a certificate, When the type is switched to PHP, Then the content tree is identical to the snapshot and the site answers over HTTPS. [check: tests/unit/test_webinoly.py]
- Given a site that already has the requested type, When the switch runs, Then nothing changes and the command reports that. [check: tests/unit/test_services.py]
- Given a removal that fails, When the switch runs, Then the previous type and content are back and the command fails. [check: tests/unit/test_webinoly.py]

## How to test

Level: unit on the command sequence and on the rollback decision, with the remote runner faked, plus the existing e2e file set on a real server. Data: a site with one release and a certificate; a second run with the same type; a removal that fails halfway. Live check needs a prepared server and a base domain whose A record points at it.

## Basis

Reuse delete_site with revoke off, create_site, enable_ssl, ensure_releases_layout and switch_release in the Webinoly provider; reuse require_confirmation and the guard in output for the confirmation gate; follow update_site_config in the service as the place the flags land.

## Read first

- `docs/research/2026-09-08-webinoly-behaviour.md`
- `docs/usage/webinoly.md`

## Out of scope

- Changing the type of a target deploy.
- Preserving MySQL databases or PHP settings that belong to the removed site: Webinoly creates them fresh.
