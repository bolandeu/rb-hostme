from __future__ import annotations

import sys
import urllib.error
import urllib.request
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape as rich_escape

from hostme import config, output, webinoly
from hostme.errors import HostmeError
from hostme.ssh import rsync_to

# Форма команд копирует surge.sh (AGENTS.md): `hostme <path> [domain]` для деплоя,
# `hostme <domain> <subcommand>` для управления — без промежуточных слов вроде "deploy".
# Typer/Click умеет только статическое дерево подкоманд, поэтому реальный argv
# переписывается в explicit-подкоманды (_translate_argv) до того, как его увидит Typer.
_TOP_LEVEL_COMMANDS = {"server", "domain", "list", "open", "help", "--help", "-h"}
_DOMAIN_SUBCOMMANDS = {"teardown", "config", "auth", "ssl", "debug", "revs", "rollback", "rollfore"}


def _translate_argv(argv: list[str]) -> list[str]:
    args = list(argv)
    prefix: list[str] = []
    while args and args[0] == "--json":
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
app.add_typer(server_app, name="server")
app.add_typer(domain_app, name="domain")

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
    ("hostme <domain> auth --user U --pass P", "включить password protection (HTTP Basic Auth)"),
    ("hostme <domain> auth --off", "выключить password protection"),
    ("hostme <domain> debug [--error] [--lines N]", "HTTP-статус + хвост access/error-лога"),
    ("hostme <domain> revs", "список релизов сайта (для rollback/rollfore)"),
    ("hostme <domain> rollback", "откатить сайт на предыдущий релиз"),
    ("hostme <domain> rollfore", "вернуть сайт на следующий (после rollback) релиз"),
    ("hostme list", "таблица всех сайтов из реестра"),
    ("hostme open <domain>", "открыть сайт в браузере"),
    ("hostme server add --name N --host H --user U [--key PATH] [--default]", "зарегистрировать сервер"),
    ("hostme server init <name>", "поставить/проверить Webinoly на сервере"),
    ("hostme server list", "таблица серверов"),
    ("hostme server remove <name> [--force]", "убрать сервер из реестра"),
    ("hostme domain add <server> <domain> [--default]", "зарегистрировать служебный (base) домен"),
    ("hostme domain default <domain>", "сделать домен дефолтным (для авто-генерации поддоменов)"),
    ("hostme domain list", "таблица служебных доменов"),
    ("--json (глобальный флаг, до остальных)", "чистый JSON вместо rich-вывода, без цвета — для агентов"),
]

_NOT_IMPLEMENTED_NOTE = (
    "Не реализовано в MVP: `hostme <domain> ssl` (подстановка своего сертификата), "
    "`hostme <domain> discard` (нет аналога — у нас нет preview-концепции), wildcard SSL "
    "изнутри hostme (делается вручную по WILDCARD-SSL.md — DNS-01 требует ручного шага "
    "с DNS-провайдером), git push-to-deploy, -proxy= сайты (вне скоупа — только html/php/статика)."
)


@app.callback()
def root(
    json_output: bool = typer.Option(
        False, "--json", help="Машиночитаемый вывод (для агентов)."
    ),
) -> None:
    output.set_json_mode(json_output)


# --- server ---------------------------------------------------------------


@server_app.command("add")
def server_add(
    name: Annotated[str, typer.Option("--name")],
    host: Annotated[str, typer.Option("--host")],
    user: Annotated[str, typer.Option("--user")] = "root",
    key: Annotated[str, typer.Option("--key")] = "~/.ssh/id_ed25519",
    default: Annotated[bool, typer.Option("--default")] = False,
) -> None:
    servers = config.load_servers()
    if config.find_server(servers, name) is not None:
        raise HostmeError(f"Сервер {name!r} уже зарегистрирован")

    if default:
        for s in servers:
            s.default = False
    is_first = not servers
    servers.append(
        config.Server(
            name=name, host=host, user=user, ssh_key=key, default=default or is_first
        )
    )
    config.save_servers(servers)
    output.success(f"Сервер {name} добавлен", server=name, host=host)


