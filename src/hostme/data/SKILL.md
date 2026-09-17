---
name: hostme
description: "Deploy static/PHP sites (built landing pages, client sites, previews, artifacts that need a real URL) via `hostme` — a personal surge.sh-alike CLI. Deploys to the user's own VPS (--server, full lifecycle) or a registered third-party ftp/sftp/ssh hosting (--target, file transfer only — needs the user's explicit go-ahead per deploy, see below). Use whenever the user wants a local folder published/hosted/deployed to a real domain, not just previewed locally. Not for anything with a backend process (Node/API servers) — hostme only serves static files and PHP."
metadata:
  version: 1.2.0
---

# hostme

Personal CLI (repo: `~/Projects/hostme`, full spec in that repo's
PRD.md/TODO.md) that deploys a local folder to the user's own VPS through
Webinoly (nginx+php-fpm), with SSL always on. One command, no accounts, no
platform lock-in — the self-hosted analog of `surge.sh`.

This doc is bundled with the package itself (`src/hostme/data/SKILL.md`), not
maintained by hand in `~/.claude/skills/` — see "Staying in sync" below for
why that matters.

## First: get the live command reference, don't guess

The command surface evolves; don't hardcode it here. Before doing anything,
run:

```
hostme --json help
```

(`hostme help --json` works identically — see "`--json` works in either
position" below.) This returns the authoritative list of commands with usage
+ description, and notes what's explicitly NOT implemented (e.g. `discard`,
custom `ssl`, git push-to-deploy). Trust that output over anything below if
they conflict — this file can go stale, `hostme help` cannot (it's generated
from the same code that runs the commands).

If you can execute the CLI but can't read files from disk (sandboxed shell,
remote exec with no filesystem access to this installed skill), run
`hostme --ai` instead — it prints this exact document to stdout.

## The one thing that will trip you up: command order

This CLI's grammar is **not** standard subcommand-first. It copies surge.sh:

```
hostme <path> [domain] [--server NAME]     # deploy — NO "deploy" keyword
hostme <domain> <subcommand> [...]          # manage — DOMAIN FIRST, not the subcommand
```

So it's `hostme mysite.com teardown`, never `hostme teardown mysite.com`. If
you type the subcommand first, `hostme` silently reinterprets it as a deploy
whose local path is literally named after the subcommand (e.g. "teardown") —
it won't error usefully, it'll just do the wrong thing. When in doubt, check
`hostme --json help` for the exact `usage` string of the command you want.

## Quick path: deploy a build output

```
hostme ./dist                    # domain auto-generated from folder name + default base domain
hostme ./dist mysite.com --server vps1   # explicit domain, needed the first time for a domain not already known
```

If no domain is given and there's no default base (wildcard) domain
registered yet, it errors and tells you to pass one explicitly or run
`hostme domain add` first — don't guess a domain, surface that error to the
user.

Deploy is idempotent and keeps release history (`hostme <domain> revs`,
`rollback`, `rollfore`) — redeploying the same domain never loses the
previous version, it's just a symlink swap away.

## Always use `--json`

```
hostme --json <...>
```

Every command then prints one JSON object to stdout on success
(`{"ok": true, ...}`) or to stderr on failure (`{"ok": false, "error":
{"code": "...", "message": "...", "action": "..."}}` — `action`, when
present, is the concrete next command to run), with a non-zero exit code on
failure. Parse the `error.message`/`error.code` fields, not a bare string —
this is a breaking change from an earlier version of `hostme` that used
`{"ok": false, "error": "text"}`.

### `--json` works in either position

`--json`/`--non-interactive`/`--dry-run` can go **before or after** the
command (`hostme --json list` and `hostme list --json` are equivalent) —
you don't need to remember which form a given call needs. They can also mix
with each other in any order.

`--json` implies non-interactive (same as passing `--non-interactive`
explicitly) — no command blocks on stdin under `--json`. But `--json` does
**not** skip confirmation on destructive commands (`teardown`/`rollback`/
`maintenance`, own server or `--target` alike): without `--yes`/`-y` they
fail with a `CONFIRMATION_REQUIRED` error instead of either prompting or
silently proceeding. Always get the user's explicit go-ahead for that
specific domain before adding `--yes` yourself — see the destructive-ops
section below.

Use `--dry-run` to preview what a destructive command would do (prints the
same shape of result with `"dry_run": true`, no confirmation needed, nothing
changes) before actually running it with `--yes`.

