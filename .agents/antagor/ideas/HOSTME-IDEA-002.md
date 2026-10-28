---
id: HOSTME-IDEA-002
title: Keep file times on upload; HTML gets Last-Modified
created: '2026-10-28T14:39:53+00:00'
source_project: sitegen
source_path: /Users/bolandau/Work/products/sitegen
status: new
benefit: Every hosted site gets the right page dates in Yandex results.
---

Yandex takes the date of a page from the Last-Modified header. Sitegen will set each built page's file time from its document date; the upload (server and ftp/sftp/ssh targets) must keep file times, and nginx must send Last-Modified for HTML.
