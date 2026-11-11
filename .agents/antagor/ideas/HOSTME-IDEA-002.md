---
id: HOSTME-IDEA-002
title: Keep file times on upload; HTML gets Last-Modified
created: '2026-10-28T14:39:53+00:00'
source_project: sitegen
source_path: /Users/bolandau/Work/products/sitegen
status: new
benefit: Every hosted site gets the right page dates in Yandex results.
triage:
  serves:
  - P6
  risks: []
  why: 'sitegen sets a page date in its file time and Yandex reads it from Last-Modified:
    the upload must not lose that time, a small change for correct page dates'
  score: 5.0
  route: task
  at: '2026-11-11T12:22:09+00:00'
---

Yandex takes the date of a page from the Last-Modified header. Sitegen will set each built page's file time from its document date; the upload (server and ftp/sftp/ssh targets) must keep file times, and nginx must send Last-Modified for HTML.
