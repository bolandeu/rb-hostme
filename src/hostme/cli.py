from __future__ import annotations

import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape as rich_escape

from hostme import config, ftp, output, webinoly
from hostme.errors import HostmeError
from hostme.ssh import rsync_from_target, rsync_to, rsync_to_target

# Форма команд копирует surge.sh (AGENTS.md): `hostme <path> [domain]` для деплоя,
# `hostme <domain> <subcommand>` для управления — без промежуточных слов вроде "deploy".
# Typer/Click умеет только статическое дерево подкоманд, поэтому реальный argv
# переписывается в explicit-подкоманды (_translate_argv) до того, как его увидит Typer.
_TOP_LEVEL_COMMANDS = {"server", "domain", "target", "list", "open", "help", "--help", "-h"}
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
    ("hostme <domain> rollback", "откатить сайт на предыдущий релиз"),
    ("hostme <domain> rollfore", "вернуть сайт на следующий (после rollback) релиз"),
    ("hostme list", "таблица сайтов из реестра + служебные домены без деплоя через hostme (помечены отдельно)"),
    ("hostme open <domain>", "открыть сайт в браузере"),
    ("hostme server add --name N --host H --user U [--key PATH] [--default]", "зарегистрировать сервер"),
    ("hostme server init <name>", "поставить/проверить Webinoly на сервере"),
    ("hostme server update <name>", "обновить сам Webinoly на сервере (не пакеты)"),
    ("hostme server list", "таблица серверов"),
    ("hostme server remove <name> [--force]", "убрать сервер из реестра"),
    ("hostme domain add <server> <domain> [--default]", "зарегистрировать служебный (base) домен"),
    ("hostme domain default <domain>", "сделать домен дефолтным (для авто-генерации поддоменов)"),
    ("hostme domain list", "таблица служебных доменов"),
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
        "hostme <domain> teardown --yes / rollback --yes (для target-сайтов)",
        "то же самое правило подтверждения, что и у deploy на target — --json не байпасит",
    ),
    ("--json (глобальный флаг, до остальных)", "чистый JSON вместо rich-вывода, без цвета — для агентов"),
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
    json_output: bool = typer.Option(
        False, "--json", help="Машиночитаемый вывод (для агентов)."
    ),
) -> None:
    output.set_json_mode(json_output)


# --- server ---------------------------------------------------------------


def _require_unique_name(name: str) -> None:
    """servers.yaml и targets.yaml делят одно пространство имён (Site.server
    резолвится в любой из них по имени без квалификатора) — нельзя допустить
    коллизию между `hostme server add` и `hostme target add`."""
    if config.find_server(config.load_servers(), name) is not None:
        raise HostmeError(f"Имя {name!r} уже занято сервером (hostme server list)")
    if config.find_target(config.load_targets(), name) is not None:
        raise HostmeError(f"Имя {name!r} уже занято target'ом (hostme target list)")


@server_app.command("add")
def server_add(
    name: Annotated[str, typer.Option("--name")],
    host: Annotated[str, typer.Option("--host")],
    user: Annotated[str, typer.Option("--user")] = "root",
    key: Annotated[str, typer.Option("--key")] = "~/.ssh/id_ed25519",
    default: Annotated[bool, typer.Option("--default")] = False,
) -> None:
    _require_unique_name(name)
    servers = config.load_servers()

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


@server_app.command("update")
def server_update(name: Annotated[str, typer.Argument()]) -> None:
    """Обновить сам Webinoly на сервере (`sudo webinoly -update`) — не пакеты
    сервера (nginx/php/mysql), только сам Webinoly."""
    servers = config.load_servers()
    server = config.find_server(servers, name)
    if server is None:
        raise HostmeError(f"Сервер {name!r} не найден")

    output.info(f"Обновляю Webinoly на {server.name}...")
    webinoly.update_webinoly(server)
    output.success(f"Webinoly на {name} обновлён", server=name)


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
    if connection not in ("ssh", "ftp", "sftp"):
        raise HostmeError(f"--connection должен быть ssh/ftp/sftp, получено {connection!r}")
    if not password and not ssh_key:
        raise HostmeError("Укажи --password или --ssh-key")
    if connection in ("ftp", "sftp") and not password:
        raise HostmeError(f"--connection={connection} требует --password (ssh_key не подходит для {connection})")

    _require_unique_name(name)
    targets = config.load_targets()
    targets.append(
        config.Target(
            name=name,
            connection=connection,  # type: ignore[arg-type]
            host=host,
            user=user,
            remote_path=remote_path,
            password=password,
            ssh_key=ssh_key,
        )
    )
    config.save_targets(targets)
    output.success(f"Target {name} добавлен", target=name, host=host, connection=connection)


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
    targets = config.load_targets()
    target = config.find_target(targets, name)
    if target is None:
        raise HostmeError(f"Target {name!r} не найден")

    sites = config.load_sites()
    remaining = [s for s in sites if s.server == name]
    if remaining and not force:
        domains = ", ".join(s.domain for s in remaining)
        raise HostmeError(
            f"На target {name} остались сайты в реестре ({domains}). "
            f"Сначала `hostme <domain> teardown` их, либо повтори с --force."
        )

    targets.remove(target)
    config.save_targets(targets)
    output.success(f"Target {name} удалён из реестра", target=name)