`hostme --json doctor` checks environment readiness (required binaries —
`ssh`/`rsync`/`lftp`/`sshpass` as needed, config file permissions/
parseability, declared ssh keys present on disk) without contacting any
remote server — cheap to run first if a command is failing mysteriously.

## Before deploying: check what's already there

`hostme` manages its own registry (`~/.config/hostme/servers.yaml` /
`sites.yaml`) — it's not aware of anything deployed outside itself. Useful
before acting:

```
hostme --json list           # every known site: domain, server, php/html, last deploy
hostme --json domain list    # registered base (wildcard) domains and which server owns them
hostme --json server list    # registered servers
```

If the user's request implies a domain that isn't in `domain list`'s output
and isn't a subdomain of one that is, you'll need `--server NAME` explicitly
on the first deploy (see `hostme --json help` for the exact error/flow).

## If commands that should work throw "No such command '<domain>'"

That specific error means the globally installed `hostme` binary is stale —
its launcher script still calls the old entry point directly instead of the
one that rewrites surge-style argv (a real bug hit on 2026-09-09: changing
`[project.scripts]` in `pyproject.toml` does **not** regenerate the installed
launcher under an editable install). Fix: from the repo, run
`uv tool install --editable . --force`, then retry. Not something to silently
work around — surface it, since it means every domain-first command was
broken until fixed.

## Staying in sync

This file lives at `src/hostme/data/SKILL.md` in the repo and is bundled
into the installed package (`hostme --ai` prints it verbatim). The copy an
AI tool actually reads (e.g. `~/.claude/skills/hostme/SKILL.md`) is a
synced-out copy, not the source of truth — after pulling a `hostme` update,
resync it with:

```
hostme skill install
```

(writes to `~/.claude/skills/hostme/SKILL.md` by default; `--path PATH` for
somewhere else). If a locally-installed skill copy and `hostme --json help`
ever disagree, trust `help` and re-run `skill install` — don't hand-edit the
installed copy, it'll just drift again on the next update.

## `--target`: third-party hosting, NOT the user's own VPS — needs explicit go-ahead every time

Besides `--server` (the user's own VPS, Webinoly-managed, full SSL/releases/
rollback lifecycle), `hostme` can also deploy to a registered `Target` —
someone else's hosting (ftp/sftp/ssh credentials to a shared-hosting panel,
e.g. Beget). Registered with `hostme target add`, listed with
`hostme target list`, used with `hostme <path> <domain> --target NAME`
(domain must be explicit — targets have no base-domain/wildcard concept).
Target passwords are stored in the OS keychain (never in
`~/.config/hostme/servers.yaml`), resolved transparently — nothing an agent
needs to handle.

This is meaningfully higher-stakes than a `--server` deploy: it's third-party
infrastructure (often someone else's live production site, not the user's
own VPS they fully control), the rollback story is weaker (a single local
pre-deploy backup snapshot per deploy, not the server-side releases history
`--server` gets), and a wrong domain/target pairing overwrites real content
on a host you don't own the failure mode for.

**Never run a `--target` deploy (or `target add`/`target remove`, or
`teardown`/`rollback`/`maintenance` on a target-hosted site) on your own initiative.**
Always get the user's explicit go-ahead for that specific domain/target
right before doing it — a general "yes, set up target deploys" earlier in
the conversation does not cover a specific deploy call later. This is
stricter than the general destructive-ops guidance below: even a plain
`deploy` (not just teardown) needs confirmation here, because the target
itself represents someone else's hosting account, not infrastructure the
user has already delegated to you by registering it as a Server.

`auth`/`config`/`ssl`/`debug`/`revs`/`rollfore` don't apply to targets at all
(Webinoly-specific) — `hostme` itself will refuse with a clear error, no need
to pre-filter these yourself.

## Destructive operations — confirm scope, don't assume

`teardown`, `rollback`, and `maintenance` all require `--yes`/`-y` (or an
interactive terminal, where `hostme` prompts) — this applies equally to the
user's own server and to a `--target`, and `--json` does not bypass it (see
above). Never pass `--yes` on your own initiative; get the user's go-ahead
for that specific domain right before the call.

`teardown` deletes the site on the server (files + revokes SSL) and removes
it from the registry — irreversible. `rollback`/`maintenance` are reversible
(a symlink swap on the server, or a target backup restore — the previous
content isn't lost). `config --no-cors` / `--remove-redirect` are also
reversible. Reversible doesn't mean "skip asking" — it means a mistake here
is recoverable, not that it's low-stakes to begin with.
