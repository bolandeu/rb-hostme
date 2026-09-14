from __future__ import annotations

import sys
import webbrowser
from typing import Annotated

import typer
from rich.markup import escape as rich_escape

from hostme import config, output
from hostme.core import services
from hostme.errors import HostmeError

# Форма команд копирует surge.sh (AGENTS.md): `hostme <path> [domain]` для деплоя,
# `hostme <domain> <subcommand>` для управления — без промежуточных слов вроде "deploy".
# Typer/Click умеет только статическое дерево подкоманд, поэтому реальный argv
# переписывается в explicit-подкоманды (_translate_argv) до того, как его увидит Typer.
_TOP_LEVEL_COMMANDS = {"server", "domain", "target", "list", "open", "doctor", "help", "--help", "-h"}
_DOMAIN_SUBCOMMANDS = {"teardown", "config", "auth", "ssl", "debug", "revs", "rollback", "rollfore", "maintenance"}
# Глобальные флаги-префиксы — допустимы и до, и вперемешку между собой перед
# реальной командой; должны пережить переписывание argv в explicit-подкоманды.
_GLOBAL_PREFIX_FLAGS = {"--json", "--non-interactive", "--dry-run"}


def _translate_argv(argv: list[str]) -> list[str]:
    args = list(argv)
    prefix: list[str] = []
    while args and args[0] in _GLOBAL_PREFIX_FLAGS:
        prefix.append(args.pop(0))

    if not args or args[0] in _TOP_LEVEL_COMMANDS:
        return prefix + args

    if len(args) >= 2 and args[1] in _DOMAIN_SUBCOMMANDS:
        domain, subcmd, *rest = args
        return prefix + [subcmd, domain, *rest]

    return prefix + ["_deploy", *args]

_GRAMMAR_NOTE = """
ВАЖНО про форму команд (не как в обычном Typer/Click-CLI, а как у surge.sh):

  hostme <path> [domain] [--server NAME]     — деплой (БЕЗ слова "deploy")
  hostme <domain> <subcommand> [...]         — управление сайтом (ДОМЕН ПЕРВЫМ)

Ниже в списке Commands ниже Click покажет "teardown", "config", "auth" и т.п.
как будто их надо вызывать первыми (`hostme teardown ...`) — это НЕ так, реальный
порядок — домен первым: `hostme mydomain.com teardown`. Смотри `hostme help` для
полного справочника с примерами (или README.md/PRD.md в репозитории).
"""