# --- deploy / list / open / teardown ----------------------------------------


def _detect_site_type(local_path: Path) -> webinoly.SiteType:
    return "php" if any(local_path.rglob("*.php")) else "html"


def _confirm_target_action(action: str, target: config.Target, yes: bool) -> None:
    """Target — сторонний хостинг (не наш VPS), часто чужая/клиентская
    инфраструктура. В отличие от teardown на своём сервере, --json НЕ пропускает
    это подтверждение молча — иначе агент, которому по инструкции положено всегда
    звать с --json, получил бы возможность деплоить/сносить/откатывать чужой сайт
    без единого явного "да" от человека на КОНКРЕТНОЕ действие. Пропустить можно
    только явным --yes — то есть кто бы ни звал команду, обязан осознанно решить
    пропустить подтверждение, а не получить его в подарок за --json."""
    if yes:
        return
    if output.is_json_mode():
        raise HostmeError(
            f"{action} на target {target.name!r} (сторонний хостинг) требует явного --yes "
            f"даже при --json — не выполнять без подтверждения человека на это конкретное действие"
        )
    if not typer.confirm(f"{action} на target {target.name!r} ({target.connection}, сторонний хостинг). Продолжить?"):
        output.info("Отменено")
        raise typer.Exit(code=1)


_KEEP_TARGET_BACKUPS = 5


def _target_backup_dir(target_name: str) -> Path:
    return config.TARGET_BACKUPS_DIR / target_name


def _target_backup_snapshots(target_name: str) -> list[Path]:
    backups_dir = _target_backup_dir(target_name)
    if not backups_dir.is_dir():
        return []
    return sorted(p for p in backups_dir.iterdir() if p.is_dir())


