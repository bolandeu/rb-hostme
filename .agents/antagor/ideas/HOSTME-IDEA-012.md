---
id: HOSTME-IDEA-012
title: Unit tests for an ambiguous server resolve
created: '2026-11-11T13:19:27+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: taken
task: HOSTME-009
taken_project: hostme
linked: true
---

Phase 2.1 of the old plan (TODO.md, now deleted): resolve_server has tests for a few servers (explicit --server, a known site domain, one base-domain suffix match) but none for the ambiguous cases: two servers that both claim the same base domain, and two base domains that both match a new subdomain. Write unit tests, then decide which server wins and document that in docs/usage/servers-and-domains.md. Still wanted: today the first match wins by list order, and no test or doc says so.
