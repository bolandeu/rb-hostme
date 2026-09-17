from __future__ import annotations

import sys
import webbrowser
from typing import Annotated

import typer
from rich.markup import escape as rich_escape

from hostme import config, output
from hostme.core import services
from hostme.core.errors import HostmeError, UnexpectedError
from hostme.core.version import DEV_VERSION, installed_version, package_summary
from hostme.data import load_skill_doc

# Форма команд копирует surge.sh (AGENTS.md): `hostme <path> [domain]` для деплоя,
# `hostme <domain> <subcommand>` для управления — без промежуточных слов вроде "deploy".
# Typer/Click умеет только статическое дерево подкоманд, поэтому реальный argv
# переписывается в explicit-подкоманды (_translate_argv) до того, как его увидит Typer.
_TOP_LEVEL_COMMANDS = {
    "server", "domain", "target", "skill", "list", "open", "doctor", "help", "--ai", "--version", "--help", "-h",
}
_DOMAIN_SUBCOMMANDS = {"teardown", "config", "auth", "ssl", "debug", "revs", "rollback", "rollfore", "maintenance"}
# Глобальные флаги — только на уровне root-callback (Typer не даёт их объявить
# и там, и на каждой команде одновременно без дублирования на 15+ функций), но
# агент не обязан помнить, что они идут именно ДО команды — conventions.md
# (cli-builder) требует, чтобы `<cli> <command> --json` работало наравне с
# `<cli> --json <command>`. Раз argv и так целиком переписывается под
# surge-грамматику ниже, тут же вынимаем эти флаги из ЛЮБОЙ позиции и
# перекладываем в префикс — не только с начала, как раньше.
_GLOBAL_PREFIX_FLAGS = {"--json", "--non-interactive", "--dry-run", "--quiet", "--verbose"}


def _translate_argv(argv: list[str]) -> list[str]:
    prefix: list[str] = [a for a in argv if a in _GLOBAL_PREFIX_FLAGS]
    args = [a for a in argv if a not in _GLOBAL_PREFIX_FLAGS]

    if not args or args[0] in _TOP_LEVEL_COMMANDS:
        return prefix + args

    if len(args) >= 2 and args[1] in _DOMAIN_SUBCOMMANDS:
        domain, subcmd, *rest = args
        return prefix + [subcmd, domain, *rest]

    # `hostme teardown --help` — просьба о справке по teardown, а не деплой папки
    # с именем "teardown" (иначе показывалась бы справка деплоя, сбивая с толку).
    if args[0] in _DOMAIN_SUBCOMMANDS and (len(args) == 1 or args[1] in ("-h", "--help")):
        return prefix + args

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