@server_app.command("init")
def server_init(name: Annotated[str, typer.Argument()]) -> None:
    servers = config.load_servers()
    server = config.find_server(servers, name)
    if server is None:
        raise HostmeError(f"Сервер {name!r} не найден. Сначала `hostme server add`.")

    output.info(f"Устанавливаю Webinoly на {server.name}...")
    webinoly.install(server)
    webinoly.enable_sftp(server)
    output.success(f"Сервер {name} готов (Webinoly установлен)", server=name)


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
    servers = config.load_servers()
    server = config.find_server(servers, name)
    if server is None:
        raise HostmeError(f"Сервер {name!r} не найден")

    sites = config.load_sites()
    remaining = [s for s in sites if s.server == name]
    if remaining and not force:
        domains = ", ".join(s.domain for s in remaining)
        raise HostmeError(
            f"На сервере {name} остались сайты в реестре ({domains}). "
            f"Сначала `hostme <domain> teardown` их, либо повтори с --force."
        )

    servers.remove(server)
    config.save_servers(servers)
    output.success(f"Сервер {name} удалён из реестра", server=name)


# --- domain -----------------------------------------------------------------


@domain_app.command("add")
def domain_add(
    server_name: Annotated[str, typer.Argument()],
    domain: Annotated[str, typer.Argument()],
    default: Annotated[bool, typer.Option("--default")] = False,
) -> None:
    domain = config.normalize_domain(domain)
    servers = config.load_servers()
    server = config.find_server(servers, server_name)
    if server is None:
        raise HostmeError(f"Сервер {server_name!r} не найден")

    if any(d.name == domain for s in servers for d in s.base_domains):
        raise HostmeError(f"Домен {domain} уже зарегистрирован")

    has_default = config.default_base_domain(servers) is not None
    if default:
        for s in servers:
            for d in s.base_domains:
                d.default = False
    server.base_domains.append(config.BaseDomain(name=domain, default=default or not has_default))
    config.save_servers(servers)
    output.success(f"Домен {domain} зарегистрирован за сервером {server_name}", domain=domain)


@domain_app.command("default")
def domain_default(domain: Annotated[str, typer.Argument()]) -> None:
    domain = config.normalize_domain(domain)
    servers = config.load_servers()
    target = next((d for s in servers for d in s.base_domains if d.name == domain), None)
    if target is None:
        raise HostmeError(f"Домен {domain!r} не зарегистрирован. Сначала `hostme domain add`.")

    for s in servers:
        for d in s.base_domains:
            d.default = d is target
    config.save_servers(servers)
    output.success(f"Домен {domain} теперь по умолчанию", domain=domain)


@domain_app.command("list")
def domain_list_cmd() -> None:
    servers = config.load_servers()
    rows = [(s.name, d) for s in servers for d in s.base_domains]
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


# --- deploy / list / open / teardown ----------------------------------------


def _detect_site_type(local_path: Path) -> webinoly.SiteType:
    return "php" if any(local_path.rglob("*.php")) else "html"