def _prune_target_backups(target_name: str, keep: int = _KEEP_TARGET_BACKUPS) -> None:
    snapshots = _target_backup_snapshots(target_name)
    for old in snapshots[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


def _backup_target_before_deploy(target: config.Target) -> None:
    """Бэкап перед деплоем на Target — скачиваем текущее содержимое remote_path
    в локальный снепшот ДО заливки нового. Работает одинаково для ssh/ftp/sftp
    (просто ещё один `mirror`/rsync в обратную сторону) — в отличие от Webinoly-
    releases не нужен shell на сервере (у shared-хостингов часто его нет вовсе).
    Best-effort: если скачивать нечего (первый деплой на этот target, remote_path
    ещё не существует) — не роняем весь деплой, просто предупреждаем."""
    backups_dir = _target_backup_dir(target.name)
    backups_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    snapshot = backups_dir / ts
    snapshot.mkdir(mode=0o700)
    try:
        if target.connection == "ssh":
            rsync_from_target(target, str(snapshot))
        else:
            ftp.mirror_from(target, str(snapshot))
    except HostmeError as exc:
        shutil.rmtree(snapshot, ignore_errors=True)
        output.info(f"Бэкап перед деплоем не удался (возможно, это первый деплой на {target.name}): {exc}")
        return
    _prune_target_backups(target.name)


def _deploy_to_target(local_path: Path, domain: str | None, target_name: str, yes: bool) -> None:
    """Деплой на сторонний хостинг (ftp/sftp/ssh, без Webinoly) — просто залить
    файлы, никакого create_site/SSL/releases (хостер уже сам всё настроил)."""
    if domain is None:
        raise HostmeError(
            "Для --target домен нужно указывать явно — у сторонних хостингов нет "
            "служебных (base) доменов для авто-генерации поддомена."
        )
    domain = config.normalize_domain(domain)

    target = config.find_target(config.load_targets(), target_name)
    if target is None:
        raise HostmeError(f"Target {target_name!r} не найден. Сначала `hostme target add`.")

    _confirm_target_action(f"Деплой {domain}", target, yes)

    sites = config.load_sites()
    config.check_collision(sites, domain, str(local_path))

    _backup_target_before_deploy(target)

    output.info(f"Заливаю файлы на {target.name} ({target.connection})...")
    if target.connection == "ssh":
        rsync_to_target(str(local_path), target)
    else:
        ftp.mirror_to(str(local_path), target)

    existing = next((s for s in sites if s.domain == domain), None)
    if existing is not None:
        sites.remove(existing)
    sites.append(
        config.Site(
            domain=domain,
            server=target.name,
            local_path=str(local_path),
            deployed_at=datetime.now(UTC).isoformat(),
            source_file=existing.source_file if existing is not None else None,
        )
    )
    config.save_sites(sites)
    output.success(f"Залито на {target.name}", target=target.name, domain=domain)


def _teardown_target(target: config.Target) -> None:
    """Для target нет понятия "сайт" на удалённой стороне (хостер уже сам всё
    настроил) — teardown тут значит "убрать то, что мы туда залили". Не пишем
    отдельную команду удаления по SSH/FTP — переиспользуем тот же transport,
    что и deploy, просто с ПУСТОЙ локальной папкой: rsync/lftp --delete сами
    сотрут всё существующее на той стороне."""
    empty_dir = tempfile.mkdtemp(prefix="hostme-empty-")
    try:
        if target.connection == "ssh":
            rsync_to_target(empty_dir, target)
        else:
            ftp.mirror_to(empty_dir, target)
    finally:
        os.rmdir(empty_dir)


@app.command("_deploy", hidden=True)
def deploy(
    path: Annotated[str, typer.Argument()],
    domain: Annotated[str | None, typer.Argument()] = None,
    server_name: Annotated[str | None, typer.Option("--server")] = None,
    target_name: Annotated[str | None, typer.Option("--target")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    local_path = Path(path).expanduser().resolve()
    if not local_path.is_dir():
        raise HostmeError(f"{local_path} не является директорией")

    if target_name is not None:
        _deploy_to_target(local_path, domain, target_name, yes)
        return

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
    servers = config.load_servers()
    site_domains = {s.domain for s in sites}
    # Служебные (base) домены сами по себе не "сайты" (никогда не проходили
    # через hostme <path> <domain>), но домен на сервере реально есть (обычно
    # заглушка «Сайт в разработке» под будущие поддомены) — не показывать их
    # тут молча "как будто их нет", а явно пометить как служебные без деплоя.
    bare_base_domains = [
        (d.name, s.name) for s in servers for d in s.base_domains if d.name not in site_domains
    ]

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


def _find_site(domain: str) -> config.Site:
    site = next((s for s in config.load_sites() if s.domain == domain), None)
    if site is None:
        raise HostmeError(f"Сайт {domain} не найден в реестре")
    return site


def _require_site_server(domain: str) -> tuple[config.Site, config.Server]:
    """Для команд, которые умеют работать ТОЛЬКО с Webinoly-сервером (auth/config/
    debug/revs/rollback/rollfore — весь их смысл завязан на Webinoly). Если сайт
    задеплоен на Target (сторонний хостинг) — понятная ошибка вместо "сервер не
    найден в конфиге" (дело не в отсутствующем конфиге, а в том, что фича
    Webinoly-специфична и для target'ов не имеет смысла)."""
    site = _find_site(domain)
    server = config.find_server(config.load_servers(), site.server)
    if server is not None:
        return site, server
    target = config.find_target(config.load_targets(), site.server)
    if target is not None:
        raise HostmeError(
            f"{domain} задеплоен на target {site.server!r} (сторонний хостинг, "
            f"connection={target.connection}) — эта команда Webinoly-специфична, "
            f"для target'ов не поддерживается"
        )
    raise HostmeError(f"Сервер {site.server!r} для сайта {domain} не найден в конфиге")


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


def _rollback_target(target: config.Target) -> None:
    """Одношаговый откат для Target — нет полноценной истории с указателем
    "текущей" позиции, как у Webinoly-releases (там она на сервере, тут только
    локальные снепшоты) — просто заливаем самый свежий локальный бэкап обратно."""
    snapshots = _target_backup_snapshots(target.name)
    if not snapshots:
        raise HostmeError(f"У target {target.name!r} нет локальных бэкапов для отката")
    snapshot = snapshots[-1]
    if target.connection == "ssh":
        rsync_to_target(str(snapshot), target)
    else:
        ftp.mirror_to(str(snapshot), target)


@app.command("rollback")
def rollback(
    domain: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Вызов: hostme <domain> rollback [--yes] — откатить на предыдущий релиз
    (сервер) или последний локальный бэкап (target, требует --yes/подтверждения —
    сторонний хостинг)."""
    domain = config.normalize_domain(domain)
    site = _find_site(domain)

    server = config.find_server(config.load_servers(), site.server)
    if server is not None:
        releases = webinoly.list_releases(server, domain)
        current = webinoly.current_release(server, domain)
        if current is None or current not in releases:
            raise HostmeError(f"Не удалось определить текущий релиз {domain}")
        idx = releases.index(current)
        if idx == 0:
            raise HostmeError(f"У {domain} нет более старого релиза для отката (текущий — самый старый: {current})")
        release = releases[idx - 1]
        webinoly.switch_release(server, domain, release)
        output.success(f"{domain} откачен на релиз {release}", domain=domain, release=release)
        return

    site_target = config.find_target(config.load_targets(), site.server)
    if site_target is None:
        raise HostmeError(f"Сервер/target {site.server!r} для сайта {domain} не найден в конфиге")
    _confirm_target_action(f"Rollback {domain}", site_target, yes)
    _rollback_target(site_target)
    output.success(f"{domain} откачен на предыдущий бэкап", domain=domain, target=site_target.name)


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
    """Вызов: hostme <domain> teardown [--yes] — снести сайт и убрать из реестра.
    Для target-сайтов (сторонний хостинг) --json НЕ пропускает подтверждение
    молча — нужен явный --yes (см. _confirm_target_action)."""
    domain = config.normalize_domain(domain)
    site = _find_site(domain)

    server = config.find_server(config.load_servers(), site.server)
    target = None if server is not None else config.find_target(config.load_targets(), site.server)

    if target is not None:
        _confirm_target_action(f"Teardown {domain}", target, yes)
    elif not yes and not output.is_json_mode() and not typer.confirm(
        f"Снести сайт {domain} и убрать из реестра?"
    ):
        output.info("Отменено")
        raise typer.Exit(code=1)

    if server is not None:
        webinoly.delete_site(server, domain)
    else:
        if target is None:
            raise HostmeError(f"Сервер/target {site.server!r} для сайта {domain} не найден в конфиге")
        _teardown_target(target)

    sites = config.load_sites()
    sites.remove(next(s for s in sites if s.domain == domain))
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
    _require_site_server(domain)  # только валидация — упадёт понятной ошибкой для target'ов
    sites = config.load_sites()
    site = next(s for s in sites if s.domain == domain)
    server = config.find_server(config.load_servers(), site.server)

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
    nginx_snippet: Annotated[str | None, typer.Option("--nginx-snippet")] = None,
    no_nginx_snippet: Annotated[bool, typer.Option("--no-nginx-snippet")] = False,
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

    if nginx_snippet and no_nginx_snippet:
        raise HostmeError("--nginx-snippet и --no-nginx-snippet вместе не имеют смысла")

    snippet_content: str | None = None
    if nginx_snippet:
        snippet_path = Path(nginx_snippet).expanduser()
        if not snippet_path.is_file():
            raise HostmeError(f"{snippet_path} не найден")
        snippet_content = snippet_path.read_text()

    has_changes = bool(cors) or no_cors or bool(redirect) or bool(remove_redirect) or bool(nginx_snippet) or no_nginx_snippet
    if not has_changes:
        _print_site_config(site)
        return

    _site, server = _require_site_server(domain)

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

    if no_nginx_snippet:
        webinoly.set_custom_nginx_snippet(server, domain, "")
    elif snippet_content is not None:
        webinoly.set_custom_nginx_snippet(server, domain, snippet_content)

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
    _site, server = _require_site_server(domain)

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
