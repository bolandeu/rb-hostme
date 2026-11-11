---
id: HOSTME-005
title: 'ssh target deploy: staging upload, rename swap, no mixed site'
status: done
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
type: feature
owns_paths:
- src/hostme/providers/ssh.py
test_paths:
- tests/unit/test_ssh.py
docs:
- docs/usage/
tools: []
worker_args: null
class: standard
decision: false
visual: null
depends_on: []
budget_usd: null
epic: E-002
spec_refs: []
checks:
- python3 scripts/check_command_docstrings.py
resident: null
tool: null
pr: null
translation: 'Заливка на ssh-таргет: rsync в staging-папку, затем переименование live→old,
  staging→live, при сбое live не меняется; относительные пути shared-хостингов сохраняются;
  время файлов (-a) сохраняется.'
---

rsync_to_target copies straight into remote_path, so a broken connection or a full disk leaves old and new files mixed on a live site. Make it whole or nothing, mirroring what the ftp/sftp task does, with the same wording in the docstrings.

The contract:
- rsync the folder into a sibling staging directory (`<remote>.hostme-staging-<ts>`), never into remote_path.
- Swap with renames in the same parent: live -> old, staging -> live; if the second rename fails, rename old back and raise SshError, so the visitor sees no change.
- A missing live directory on first deploy is not an error; keep the paths relative when remote_path is relative (shared hostings).
- After a successful swap remove the old copy and any stale staging/old directories of earlier failed runs.
- Every ssh/rsync command goes through the existing providers/ssh.py helpers (run_remote / _run_target_rsync, same transport and env as today); no new subprocess seam.
- Assert in tests that the rsync call keeps file times (`-a`, which carries `-t`) and that the destination is the staging path.

## Acceptance

- Given a target deploy over ssh, When rsync fails or times out mid-upload, Then remote_path still holds exactly the previous files and the error is an SshError. [check: tests/unit/test_ssh.py]
- Given a successful deploy, When the swap finishes, Then remote_path holds the new files and no staging or old directory stays behind. [check: tests/unit/test_ssh.py]
- Given a relative remote_path on a shared hosting, When the swap runs, Then the staging and old paths stay relative, next to remote_path. [check: tests/unit/test_ssh.py]
- Given the rsync call, When its arguments are inspected, Then the archive flag carrying file times is present and the destination is the staging directory. [check: tests/unit/test_ssh.py]

## How to test

level: unit; seam: providers.ssh.rsync_to_target with a fake rsync and ssh on PATH that record argv and can fail at the Nth call; data: a temp folder with two files and an ssh target fixture.

## Basis

Reuse _target_ssh_transport, _run_target_rsync, _target_remote_path and the quoting already in providers/ssh.py; keep the docstring style of rsync_to_target.

## Read first

- `src/hostme/core/services.py`
- `docs/usage/servers-and-domains.md`

## Out of scope

- The ftp/sftp path (its own task) and server deploys (releases/rollback).
- Rollback command for targets; retries.