# Голый `hostme` — точка входа для человека и агента: имя + версия + описание,
# затем команды с первой строкой docstring. Без no_args_is_help (он выходит с
# кодом 2) — root() ниже печатает справку и выходит с 0 (conventions.md).
app = typer.Typer(
    name="hostme",
    help=f"hostme {installed_version() or DEV_VERSION} — {package_summary() or 'деплой сайтов на свои VPS.'}",
    epilog=rich_escape(_GRAMMAR_NOTE),
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

server_app = output.group("Управление серверами.")
domain_app = output.group("Управление служебными доменами.")
target_app = output.group("Управление сторонними хостингами (ftp/sftp/ssh, без Webinoly).")
skill_app = output.group("Синхронизация bundled SKILL.md туда, откуда его читают AI-агенты.")
app.add_typer(server_app, name="server")
app.add_typer(domain_app, name="domain")
app.add_typer(target_app, name="target")
app.add_typer(skill_app, name="skill")

# Полный справочник — источник и для `hostme help` (человеку/агенту без доступа к
# репозиторию), и для README/будущего Claude Code skill'а поверх hostme (PRD раздел
# 2, TODO «Сквозные задачи»). Держать в синхроне с реально реализованными командами
# — если команда здесь есть, она должна работать; чего нет в MVP, помечено явно.
_COMMAND_REFERENCE: list[tuple[str, str]] = [
    ("hostme <path> [domain] [--server NAME]", "деплой/обновление сайта (без слова deploy)"),
    ("hostme <domain> teardown [--confirm]", "снести сайт на сервере и убрать из реестра"),
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
    ("hostme <domain> rollback [--confirm]", "откатить сайт на предыдущий релиз"),
    ("hostme <domain> rollfore", "вернуть сайт на следующий (после rollback) релиз"),
    (
        "hostme <domain> maintenance [--confirm]",
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
        "hostme skill install [--path PATH]",
        "записать bundled SKILL.md туда, откуда его читает AI-агент (по умолчанию ~/.claude/skills/hostme/SKILL.md)",
    ),
    ("hostme --ai", "напечатать bundled SKILL.md в stdout (для агента без доступа к файлам на диске) и выйти"),
    (
        "hostme <path> <domain> --target NAME [--confirm]",
        (
            "деплой на target вместо Webinoly-сервера (домен обязателен явно, нет base-доменов у target'ов); "
            "требует --confirm или интерактивного подтверждения — сторонний хостинг, --json НЕ пропускает молча"
        ),
    ),
    (
        "hostme <domain> teardown --confirm / rollback --confirm / maintenance --confirm",
        "деструктивные команды (свой сервер и target одинаково) требуют --confirm (алиас --yes/-y) в неинтерактивном режиме (--json/--non-interactive) — не пропускают молча",
    ),
    ("--json (в любой позиции — до и после команды)", "чистый JSON вместо rich-вывода, без цвета — для агентов"),
    ("--non-interactive (в любой позиции)", "никогда не спрашивать подтверждение — упасть понятной ошибкой вместо этого, если оно нужно"),
    ("--dry-run (в любой позиции)", "показать, что сделала бы деструктивная команда, ничего не меняя"),
]

_NOT_IMPLEMENTED_NOTE = (
    "Не реализовано в MVP: `hostme <domain> ssl` (подстановка своего сертификата), "
    "`hostme <domain> discard` (нет аналога — у нас нет preview-концепции), wildcard SSL "
    "изнутри hostme (делается вручную по WILDCARD-SSL.md — DNS-01 требует ручного шага "
    "с DNS-провайдером), git push-to-deploy, -proxy= сайты (вне скоупа — только html/php/статика). "
    "Для сайтов на target (сторонний хостинг): `auth`/`config`/`ssl`/`debug`/`revs`/`rollfore` "
    "не поддерживаются вовсе (Webinoly-специфичны) — только deploy/list/open/teardown/rollback. "
    "ВАЖНО для агентов: deploy/teardown/rollback на target — это чужая/стороннняя инфраструктура, "
    "не собственный VPS пользователя. Такое действие требует явного --confirm (или интерактивного "
    "подтверждения) НА КАЖДЫЙ конкретный вызов; --json НЕ пропускает это подтверждение молча "
    "(в отличие от teardown на своём сервере) — агент не должен передавать --confirm сам по себе, "
    "не получив явного «да» от человека на именно это действие прямо сейчас."
)


def _version_callback(value: bool) -> None:
    if not value:
        return
    typer.echo(installed_version() or DEV_VERSION)
    raise typer.Exit()


def _ai_callback(value: bool) -> None:
    """Встроенный SKILL.md в stdout — для агента, который может запускать CLI,
    но не может читать файлы с диска (sandbox, remote exec)."""
    if not value:
        return
    typer.echo(load_skill_doc())
    raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Машиночитаемый вывод (для агентов).")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="Не печатать необязательный человеческий вывод.")] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Диагностика в stderr: какие ssh/rsync/lftp-команды реально запускаются.")
    ] = False,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Никогда не спрашивать подтверждение интерактивно.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Показать, что сделала бы деструктивная команда, ничего не меняя.")
    ] = False,
    version: Annotated[
        bool, typer.Option("--version", callback=_version_callback, is_eager=True, help="Показать версию и выйти.")
    ] = False,
    ai: Annotated[
        bool,
        typer.Option(
            "--ai",
            callback=_ai_callback,
            is_eager=True,
            help="Напечатать встроенный SKILL.md (для агента без доступа к файлам на диске) и выйти.",
        ),
    ] = False,
) -> None:
    output.set_json_mode(json_output)
    output.set_quiet(quiet)
    output.set_verbose(verbose)
    output.set_non_interactive(non_interactive)
    output.set_dry_run(dry_run)
    output.configure_logging(verbose)
    output.help_if_no_command(ctx)


# --- server ---------------------------------------------------------------


@server_app.command("add")
@output.guard
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
@output.guard
def server_init(name: Annotated[str, typer.Argument()]) -> None:
    result = services.init_server(name)
    output.success(result.pop("message"), **result)


@server_app.command("update")
@output.guard
def server_update(name: Annotated[str, typer.Argument()]) -> None:
    result = services.update_server(name)
    output.success(result.pop("message"), **result)


