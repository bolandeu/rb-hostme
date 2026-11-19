---
name: hostme
description: "Deploy static/PHP sites (built landing pages, client sites, previews, artifacts that need a real URL) via `hostme` — a personal surge.sh-alike CLI. Deploys to the user's own VPS (--server, full lifecycle) or a registered third-party ftp/sftp/ssh hosting (--target, file transfer only — needs the user's explicit go-ahead per deploy, see below). Use whenever the user wants a local folder published/hosted/deployed to a real domain, not just previewed locally. Not for anything with a backend process (Node/API servers) — hostme only serves static files and PHP."
metadata:
  version: 2.1.0
---

# hostme

Personal CLI (repo: `~/Work/tools/rb-hostme`, docs in that repo's `docs/usage/`)
that deploys a local folder to the user's own VPS through
Webinoly (nginx+php-fpm), with SSL always on. One command, no accounts, no
platform lock-in — the self-hosted analog of `surge.sh`.

This doc is bundled with the package itself (`src/hostme/data/SKILL.md`), not
maintained by hand in `~/.claude/skills/` — see "Staying in sync" below.

## Install (if `hostme --version` fails)

```bash
uv tool install rb-hostme --index https://homeserver.tailee01ab.ts.net:3000/api/packages/bolandeu/pypi/simple
```

From the git tag instead:

```bash
uv tool install "rb-hostme @ git+https://homeserver.tailee01ab.ts.net:3000/bolandeu/hostme.git@vX.Y.Z"
```

Replace `vX.Y.Z` with the latest release tag (install from a tag, never a
branch: [the Standard](https://homeserver.tailee01ab.ts.net:3000/bolandeu/cli-generator/src/branch/main/skills/cli-builder/reference/standard.md), Install).

Same command on macOS and Linux (Windows: the CLI itself installs, but it
shells out to `ssh`/`rsync`/`lftp`, which you'd need on PATH);
`uv tool upgrade rb-hostme` updates it. Do not run from source unless asked to
develop the CLI.

## First: get the live command reference, don't guess

The command surface evolves; don't hardcode it here. A bare `hostme` prints
name + version + every command with its **real** invocation form as the
first line; `hostme <command> --help` prints the rest. For the full
reference with examples and the list of what's explicitly NOT implemented:

```
hostme help --json
```

`hostme describe --json` gives the whole CLI as one OpenCLI document
(commands, options, exit codes, env vars, data) — the bare document, no
`{"ok": ...}` envelope.

Trust that output over anything below if they conflict — this file can go
stale, the CLI's own help cannot (it's rendered from the code that runs the
commands). If you can execute the CLI but can't read files from disk
(sandboxed shell, remote exec), `hostme --ai` prints this exact document.

## The one thing that will trip you up: command order

This CLI's grammar is **not** standard subcommand-first. It copies surge.sh:

```
hostme <path> [domain] [--server NAME]     # deploy — NO "deploy" keyword
hostme <domain> <subcommand> [...]          # manage — DOMAIN FIRST, not the subcommand
```

So it's `hostme mysite.com teardown`, never `hostme teardown mysite.com`. If
you type the subcommand first with other arguments, `hostme` reinterprets it
as a deploy whose local path is literally named after the subcommand — it
won't error usefully, it'll just do the wrong thing. (`hostme teardown
--help` alone is fine — it shows teardown's help.) When in doubt, check the
`usage` string in `hostme help --json`.

## Quick path: deploy a build output

```
hostme ./dist                            # domain auto-generated from folder name + default base domain
hostme ./dist mysite.com --server vps1   # explicit domain, needed the first time for a domain not already known
```

If no domain is given and there's no default base (wildcard) domain
registered yet, it errors and tells you to pass one explicitly or run
`hostme domain add` first — don't guess a domain, surface that error to the
user.

Deploy is idempotent and keeps release history (`hostme <domain> revs`,
`rollback`, `rollfore`) — redeploying the same domain never loses the
previous version, it's just a symlink swap away. The webroot becomes an
exact mirror of the folder (`rsync --delete`): deploying the wrong/empty
folder replaces the site's content (recoverable via `rollback`).

On `--server` sites hostme enforces trailing-slash URLs in nginx: `/a`,
`/a.html` and `/a/index.html` all 301 to `/a/` (query kept), and `/a/` serves
`a/index.html` or a flat `a.html`. Build and link with trailing slashes
(Astro: `trailingSlash: 'always'`, `build.format: 'directory'`); don't add
your own snippet that strips slashes, that makes a redirect loop.
`/_astro/*` is served `immutable` for a year.

## Always use `--json`

`--json`, `--non-interactive`, `--dry-run`, `--quiet`, `--verbose` work
**before or after** the command (`hostme --json list` ≡ `hostme list
--json`), in any order. Under `--json` every command prints exactly one
single-line JSON object **to stdout** — success and error alike:

```
{"ok": true, ...}
{"ok": false, "error": {"code": "...", "message": "...", "action": "..."}}
```

Parse stdout; stderr is only diagnostics (progress lines of long operations
like deploy, and `--verbose` shows the actual
`ssh`/`rsync`/`lftp` commands being run). `action`, when present, is the
concrete next command to run. `--json` implies `--non-interactive`: nothing
blocks on stdin.

### Exit codes and `error.code`

```
0  ok
1  ERROR (a known state problem, e.g. "no older release to roll back to"),
   ABORTED (user answered "no" to the prompt),
   UNEXPECTED (a bug — re-run with --verbose for the traceback and report it),
   CREDENTIAL_STORE_UNAVAILABLE (OS keychain unusable → error.action names the env var)
2  INVALID_ARGUMENTS — bad flags, a server/domain/target/site not in the registry,
   or a destructive command without --confirm in non-interactive mode (--json,
   --non-interactive, or no TTY on stdin)
3  CREDENTIALS_UNHEALTHY — `hostme auth status`: a server key or target password
   is missing/invalid/unreachable (the full report is still in the output)
5  PROVIDER_ERROR — ssh/rsync/lftp/Webinoly failed or isn't installed
   (error.provider says which); network/timeouts land here too
```

Only exit 5 is a candidate for retry, and only after reading `message`
(a missing binary won't fix itself). `hostme doctor --json` (`healthy` +
per-check `status`) checks binaries, registry files/permissions and declared
ssh keys without contacting any server — cheap to run first if a command is
failing mysteriously.

## Before deploying: check what's already there

`hostme` manages its own registry (`~/.config/hostme/servers.yaml`, and
`sites.yaml` in its data dir — `hostme doctor` prints the path) — it's not aware of anything deployed outside itself:

```
hostme list --json           # every known site: domain, server, php/html, last deploy
hostme domain list --json    # registered base (wildcard) domains and which server owns them
hostme server list --json    # registered servers
```

If the user's request implies a domain that isn't in `domain list`'s output
and isn't a subdomain of one that is, you'll need `--server NAME` explicitly
on the first deploy.

## Destructive operations — `--dry-run`, then `--confirm` only with sign-off

`teardown`, `rollback`, `maintenance` (own server and `--target` alike) and
any deploy to a `--target` are gated. The flow is always:

1. `hostme <domain> teardown --dry-run --json` — preview (same result
   shape with `"dry_run": true`, nothing changes, no confirmation needed).
2. Show the user what it would do; get their explicit go-ahead **for that
   domain, right now**.
3. `hostme <domain> teardown --confirm --json`.

Without `--confirm` (alias `--yes`/`-y`) a gated command under `--json` or
`--non-interactive` fails with `INVALID_ARGUMENTS` — it never prompts and
never proceeds silently. Never add `--confirm` on your own initiative; a
general "yes, go ahead" earlier in the conversation does not cover a
specific call later.

`teardown` deletes the site on the server (files + revokes SSL) and removes
it from the registry — irreversible. `rollback`/`maintenance` are reversible
(a symlink swap on the server, or a target backup restore). `config
--no-cors` / `--remove-redirect` are also reversible. `config --php` / `--html`
(switch a live site between HTML and PHP) is gated by `--confirm`: the site is
down while the switch runs, though a failure restores the previous type and
content. Reversible doesn't mean "skip asking" — it means a mistake is
recoverable, not that it's low-stakes.

## `--target`: third-party hosting, NOT the user's own VPS

Besides `--server` (the user's own VPS, Webinoly-managed, full
SSL/releases/rollback lifecycle), `hostme` can deploy to a registered
`Target` — someone else's hosting (ftp/sftp/ssh credentials to a
shared-hosting panel, e.g. Beget). Registered with `hostme target add`,
listed with `hostme target list`, used with `hostme <path> <domain> --target
NAME` (domain must be explicit — targets have no base-domain concept).
Target passwords come from `HOSTME_DEPLOY_<NAME>_PASSWORD` first, else the OS
keychain (`hostme:<name>`), never from the registry file; `hostme auth status
--check --json` shows where each comes from and whether it works — nothing an agent needs to handle, and never
ask the user to paste one into a command line unless it's `target add`.

This is meaningfully higher-stakes than a `--server` deploy: it's
third-party infrastructure (often someone's live production site), the
rollback story is weaker (one local pre-deploy backup per deploy — only the
newest is restored; older ones are pruned by `settings.yaml` policy — not
server-side release history), and a wrong domain/target pairing overwrites
real content on a host you don't own the failure mode for. **Never run a
`--target` deploy, `target add`/`target remove`, or
`teardown`/`rollback`/`maintenance` on a target-hosted site on your own
initiative** — explicit go-ahead for that specific domain/target every time,
even for a plain deploy.

`auth`/`config`/`ssl`/`debug`/`revs`/`rollfore` don't apply to targets
(Webinoly-specific) — `hostme` refuses with a clear error, no need to
pre-filter.

## Staying in sync

This file lives at `src/hostme/data/SKILL.md` in the repo and is bundled
into the installed package (`hostme --ai` prints it verbatim). The copy an
AI tool actually reads (e.g. `~/.claude/skills/hostme/SKILL.md`) is a
synced-out copy — after reinstalling a newer tag, resync it with:

```
hostme skill install
```

(`--tool agents` for `~/.agents/skills/`, `--project` for the current project). If the installed copy and `hostme help
--json` ever disagree, trust `help` and re-run `skill install` — don't
hand-edit the installed copy.
