---
id: HOSTME-004
title: 'ftp/sftp target deploy: staging upload, rename swap, no mixed site'
status: publish
attempts: 1
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
- src/hostme/providers/ftp.py
- docs/usage/servers-and-domains.md
test_paths:
- tests/unit/test_ftp.py
docs:
- docs/adr/
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
translation: 'Заливка на ftp/sftp: сначала в соседнюю staging-папку, потом переименование
  (live→old, staging→live), при сбое live не меняется, старые staging/old убираются;
  время файлов сохраняется; решение записано в ADR.'
---

Today mirror_to writes straight into remote_path: an interrupted lftp run leaves old and new files mixed on a live site. Make one mirror_to call whole or nothing at the provider level, so callers (services.deploy_to_target, teardown_target) keep their shape.

The contract:
- Upload goes into a sibling staging directory, never into remote_path.
- Swap with renames in the same parent (same filesystem on the host): live -> old, staging -> live. If the second rename fails, rename old back to live and raise FtpError: the visitor's content must not change on failure.
- A missing live directory (first deploy) is not an error: nothing to rename.
- After a successful swap remove the old copy; remove stale staging/old directories of earlier failed runs at the start of a deploy.
- Keep the lftp script on stdin (password never in argv) and keep the existing `mirror --reverse --delete` semantics inside the staging upload.

File times: assert the lftp script keeps them — mirror without `--ignore-time` plus the explicit `set ftp:use-mdtm yes` and `set ftp:use-site-utime2 yes` lines; no `--no-perms` change that drops times.

Record the decision (first deploy, swap order, rollback of the swap, why not "upload in place with --delete") in an ADR: docs/adr/0010-*.md.

## Acceptance

- Given a target deploy over ftp or sftp, When lftp fails or times out during the upload, Then remote_path still holds exactly the previous files and the error is an FtpError. [check: tests/unit/test_ftp.py]
- Given a successful deploy, When the swap finishes, Then remote_path holds the new files, and staging and old directories are gone from the parent. [check: tests/unit/test_ftp.py]
- Given a first deploy to an empty parent, When the swap runs, Then a missing live directory is not an error. [check: tests/unit/test_ftp.py]
- Given the generated lftp script, When it is inspected, Then it sets ftp:use-mdtm and ftp:use-site-utime2 and does not pass --ignore-time, so file times survive. [check: tests/unit/test_ftp.py]

## How to test

level: unit; seam: providers.ftp.mirror_to with a fake lftp on PATH that records stdin and can fail at the Nth command; data: a temp folder with two files and a target fixture for ftp and sftp.

## Basis

Reuse the lftp script shape, _lftp_quote and _run_lftp in providers/ftp.py; backup snapshots in services._backup_target_before_deploy stay as they are; ADR format: docs/adr/README.md.

## Read first

- `src/hostme/core/services.py`
- `docs/usage/servers-and-domains.md`
- `docs/usage/webinoly.md`

## Out of scope

- The ssh target path (its own task) and any change to server deploys.
- Rollback command for targets; client-side retry logic.

## Feedback

### Attempt 1: the project's full check failed after the merge

The project's full check fails with this task merged into main, and passes without it: your change broke something elsewhere. Merge main into your branch and fix it within the task, or say what is outside it with `antagor inbox add`.

- `uvx --from "git+https://homeserver.tailee01ab.ts.net:3000/bolandeu/cli-generator.git@v1.27.3#subdirectory=gate" rb-release check`

```
release: gate step 'ruff format --check' failed:
…
_to_uploads_into_staging_not_into_remote_path():
--------------------------------------------------------------------------------
133 |
134 +
135 | def test_mirror_to_script_keeps_file_times():
--------------------------------------------------------------------------------
142 |
143 +
144 | def test_mirror_to_without_password_raises():
145 |     with pytest.raises(CliError, match="password"):
146 |         ftp.mirror_to("/local/path", make_target(password=None))
147 |
148 +
149 | def test_mirror_to_refuses_account_root_as_remote_path():
150 |     with pytest.raises(CliError, match="remote_path"):
151 |         ftp.mirror_to("/local/path", make_target(remote_path="/"))
152 |
153 +
154 | def test_mirror_to_raises_on_failure():
--------------------------------------------------------------------------------
160 |
161 +
162 | def test_mirror_to_timeout_raises():
--------------------------------------------------------------------------------
168 |
169 +
170 | def test_mirror_to_missing_lftp_raises():
--------------------------------------------------------------------------------
176 |
177 +
178 | @pytest.mark.parametrize("connection", ["ftp", "sftp"])
--------------------------------------------------------------------------------
195 |
196 +
197 | def test_mirror_to_first_deploy_needs_no_live_directory(fake_lftp, site_dir):
--------------------------------------------------------------------------------
204 |
205 +
206 | def test_mirror_to_failed_upload_keeps_previous_files(fake_lftp, site_dir, monkeypatch):
--------------------------------------------------------------------------------
218 |
219 +
220 | def test_mirror_to_failed_swap_returns_previous_files_and_raises(fake_lftp, site_dir, monkeypatch):
--------------------------------------------------------------------------------
232 |
233 +
234 | def test_check_target_maps_login_failure_to_invalid_and_keeps_password_off_argv():
    |

2 files would be reformatted, 110 files already formatted
release: code failed
```