app = typer.Typer(
    name="hostme",
    help="Личный аналог surge.sh — деплой сайтов на свои VPS.",
    epilog=rich_escape(_GRAMMAR_NOTE),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

server_app = typer.Typer(help="Управление серверами.", no_args_is_help=True)
domain_app = typer.Typer(help="Управление служебными доменами.", no_args_is_help=True)
target_app = typer.Typer(
    help="Управление сторонними хостингами (ftp/sftp/ssh, без Webinoly).", no_args_is_help=True
)
app.add_typer(server_app, name="server")
app.add_typer(domain_app, name="domain")
app.add_typer(target_app, name="target")

# Полный справочник — источник и для `hostme help` (человеку/агенту без доступа к
# репозиторию), и для README/будущего Claude Code skill'а поверх hostme (PRD раздел
# 2, TODO «Сквозные задачи»). Держать в синхроне с реально реализованными командами
# — если команда здесь есть, она должна работать; чего нет в MVP, помечено явно.
_COMMAND_REFERENCE: list[tuple[str, str]] = [
    ("hostme <path> [domain] [--server NAME]", "деплой/обновление сайта (без слова deploy)"),
    ("hostme <domain> teardown [--yes]", "снести сайт на сервере и убрать из реестра"),
    ("hostme <domain> config", "показать настройки сайта"),
    ("hostme <domain> config --redirect FROM=TO", "добавить/обновить redirect"),
    ("hostme <domain> config --remove-redirect FROM", "убрать redirect"),
    ("hostme <domain> config --cors ORIGIN [--cors ORIGIN ...]", "задать список разрешённых CORS-origin'ов"),
    ("hostme <domain> config --no-cors", "убрать CORS"),
    ("hostme <domain> config --nginx-snippet PATH", "залить произвольный локальный .conf как кастомный nginx-сниппет сайта"),
    ("hostme <domain> config --no-nginx-snippet", "убрать кастомный nginx-сниппет"),
    ("hostme <domain> auth --user U --pass P", "включить password protection (HTTP Basic Auth)"),
    ("hostme <domain> auth --off", "выключить password protection"),
    ("hostme <domain> debug [--error] [--lines N]", "HTTP-статус + хвост access/error-лога"),
    ("hostme <domain> revs", "список релизов сайта (для rollback/rollfore)"),
    ("hostme <domain> rollback [--yes]", "откатить сайт на предыдущий релиз"),
    ("hostme <domain> rollfore", "вернуть сайт на следующий (после rollback) релиз"),
    (
        "hostme <domain> maintenance [--yes]",
        "очистить сайт, оставив встроенный плейсхолдер «в разработке»; старое содержимое не теряется — откат через rollback",
    ),
    ("hostme list", "таблица сайтов из реестра + служебные домены без деплоя через hostme (помечены отдельно)"),
    ("hostme open <domain>", "открыть сайт в браузере"),
    ("hostme doctor", "проверка окружения/конфига (бинари, права, ключи) без обращения к серверам"),
    ("hostme server add --name N --host H --user U [--key PATH] [--default]", "зарегистрировать сервер"),
    ("hostme server init <name>", "поставить/проверить Webinoly на сервере"),
    ("hostme server update <name>", "обновить сам Webinoly на сервере (не пакеты)"),
    ("hostme server list", "таблица серверов"),
    ("hostme server remove <name> [--force]", "убрать сервер из реестра"),
    ("hostme domain add <server> <domain> [--default]", "зарегистрировать служебный (base) домен"),
    ("hostme domain default <domain>", "сделать домен дефолтным (для авто-генерации поддоменов)"),
    ("hostme domain list", "таблица служебных доменов"),
    ("hostme domain remove <domain>", "убрать служебный домен из реестра"),
    (
        "hostme target add --name N --connection ssh|ftp|sftp --host H --user U [--password P] [--ssh-key PATH] [--path REMOTE]",
        "зарегистрировать сторонний хостинг (не Webinoly — просто заливка файлов)",
    ),
    ("hostme target list", "таблица target'ов"),
    ("hostme target remove <name> [--force]", "убрать target из реестра"),
    (
        "hostme <path> <domain> --target NAME [--yes]",
        (
            "деплой на target вместо Webinoly-сервера (домен обязателен явно, нет base-доменов у target'ов); "
            "требует --yes или интерактивного подтверждения — сторонний хостинг, --json НЕ пропускает молча"
        ),
    ),
    (
        "hostme <domain> teardown --yes / rollback --yes / maintenance --yes",
        "деструктивные команды (свой сервер и target одинаково) требуют --yes в неинтерактивном режиме (--json/--non-interactive) — не пропускают молча",
    ),
    ("--json (глобальный флаг, до остальных)", "чистый JSON вместо rich-вывода, без цвета — для агентов"),
    ("--non-interactive (глобальный флаг)", "никогда не спрашивать подтверждение — упасть понятной ошибкой вместо этого, если оно нужно"),
    ("--dry-run (глобальный флаг)", "показать, что сделала бы деструктивная команда, ничего не меняя"),
]

_NOT_IMPLEMENTED_NOTE = (
    "Не реализовано в MVP: `hostme <domain> ssl` (подстановка своего сертификата), "
    "`hostme <domain> discard` (нет аналога — у нас нет preview-концепции), wildcard SSL "
    "изнутри hostme (делается вручную по WILDCARD-SSL.md — DNS-01 требует ручного шага "
    "с DNS-провайдером), git push-to-deploy, -proxy= сайты (вне скоупа — только html/php/статика). "
    "Для сайтов на target (сторонний хостинг): `auth`/`config`/`ssl`/`debug`/`revs`/`rollfore` "
    "не поддерживаются вовсе (Webinoly-специфичны) — только deploy/list/open/teardown/rollback. "
    "ВАЖНО для агентов: deploy/teardown/rollback на target — это чужая/стороннняя инфраструктура, "
    "не собственный VPS пользователя. Такое действие требует явного --yes (или интерактивного "
    "подтверждения) НА КАЖДЫЙ конкретный вызов; --json НЕ пропускает это подтверждение молча "
    "(в отличие от teardown на своём сервере) — агент не должен передавать --yes сам по себе, "
    "не получив явного «да» от человека на именно это действие прямо сейчас."
)


@app.callback()
def root(
    json_output: Annotated[bool, typer.Option("--json", help="Машиночитаемый вывод (для агентов).")] = False,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Никогда не спрашивать подтверждение интерактивно.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Показать, что сделала бы деструктивная команда, ничего не меняя.")
    ] = False,
) -> None:
    output.set_json_mode(json_output)
    output.set_non_interactive(non_interactive)
    output.set_dry_run(dry_run)