@app.command("_deploy", hidden=True)
def deploy(
    path: Annotated[str, typer.Argument()],
    domain: Annotated[str | None, typer.Argument()] = None,
    server_name: Annotated[str | None, typer.Option("--server")] = None,
) -> None:
    local_path = Path(path).expanduser().resolve()
    if not local_path.is_dir():
        raise HostmeError(f"{local_path} не является директорией")

    servers = config.load_servers()
    sites = config.load_sites()

    if domain is None:
        domain = config.default_domain(str(local_path), servers)
        if domain is None:
            raise HostmeError(
                "Домен не указан, и нет ни одного служебного домена по умолчанию. "
                "Укажи домен явно или сначала `hostme domain add`."
            )
    else:
        domain = config.normalize_domain(domain)

    server = config.resolve_server(servers, sites, domain, explicit_server=server_name)
    if server is None:
        raise HostmeError(
            f"Не удалось определить сервер для домена {domain}. Укажи --server явно."
        )

    config.check_collision(sites, domain, str(local_path))

    site_type = _detect_site_type(local_path)
    is_new_site = not webinoly.site_exists(server, domain)
    if is_new_site:
        output.info(f"Создаю сайт {domain} ({site_type}) на {server.name}...")
        webinoly.create_site(server, domain, site_type)

        base_domain = next(
            (
                d.name
                for d in server.base_domains
                if domain != d.name and domain.endswith(f".{d.name}")
            ),
            None,
        )
        if base_domain is not None:
            webinoly.enable_ssl(server, domain, add_to_wildcard=base_domain)
        else:
            webinoly.enable_ssl(server, domain)

    # Пишем в реестр сразу после создания сайта на сервере (deployed_at ещё None) —
    # если rsync/chown ниже упадёт, сайт всё равно останется виден в `list`/`teardown`,
    # а не осиротеет молча (создан на сервере, но не отслеживается локально).
    existing = next((s for s in sites if s.domain == domain), None)
    if existing is not None:
        sites.remove(existing)
    site_record = config.Site(
        domain=domain,
        server=server.name,
        local_path=str(local_path),
        php=(site_type == "php"),
        # Сохраняем привязку к include-файлу (sites.d/*.yaml), если сайт уже там
        # жил — иначе редеплой перенёс бы его обратно в главный sites.yaml.
        source_file=existing.source_file if existing is not None else None,
    )
    sites.append(site_record)
    config.save_sites(sites)

    # Releases-схема (TODO 3.2): htdocs — симлинк на releases/<ts>, заливка идёт
    # в новую директорию, а не поверх текущей — старый релиз остаётся как бэкап
    # и откатывается через `rollback` без повторной заливки файлов.
    webinoly.ensure_releases_layout(server, domain)
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    release = webinoly.release_path(domain, ts)
    output.info(f"Заливаю файлы в новый релиз {ts}...")
    rsync_to(str(local_path), server, release)
    webinoly.fix_ownership_path(server, release)
    webinoly.switch_release(server, domain, ts)
    webinoly.prune_releases(server, domain)

    site_record.deployed_at = datetime.now(UTC).isoformat()
    config.save_sites(sites)

    output.success(f"Deployed to https://{domain}", url=f"https://{domain}", domain=domain)


@app.command("list")
def list_sites_cmd() -> None:
    sites = config.load_sites()
    if output.is_json_mode():
        output.info(
            "sites",
            sites=[
                {
                    "domain": s.domain,
                    "server": s.server,
                    "php": s.php,
                    "deployed_at": s.deployed_at,
                }
                for s in sites
            ],
        )
        return
    if not sites:
        output.console.print("Сайтов пока нет.")
        return
    for s in sites:
        kind = "php" if s.php else "html"
        output.console.print(f"https://{s.domain}  [{kind}]  {s.server}  {s.deployed_at or ''}")


@app.command("open")
def open_site(domain: Annotated[str, typer.Argument()]) -> None:
    webbrowser.open(f"https://{domain}")
    output.success(f"Открываю https://{domain}")


def _require_site_server(domain: str) -> tuple[config.Site, config.Server]:
    sites = config.load_sites()
    site = next((s for s in sites if s.domain == domain), None)
    if site is None:
        raise HostmeError(f"Сайт {domain} не найден в реестре")
    servers = config.load_servers()
    server = config.find_server(servers, site.server)
    if server is None:
        raise HostmeError(f"Сервер {site.server!r} для сайта {domain} не найден в конфиге")
    return site, server


@app.command("revs")
def revs(domain: Annotated[str, typer.Argument()]) -> None:
    """Вызов: hostme <domain> revs — список релизов сайта."""
    domain = config.normalize_domain(domain)
    _site, server = _require_site_server(domain)
    releases = webinoly.list_releases(server, domain)
    current = webinoly.current_release(server, domain)
    if output.is_json_mode():
        output.info("revs", domain=domain, current=current, releases=releases)
        return
    if not releases:
        output.console.print("Релизов пока нет.")
        return
    for r in releases:
        output.console.print(f"{r}{' (current)' if r == current else ''}")


