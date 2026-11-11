---
id: HOSTME-IDEA-011
title: 'E2E: server add + server init on a clean server'
created: '2026-11-11T13:19:27+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: new
---

Phase 1.8 of the old plan (TODO.md, now deleted): the e2e tests assume Webinoly is already installed, so server init (webinoly_install + enable_sftp) never runs in a test. Add an e2e that registers an untouched Ubuntu server and runs server init from zero. Still wanted, but only when a spare clean server exists: a fresh VPS is not available now, and the check costs a full Webinoly install.
