---
id: HOSTME-IDEA-014
title: Change the site type of an existing site (html to php, php to html)
created: '2026-11-12T07:33:53+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: new
---

Today the type is fixed at creation: Webinoly refuses to create over an existing site, and hostme has no command to switch it. Every such case ends with remove-and-recreate: site teardown keeps the files but loses the placeholder index and forces the certificate step again. Cost: a live site goes 403 at the root while the operator walks the remove/create/ssl sequence by hand (2026-11-12, bolandau.ru, work done by the sysadmin outside hostme). What the product needs: one command that flips the type, keeps the content and the certificate, and reloads nginx.