@server_app.command("list")
@output.guard
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
@output.guard
def server_remove(
    name: Annotated[str, typer.Argument()],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    result = services.remove_server(name, force)
    output.success(result.pop("message"), **result)


# --- domain -----------------------------------------------------------------


@domain_app.command("add")
@output.guard
def domain_add(
    server_name: Annotated[str, typer.Argument()],
    domain: Annotated[str, typer.Argument()],
    default: Annotated[bool, typer.Option("--default")] = False,
) -> None:
    result = services.add_domain(server_name, domain, default)
    output.success(result.pop("message"), **result)


@domain_app.command("default")
@output.guard
def domain_default(domain: Annotated[str, typer.Argument()]) -> None:
    result = services.set_default_domain(domain)
    output.success(result.pop("message"), **result)


@domain_app.command("remove")
@output.guard
def domain_remove(domain: Annotated[str, typer.Argument()]) -> None:
    result = services.remove_domain(domain)
    output.success(result.pop("message"), **result)


@domain_app.command("list")
@output.guard
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
@output.guard
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
@output.guard
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
@output.guard
def target_remove(
    name: Annotated[str, typer.Argument()],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    result = services.remove_target(name, force)
    output.success(result.pop("message"), **result)


# --- skill (bundled SKILL.md для AI-агентов) --------------------------------


@skill_app.command("install")
@output.guard
def skill_install(
    path: Annotated[
        str | None,
        typer.Option("--path", help="Куда записать (по умолчанию — ~/.claude/skills/hostme/SKILL.md)."),
    ] = None,
) -> None:
    """Вызов: hostme skill install [--path PATH] — записать встроенный
    SKILL.md туда, откуда его читает AI-агент, чтобы документация не
    расходилась с реальным CLI (см. `hostme --ai`)."""
    result = services.install_skill(path)
    output.success(result.pop("message"), **result)


# --- deploy / list / open / teardown ----------------------------------------


@app.command("_deploy", hidden=True)
@output.guard
def deploy(
    path: Annotated[str, typer.Argument()],
    domain: Annotated[str | None, typer.Argument()] = None,
    server_name: Annotated[str | None, typer.Option("--server")] = None,
    target_name: Annotated[str | None, typer.Option("--target")] = None,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", "--yes", "-y", help="Подтвердить деструктивное действие без вопроса (обязателен вместе с --non-interactive/--json)."),
    ] = False,
) -> None:
    result = services.deploy(path, domain, server_name, target_name, confirm)
    output.success(result.pop("message"), **result)


@app.command("list")
@output.guard
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
@output.guard
def open_site(domain: Annotated[str, typer.Argument()]) -> None:
    webbrowser.open(f"https://{domain}")
    output.success(f"Открываю https://{domain}")


@app.command("revs")
@output.guard
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
@output.guard
def rollback(
    domain: Annotated[str, typer.Argument()],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", "--yes", "-y", help="Подтвердить деструктивное действие без вопроса (обязателен вместе с --non-interactive/--json)."),
    ] = False,
) -> None:
    """Вызов: hostme <domain> rollback [--confirm] — откатить на предыдущий релиз
    (сервер) или последний локальный бэкап (target)."""
    domain = config.normalize_domain(domain)
    result = services.rollback(domain, confirm)
    output.success(result.pop("message"), **result)


@app.command("rollfore")
@output.guard
def rollfore(domain: Annotated[str, typer.Argument()]) -> None:
    """Вызов: hostme <domain> rollfore — вернуть на следующий (после rollback) релиз."""
    domain = config.normalize_domain(domain)
    result = services.rollfore(domain)
    output.success(result.pop("message"), **result)


@app.command("maintenance")
@output.guard
def maintenance(
    domain: Annotated[str, typer.Argument()],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", "--yes", "-y", help="Подтвердить деструктивное действие без вопроса (обязателен вместе с --non-interactive/--json)."),
    ] = False,
) -> None:
    """Вызов: hostme <domain> maintenance [--confirm] — очистить сайт, оставив
    встроенный плейсхолдер "в разработке". Откат — через `rollback`."""
    domain = config.normalize_domain(domain)
    result = services.set_maintenance(domain, confirm)
    output.success(result.pop("message"), **result)


@app.command("teardown")
@output.guard
def teardown(
    domain: Annotated[str, typer.Argument()],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", "--yes", "-y", help="Подтвердить деструктивное действие без вопроса (обязателен вместе с --non-interactive/--json)."),
    ] = False,
) -> None:
    """Вызов: hostme <domain> teardown [--confirm] — снести сайт и убрать из реестра."""
    domain = config.normalize_domain(domain)
    result = services.teardown(domain, confirm)
    output.success(result.pop("message"), **result)


@app.command("auth")
@output.guard
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
@output.guard
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
@output.guard
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
@output.guard
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


@app.command("help")
@output.guard
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
    # Команды уже под output.guard; это страховка для ошибок в самом
    # root-callback (например, не прочитался bundled SKILL.md для --ai).
    try:
        app(args=_translate_argv(sys.argv[1:]))
    except HostmeError as exc:
        output.emit_error(exc)
    except Exception as exc:  # noqa: BLE001 — не даём агенту голый трейсбек
        output.emit_error(UnexpectedError(exc))


if __name__ == "__main__":
    main()