@app.command("rollback")
def rollback(domain: Annotated[str, typer.Argument()]) -> None:
    """Вызов: hostme <domain> rollback — откатить на предыдущий релиз."""
    domain = config.normalize_domain(domain)
    _site, server = _require_site_server(domain)
    releases = webinoly.list_releases(server, domain)
    current = webinoly.current_release(server, domain)
    if current is None or current not in releases:
        raise HostmeError(f"Не удалось определить текущий релиз {domain}")
    idx = releases.index(current)
    if idx == 0:
        raise HostmeError(f"У {domain} нет более старого релиза для отката (текущий — самый старый: {current})")
    target = releases[idx - 1]
    webinoly.switch_release(server, domain, target)
    output.success(f"{domain} откачен на релиз {target}", domain=domain, release=target)


@app.command("rollfore")
def rollfore(domain: Annotated[str, typer.Argument()]) -> None:
    """Вызов: hostme <domain> rollfore — вернуть на следующий (после rollback) релиз."""
    domain = config.normalize_domain(domain)
    _site, server = _require_site_server(domain)
    releases = webinoly.list_releases(server, domain)
    current = webinoly.current_release(server, domain)
    if current is None or current not in releases:
        raise HostmeError(f"Не удалось определить текущий релиз {domain}")
    idx = releases.index(current)
    if idx >= len(releases) - 1:
        raise HostmeError(f"У {domain} нет более нового релиза (текущий — самый новый: {current})")
    target = releases[idx + 1]
    webinoly.switch_release(server, domain, target)
    output.success(f"{domain} переключён на релиз {target}", domain=domain, release=target)


