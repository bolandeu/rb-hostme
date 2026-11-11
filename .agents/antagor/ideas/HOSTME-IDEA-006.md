---
id: HOSTME-IDEA-006
title: Wildcard SSL without a manual DNS step
created: '2026-11-11T13:04:34+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: new
---

A base domain gets its wildcard certificate by hand: DNS-01 needs a TXT record at the registrar, so the human copies it (the checked live procedure was the file WILDCARD-SSL.md, now a research record). Every new base domain repeats the step, and a renewal that misses it takes all its subdomains off HTTPS. Automate it through the registrar or hosting API the human already has (Beget and the six NS servers were tried by hand).
