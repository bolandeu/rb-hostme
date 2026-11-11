---
id: HOSTME-IDEA-001
title: Target upload is whole or nothing
created: '2026-10-28T14:39:53+00:00'
source_project: sitegen
source_path: /Users/bolandau/Work/products/sitegen
status: epic
benefit: Target deploys become whole or nothing, as server deploys with releases and
  rollback already are.
triage:
  serves: []
  risks: []
  why: A stopped target deploy leaves a half-updated live site; atomicity is what
    server deploys already give (PRD §5).
  score: 8.0
  route: task
  at: '2026-11-11T12:29:20+00:00'
epic: E-002
before_epic: new
---

An upload to a third-party host (ftp, sftp, ssh) writes into the live folder, so a stopped or failed run leaves old and new files mixed on the site.