@app.command("teardown")
def teardown(
    domain: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Вызов: hostme <domain> teardown [--yes] — снести сайт и убрать из реестра."""
    domain = config.normalize_domain(domain)
    servers = config.load_servers()
    sites = config.load_sites()

    site = next((s for s in sites if s.domain == domain), None)
    if site is None:
        raise HostmeError(f"Сайт {domain} не найден в реестре")

    if not yes and not output.is_json_mode() and not typer.confirm(
        f"Снести сайт {domain} на сервере (файлы + SSL) и убрать из реестра?"
    ):
        output.info("Отменено")
        raise typer.Exit(code=1)

    server = config.find_server(servers, site.server)
    if server is None:
        raise HostmeError(f"Сервер {site.server!r} для сайта {domain} не найден в конфиге")

    webinoly.delete_site(server, domain)
    sites.remove(site)
    config.save_sites(sites)
    output.success(f"Сайт {domain} удалён", domain=domain)


@app.command("auth")
def auth(
    domain: Annotated[str, typer.Argument()],
    user: Annotated[str | None, typer.Option("--user")] = None,
    password: Annotated[str | None, typer.Option("--pass")] = None,
    off: Annotated[bool, typer.Option("--off")] = False,
) -> None:
    """Вызов: hostme <domain> auth --user U --pass P (или --off) — password protection."""
    domain = config.normalize_domain(domain)
    servers = config.load_servers()
    sites = config.load_sites()

    site = next((s for s in sites if s.domain == domain), None)
    if site is None:
        raise HostmeError(f"Сайт {domain} не найден в реестре")
    server = config.find_server(servers, site.server)
    if server is None:
        raise HostmeError(f"Сервер {site.server!r} для сайта {domain} не найден в конфиге")

    if off:
        webinoly.disable_http_auth(server, domain)
        site.password_protect = None
        config.save_sites(sites)
        output.success(f"Пароль снят с {domain}", domain=domain)
        return

    if not user or not password:
        raise HostmeError("Укажи --user и --pass, либо --off чтобы снять защиту")

    webinoly.set_http_auth(server, domain, user, password)
    # Пароль на сервер уже ушёл в открытом виде (PRD §13.2 — решено: `--pass` в
    # аргументе командной строки ок для MVP, single user/локальная машина) —
    # локально в реестре его не храним, только факт защиты и логин.
    site.password_protect = {"enabled": True, "user": user}
    config.save_sites(sites)
    output.success(f"Сайт {domain} защищён паролем (юзер {user})", domain=domain)


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
) -> None:
    """Вызов: hostme <domain> config [--cors ...] [--redirect FROM=TO] [...] — настройки сайта; без флагов печатает текущие."""
    domain = config.normalize_domain(domain)
    if no_force_https:
        raise HostmeError(
            "Webinoly всегда включает редирект HTTP→HTTPS вместе с -ssl=on и не даёт его "
            "отключить (см. docs/webinoly.md) — --no-force-https не поддерживается"
        )

    sites = config.load_sites()
    site = next((s for s in sites if s.domain == domain), None)
    if site is None:
        raise HostmeError(f"Сайт {domain} не найден в реестре")

    if force_https and not (cors or no_cors or redirect or remove_redirect):
        output.success(
            f"Force-https для {domain} уже всегда включён вместе с SSL (Webinoly, docs/webinoly.md) — "
            f"ничего делать не нужно",
            domain=domain,
        )
        return

    has_changes = bool(cors) or no_cors or bool(redirect) or bool(remove_redirect)
    if not has_changes:
        _print_site_config(site)
        return

    servers = config.load_servers()
    server = config.find_server(servers, site.server)
    if server is None:
        raise HostmeError(f"Сервер {site.server!r} для сайта {domain} не найден в конфиге")

    for pair in redirect:
        frm, sep, to = pair.partition("=")
        if not sep:
            raise HostmeError(f"--redirect ожидает вид FROM=TO, получено {pair!r}")
        webinoly.add_redirect(server, domain, frm, to)
        site.redirects = [r for r in site.redirects if r["from"] != frm]
        site.redirects.append({"from": frm, "to": to})

    for frm in remove_redirect:
        webinoly.remove_redirect(server, domain, frm)
        site.redirects = [r for r in site.redirects if r["from"] != frm]

    if no_cors:
        webinoly.set_cors(server, domain, [])
        site.cors = []
    elif cors:
        webinoly.set_cors(server, domain, cors)
        site.cors = list(cors)

    config.save_sites(sites)
    output.success(f"Настройки {domain} обновлены", domain=domain)


def _http_status(domain: str, timeout: float = 8.0) -> str:
    req = urllib.request.Request(f"https://{domain}", method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception as exc:  # noqa: BLE001
        return f"ошибка: {exc}"


@app.command("debug")
def debug(
    domain: Annotated[str, typer.Argument()],
    error: Annotated[bool, typer.Option("--error")] = False,
    lines: Annotated[int, typer.Option("--lines")] = 10,
) -> None:
    """Вызов: hostme <domain> debug [--error] [--lines N] — HTTP-статус + хвост лога."""
    domain = config.normalize_domain(domain)
    sites = config.load_sites()
    site = next((s for s in sites if s.domain == domain), None)
    if site is None:
        raise HostmeError(f"Сайт {domain} не найден в реестре")
    servers = config.load_servers()
    server = config.find_server(servers, site.server)
    if server is None:
        raise HostmeError(f"Сервер {site.server!r} для сайта {domain} не найден в конфиге")

    status = _http_status(domain)
    log_output = webinoly.tail_log(server, domain, error=error, lines=lines)

    if output.is_json_mode():
        output.info("debug", domain=domain, http_status=status, log=log_output)
        return
    output.console.print(f"https://{domain} -> {status}")
    output.console.print(f"--- {'error' if error else 'access'} log (последние {lines}) ---")
    output.console.print(log_output or "(пусто)")


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
        output.error(str(exc))
    except Exception as exc:  # noqa: BLE001 — не даём агенту голый трейсбек
        output.error(f"Неожиданная ошибка: {exc}")


if __name__ == "__main__":
    main()
