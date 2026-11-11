---
id: HOSTME-IDEA-003
title: Brotli for hosted static sites
created: '2026-10-28T14:39:54+00:00'
source_project: sitegen
source_path: /Users/bolandau/Work/products/sitegen
status: new
benefit: Smaller pages and faster loading for every hosted site.
triage:
  serves: []
  risks: []
  why: Smaller pages for every hosted site; blocked by the nginx build on the servers,
    so it waits.
  score: 2.0
  route: task
  at: '2026-11-11T12:29:23+00:00'
---

nginx on the hosting is built without the Brotli module (docs/webinoly.md), so pages go only with gzip. Add Brotli when the module can be added.
