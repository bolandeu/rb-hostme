---
id: HOSTME-IDEA-008
title: -proxy= sites for a non-PHP app behind nginx
created: '2026-11-11T13:04:51+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: new
---

PRD §10/§11 kept Webinoly `-proxy=` (reverse proxy to Node, Java or another local process) outside the scope: hostme serves static files and PHP only. A site that needs a small backend now lives outside hostme entirely. Add it as a third site type when such a site appears: Webinoly already has the flag, hostme needs a port and a process to start on the server.
