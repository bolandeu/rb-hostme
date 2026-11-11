---
id: HOSTME-006
title: 'Target deploy docs: swap, idempotence, page dates'
status: queue
attempts: 0
blocked: false
blocked_reason: null
phase: null
tests_hash: null
publish_stage: null
created_by: architect
approved_by: human
approved_words: Согласован
worker: pi
type: docs
owns_paths:
- docs/usage/servers-and-domains.md
test_paths: []
docs:
- docs/usage/servers-and-domains.md
tools: []
worker_args: null
class: mechanical
decision: false
visual: null
depends_on:
- HOSTME-004
- HOSTME-005
budget_usd: null
epic: E-002
spec_refs: []
checks: manual
resident: null
tool: null
pr: null
translation: 'Раздел про target в docs/usage/servers-and-domains.md: порядок staging-заливки
  и swap, что сбой не меняет живой сайт, идемпотентность повторного деплоя, сохранение
  времени файлов и готовая команда проверки Last-Modified.'
---

docs/usage/servers-and-domains.md says how a target deploy works, but not what the swap guarantees and not how a deployed page's date is checked. Bring it in line with the code the two provider tasks leave behind.

Write, in the target section:
- the deploy order: snapshot to target-backups, upload into a staging directory, swap by renames, old copy removed; a failed or stopped run leaves the live folder as it was;
- that a repeat deploy is idempotent and removes files that are gone locally (mirror --reverse --delete, rsync --delete);
- file times: the upload keeps the time of each local file (rsync -a, lftp mirror with ftp:use-mdtm/use-site-utime2), so a built page keeps its document date;
- how the Human checks a served page's date, as a ready command: `curl -sI https://<domain>/ | grep -i last-modified` and what the answer must show (the time of the local file, in GMT);
- what nginx does by default with static files (sends Last-Modified from the file time), and that hostings which cache in front may rewrite it.

Keep the file's style: short sentences, ready commands, no promises about code that does not exist.

## Acceptance

- Given the target section of docs/usage/servers-and-domains.md, When it is read, Then it states the staging-and-swap order, that a failed run leaves the live folder unchanged, and that a repeat deploy removes files deleted locally. [check: manual]
- Given the page-date part, When the Human runs the quoted curl command against a deployed site, Then the doc says which header and value must come back. [check: manual]

## Read first

- `src/hostme/providers/ftp.py`
- `src/hostme/providers/ssh.py`

## Out of scope

- No code or test change; no new command.
- Nothing about Brotli or caching headers beyond Last-Modified.