# --- server ---------------------------------------------------------------


@server_app.command("add")
def server_add(
    name: Annotated[str, typer.Option("--name")],
    host: Annotated[str, typer.Option("--host")],
    user: Annotated[str, typer.Option("--user")] = "root",
    key: Annotated[str, typer.Option("--key")] = "~/.ssh/id_ed25519",
    default: Annotated[bool, typer.Option("--default")] = False,
) -> None:
    result = services.add_server(name, host, user, key, default)
    output.success(result.pop("message"), **result)


@server_app.command("init")
def server_init(name: Annotated[str, typer.Argument()]) -> None:
    result = services.init_server(name)
    output.success(result.pop("message"), **result)


@server_app.command("update")
def server_update(name: Annotated[str, typer.Argument()]) -> None:
    result = services.update_server(name)
    output.success(result.pop("message"), **result)


@server_app.command("list")
def server_list_cmd() -> None:
    servers = config.load_servers()
    if output.is_json_mode():
        output.info(
            "servers",
            servers=[
                {"name": s.name, "host": s.host, "user": s.user, "default": s.default}
                for s in servers
            ],
        )
        return
    if not servers:
        output.console.print("Серверов пока нет. `hostme server add ...`")
        return
    for s in servers:
        mark = " (default)" if s.default else ""
        output.console.print(f"{s.name}{mark} — {s.user}@{s.host}")


