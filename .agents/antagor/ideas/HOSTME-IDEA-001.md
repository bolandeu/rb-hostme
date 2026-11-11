---
id: HOSTME-IDEA-001
title: Target upload is whole or nothing
created: '2026-10-28T14:39:53+00:00'
source_project: sitegen
source_path: /Users/bolandau/Work/products/sitegen
status: new
benefit: Target deploys become whole or nothing, as server deploys with releases and
  rollback already are.
triage:
  serves:
  - P1
  risks: []
  why: an interrupted target deploy leaves the live site half old and half new, the
    one gap where a target deploy is weaker than a server deploy with releases
  score: 6.0
  route: task
  at: '2026-11-11T12:22:05+00:00'
---

An upload to a third-party host (ftp, sftp, ssh) writes into the live folder, so a stopped or failed run leaves old and new files mixed on the site.
