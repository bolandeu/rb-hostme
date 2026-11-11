---
id: HOSTME-IDEA-003
title: Brotli for hosted static sites
created: '2026-10-28T14:39:54+00:00'
source_project: sitegen
source_path: /Users/bolandau/Work/products/sitegen
status: clarifying
benefit: Smaller pages and faster loading for every hosted site.
triage:
  serves:
  - P6
  risks: []
  why: smaller pages on every hosted site, and the narrowed fix changes nothing on
    a server without the module; whether to rebuild nginx is the Human's decision
  score: 2.0
  route: clarify
  at: '2026-11-11T12:22:33+00:00'
clarify_project: /Users/bolandau/Work/tools/hostme
clarify_since: '2026-11-11T12:22:33+00:00'
---

nginx on the hosting is built without the Brotli module (docs/webinoly.md), so pages go only with gzip. Narrow: hostme does not touch the server build — it checks whether the running nginx has Brotli and, when it does, serves the site with brotli on; adding the module to a Webinoly server is a separate ops decision of the Human (how, in docs/webinoly.md).