@server_app.command("remove")
def server_remove(
    name: Annotated[str, typer.Argument()],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    result = services.remove_server(name, force)
    output.success(result.pop("message"), **result)


# --- domain -----------------------------------------------------------------


@domain_app.command("add")
def domain_add(
    server_name: Annotated[str, typer.Argument()],
    domain: Annotated[str, typer.Argument()],
    default: Annotated[bool, typer.Option("--default")] = False,
) -> None:
    result = services.add_domain(server_name, domain, default)
    output.success(result.pop("message"), **result)


@domain_app.command("default")
def domain_default(domain: Annotated[str, typer.Argument()]) -> None:
    result = services.set_default_domain(domain)
    output.success(result.pop("message"), **result)


@domain_app.command("remove")
def domain_remove(domain: Annotated[str, typer.Argument()]) -> None:
    result = services.remove_domain(domain)
    output.success(result.pop("message"), **result)


@domain_app.command("list")
def domain_list_cmd() -> None:
    rows = services.list_domains()
    if output.is_json_mode():
        output.info(
            "domains",
            domains=[
                {"domain": d.name, "server": server_name, "default": d.default}
                for server_name, d in rows
            ],
        )
        return
    if not rows:
        output.console.print("Служебных доменов пока нет. `hostme domain add ...`")
        return
    for server_name, d in rows:
        mark = " (default)" if d.default else ""
        output.console.print(f"{d.name}{mark} — {server_name}")


# --- target (сторонний хостинг, ftp/sftp/ssh, без Webinoly) -----------------


@target_app.command("add")
def target_add(
    name: Annotated[str, typer.Option("--name")],
    connection: Annotated[str, typer.Option("--connection")],
    host: Annotated[str, typer.Option("--host")],
    user: Annotated[str, typer.Option("--user")],
    password: Annotated[str | None, typer.Option("--password")] = None,
    ssh_key: Annotated[str | None, typer.Option("--ssh-key")] = None,
    remote_path: Annotated[str, typer.Option("--path")] = "/",
) -> None:
    result = services.add_target(name, connection, host, user, password, ssh_key, remote_path)
    output.success(result.pop("message"), **result)


@target_app.command("list")
def target_list_cmd() -> None:
    targets = config.load_targets()
    if output.is_json_mode():
        output.info(
            "targets",
            targets=[
                {
                    "name": t.name,
                    "connection": t.connection,
                    "host": t.host,
                    "user": t.user,
                    "remote_path": t.remote_path,
                    # пароль/ключ никогда не печатаем — ни в --json, ни в человеческом выводе
                    "has_password": bool(t.password),
                    "has_ssh_key": bool(t.ssh_key),
                }
                for t in targets
            ],
        )
        return
    if not targets:
        output.console.print("Target'ов пока нет. `hostme target add ...`")
        return
    for t in targets:
        output.console.print(f"{t.name} ({t.connection}) — {t.user}@{t.host}:{t.remote_path}")


@target_app.command("remove")
def target_remove(
    name: Annotated[str, typer.Argument()],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    result = services.remove_target(name, force)
    output.success(result.pop("message"), **result)


# --- deploy / list / open / teardown ----------------------------------------


@app.command("_deploy", hidden=True)
def deploy(
    path: Annotated[str, typer.Argument()],
    domain: Annotated[str | None, typer.Argument()] = None,
    server_name: Annotated[str | None, typer.Option("--server")] = None,
    target_name: Annotated[str | None, typer.Option("--target")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    result = services.deploy(path, domain, server_name, target_name, yes)
    output.success(result.pop("message"), **result)


@app.command("list")
def list_sites_cmd() -> None:
    sites, bare_base_domains = services.list_sites()
    if output.is_json_mode():
        output.info(
            "sites",
            sites=[
                {
                    "domain": s.domain,
                    "server": s.server,
                    "php": s.php,
                    "deployed_at": s.deployed_at,
                    "base_domain": False,
                }
                for s in sites
            ]
            + [
                {"domain": name, "server": server_name, "php": None, "deployed_at": None, "base_domain": True}
                for name, server_name in bare_base_domains
            ],
        )
        return
    if not sites and not bare_base_domains:
        output.console.print("Сайтов пока нет.")
        return
    for s in sites:
        kind = "php" if s.php else "html"
        output.console.print(f"https://{s.domain}  [{kind}]  {s.server}  {s.deployed_at or ''}")
    for name, server_name in bare_base_domains:
        output.console.print(f"https://{name}  [служебный домен, без деплоя через hostme]  {server_name}")


@app.command("open")
def open_site(domain: Annotated[str, typer.Argument()]) -> None:
    webbrowser.open(f"https://{domain}")
    output.success(f"Открываю https://{domain}")


@app.command("revs")
def revs(domain: Annotated[str, typer.Argument()]) -> None:
    """Вызов: hostme <domain> revs — список релизов сайта."""
    domain = config.normalize_domain(domain)
    result = services.get_revisions(domain)
    if output.is_json_mode():
        output.info("revs", **result)
        return
    releases, current = result["releases"], result["current"]
    if not releases:
        output.console.print("Релизов пока нет.")
        return
    for r in releases:
        output.console.print(f"{r}{' (current)' if r == current else ''}")


@app.command("rollback")
def rollback(
    domain: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Вызов: hostme <domain> rollback [--yes] — откатить на предыдущий релиз
    (сервер) или последний локальный бэкап (target)."""
    domain = config.normalize_domain(domain)
    result = services.rollback(domain, yes)
    output.success(result.pop("message"), **result)


@app.command("rollfore")
def rollfore(domain: Annotated[str, typer.Argument()]) -> None:
    """Вызов: hostme <domain> rollfore — вернуть на следующий (после rollback) релиз."""
    domain = config.normalize_domain(domain)
    result = services.rollfore(domain)
    output.success(result.pop("message"), **result)


@app.command("maintenance")
def maintenance(
    domain: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Вызов: hostme <domain> maintenance [--yes] — очистить сайт, оставив
    встроенный плейсхолдер "в разработке". Откат — через `rollback`."""
    domain = config.normalize_domain(domain)
    result = services.set_maintenance(domain, yes)
    output.success(result.pop("message"), **result)


@app.command("teardown")
def teardown(
    domain: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Вызов: hostme <domain> teardown [--yes] — снести сайт и убрать из реестра."""
    domain = config.normalize_domain(domain)
    result = services.teardown(domain, yes)
    output.success(result.pop("message"), **result)


@app.command("auth")
def auth(
    domain: Annotated[str, typer.Argument()],
    user: Annotated[str | None, typer.Option("--user")] = None,
    password: Annotated[str | None, typer.Option("--pass")] = None,
    off: Annotated[bool, typer.Option("--off")] = False,
) -> None:
    """Вызов: hostme <domain> auth --user U --pass P (или --off) — password protection."""
    domain = config.normalize_domain(domain)
    result = services.set_http_auth(domain, user, password, off)
    output.success(result.pop("message"), **result)


def _print_site_config(site: config.Site) -> None:
    if output.is_json_mode():
        output.info(
            "config",
            domain=site.domain,
            server=site.server,
            php=site.php,
            ssl=site.ssl,
            force_https=site.force_https,
            cors=site.cors,
            redirects=site.redirects,
            password_protect=site.password_protect,
        )
        return
    output.console.print(f"domain: {site.domain}")
    output.console.print(f"server: {site.server}")
    output.console.print(f"php: {site.php}")
    output.console.print(f"ssl: {site.ssl}  (force-https: всегда включён вместе с SSL, см. docs/webinoly.md)")
    output.console.print(f"cors: {', '.join(site.cors) or '(нет)'}")
    if site.redirects:
        for r in site.redirects:
            output.console.print(f"redirect: {r['from']} -> {r['to']}")
    else:
        output.console.print("redirects: (нет)")
    output.console.print(f"password_protect: {site.password_protect or '(выкл)'}")


@app.command("config")
def site_config(
    domain: Annotated[str, typer.Argument()],
    cors: Annotated[list[str], typer.Option("--cors")] = [],  # noqa: B006
    no_cors: Annotated[bool, typer.Option("--no-cors")] = False,
    redirect: Annotated[list[str], typer.Option("--redirect")] = [],  # noqa: B006
    remove_redirect: Annotated[list[str], typer.Option("--remove-redirect")] = [],  # noqa: B006
    force_https: Annotated[bool, typer.Option("--force-https")] = False,
    no_force_https: Annotated[bool, typer.Option("--no-force-https")] = False,
    nginx_snippet: Annotated[str | None, typer.Option("--nginx-snippet")] = None,
    no_nginx_snippet: Annotated[bool, typer.Option("--no-nginx-snippet")] = False,
) -> None:
    """Вызов: hostme <domain> config [--cors ...] [--redirect FROM=TO] [...] — настройки сайта; без флагов печатает текущие."""
    domain = config.normalize_domain(domain)
    result = services.update_site_config(
        domain, cors, no_cors, redirect, remove_redirect, force_https, no_force_https, nginx_snippet, no_nginx_snippet
    )
    if result["message"] is None:
        _print_site_config(result["site"])
        return
    output.success(result["message"], domain=domain)


@app.command("debug")
def debug(
    domain: Annotated[str, typer.Argument()],
    error: Annotated[bool, typer.Option("--error")] = False,
    lines: Annotated[int, typer.Option("--lines")] = 10,
) -> None:
    """Вызов: hostme <domain> debug [--error] [--lines N] — HTTP-статус + хвост лога."""
    domain = config.normalize_domain(domain)
    result = services.get_debug_info(domain, error, lines)
    if output.is_json_mode():
        output.info("debug", **result)
        return
    output.console.print(f"https://{result['domain']} -> {result['http_status']}")
    output.console.print(f"--- {'error' if error else 'access'} log (последние {lines}) ---")
    output.console.print(result["log"] or "(пусто)")


@app.command("doctor")
def doctor() -> None:
    """Вызов: hostme doctor — проверка окружения/конфига (бинари, права,
    читаемость реестров, локальные ssh-ключи) без обращения к серверам."""
    result = services.run_doctor()
    if output.is_json_mode():
        output.info("doctor", **result)
    else:
        for check in result["checks"]:
            icon = {"ok": "[green]✔[/green]", "warn": "[yellow]![/yellow]", "fail": "[red]✖[/red]"}[check["status"]]
            output.console.print(f"{icon} {check['name']}: {check['detail']}")
    if not result["ok"]:
        raise typer.Exit(code=1)


@app.command("help")
def help_cmd() -> None:
    """Полный справочник команд (для человека и для агентов — см. --json)."""
    if output.is_json_mode():
        output.info(
            "help",
            commands=[{"usage": usage, "description": desc} for usage, desc in _COMMAND_REFERENCE],
            not_implemented=_NOT_IMPLEMENTED_NOTE,
        )
        return
    # markup=False обязателен: в usage-строках полно "[domain]"/"[--server NAME]" —
    # без этого Rich принимает квадратные скобки за markup-теги и съедает текст внутри.
    output.console.print("hostme — деплой сайтов на свои VPS (аналог surge.sh).\n", markup=False)
    output.console.print(_GRAMMAR_NOTE.strip(), markup=False)
    output.console.print()
    width = max(len(usage) for usage, _ in _COMMAND_REFERENCE)
    for usage, desc in _COMMAND_REFERENCE:
        output.console.print(f"  {usage.ljust(width)}  {desc}", markup=False)
    output.console.print(f"\n{_NOT_IMPLEMENTED_NOTE}", markup=False)


def main() -> None:
    try:
        app(args=_translate_argv(sys.argv[1:]))
    except HostmeError as exc:
        output.error(exc)
    except Exception as exc:  # noqa: BLE001 — не даём агенту голый трейсбек
        output.error(f"Неожиданная ошибка: {exc}")


if __name__ == "__main__":
    main()
