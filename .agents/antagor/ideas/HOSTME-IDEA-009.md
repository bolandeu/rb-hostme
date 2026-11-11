---
id: HOSTME-IDEA-009
title: E2E tests call the hostme CLI, not the providers
created: '2026-11-11T13:18:55+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: taken
task: HOSTME-007
taken_project: hostme
linked: true
---

Phase 1.8 of the old plan (TODO.md, now deleted): tests/e2e/test_webinoly_smoke.py and test_webinoly_adapter.py call Webinoly through hostme.providers directly, not through the hostme CLI. Rewrite them to run the CLI in a subprocess, so the CLI grammar (_translate_argv), guards, exit codes and --json output are covered end to end. Still wanted: the tests today pass even if a command's argument parsing breaks.
