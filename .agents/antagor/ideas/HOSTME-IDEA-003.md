---
id: HOSTME-IDEA-003
title: Brotli for hosted static sites
created: '2026-10-28T14:39:54+00:00'
source_project: sitegen
source_path: /Users/bolandau/Work/products/sitegen
status: new
benefit: Smaller pages and faster loading for every hosted site.
---

nginx on the hosting is built without the Brotli module (docs/webinoly.md), so pages go only with gzip. Narrow: hostme does not touch the server build — it checks whether the running nginx has Brotli and, when it does, serves the site with brotli on; adding the module to a Webinoly server is a separate ops decision of the Human (how, in docs/webinoly.md).
