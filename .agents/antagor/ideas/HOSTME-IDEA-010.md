---
id: HOSTME-IDEA-010
title: 'E2E: a PHP site really runs PHP'
created: '2026-11-11T13:18:55+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: new
---

Phase 1.8 of the old plan (TODO.md, now deleted): there is no e2e test for a PHP site. Deploy a folder with a .php file through the CLI, then curl the URL and check that the PHP output comes back, not the source text. Still wanted: the php/html site type decides -php vs -html in Webinoly create_site, and no test proves PHP-FPM serves it.
