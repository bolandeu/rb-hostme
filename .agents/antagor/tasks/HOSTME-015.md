---
id: HOSTME-015
title: A placeholder certificate is a failed deploy, and SSL can be retried later
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
- src/hostme/providers/webinoly.py
- src/hostme/core/services.py
test_paths:
- tests/unit/test_webinoly.py
- tests/unit/test_services.py
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
epic: E-007
spec_refs: []
checks:
- python3 scripts/check_command_docstrings.py
resident: null
tool: null
pr: null
---

Live case, p2g-1, 2026-11-12. A site was created and its certificate step failed (no Let's Encrypt contact). Webinoly left its placeholder certificate: CN=blackhole, self-signed. The next deploy saw a certificate present, reused it, and reported Deployed to https://... with ok true, while every client gets a certificate error. A later retry to repair it fails too: the releases layout makes htdocs a symlink, and Webinoly's acme-challenge location runs with disable_symlinks on, so Let's Encrypt gets 404 and no certificate is issued. Only a full teardown and a fresh create recovered (verified: after teardown and redeploy the site answered 200 with a Let's Encrypt certificate).
Fix: treat a placeholder certificate as a failure of the deploy and say so; make SSL repair possible on an existing site instead of requiring a teardown - put the acme challenge path where the symlink does not block it, then retry the certificate.

## Acceptance

- Given a site whose certificate is the Webinoly placeholder, When it is deployed, Then the command fails with a message that names the certificate, and the JSON envelope is not ok. [check: tests/unit/test_webinoly.py]
- Given a site with a placeholder certificate, When the certificate is repaired, Then the site serves a Let's Encrypt certificate without a teardown. [check: tests/unit/test_services.py]

## How to test

Level: unit on the decision and the command sequence with the remote runner faked; live on a prepared server by breaking the certificate first. Data: a site with the blackhole certificate, a healthy site, a site after repair.

## Basis

Reuse enable_ssl, delete_site and ensure_releases_layout in the Webinoly provider; follow the deploy service flow in services where the site is created and SSL is enabled.

## Read first

- `docs/research/2026-09-08-webinoly-behaviour.md`

## Out of scope

- Recovering sites whose certificate expired: the expiry path stays as it is.
- Any change to the releases layout beyond what the certificate path needs.
