---
id: HOSTME-IDEA-002
title: Keep file times on upload; HTML gets Last-Modified
created: '2026-10-28T14:39:53+00:00'
source_project: sitegen
source_path: /Users/bolandau/Work/products/sitegen
status: epic
benefit: Every hosted site gets the right page dates in Yandex results.
triage:
  serves: []
  risks: []
  why: Sites lose their page dates without Last-Modified; Yandex takes page date from
    it.
  score: 5.0
  route: task
  at: '2026-11-11T12:29:21+00:00'
epic: E-002
before_epic: new
---

Yandex takes the date of a page from the Last-Modified header. Sitegen will set each built page's file time from its document date; the upload (server and ftp/sftp/ssh targets) must keep file times, and nginx must send Last-Modified for HTML.
