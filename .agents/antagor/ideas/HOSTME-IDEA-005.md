---
id: HOSTME-IDEA-005
title: Own certificate instead of Let's Encrypt
created: '2026-11-11T13:04:16+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: new
---

PRD §5/§6 promised `hostme <domain> ssl --cert PATH --key PATH` to put a certificate the human already owns in place of a Let's Encrypt one. `hostme help` lists it as not implemented in MVP. Needed when a client brings a wildcard or an EV certificate, or when Let's Encrypt rate limits or the DNS-01 step block an issue. Today the only path is a manual Webinoly command on the server.
