---
id: HOSTME-IDEA-007
title: git push-to-deploy as a second way to publish
created: '2026-11-11T13:04:34+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: new
---

PRD §10/§11 named git push-to-deploy and CI integration as a possible later step: a push to a branch of the site repository deploys the folder the way `hostme <path> <domain>` does. Today every publish is a local command, so CI cannot publish a site and a second machine must repeat the local path by hand.
