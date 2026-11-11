"""Бизнес-логика hostme — деплой/управление сайтами и реестром серверов/
targets. Команды в commands/ — только парсинг аргументов и вызов функций
отсюда; сюда же попадает единая точка подтверждения деструктивных операций
(`output.require_confirmation`, раздел 10 architecture.md). Функции, которым
нужен режим вывода (dry-run, подтверждение, прогресс), получают `ctx` команды."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from hostme import config, output
from hostme.core.errors import InvalidArguments, StateError
from hostme.credentials import manager as credentials
from hostme.providers import ftp, http, webinoly
from hostme.providers.ssh import rsync_from_target, rsync_to, rsync_to_target

if TYPE_CHECKING:
    import typer

MAINTENANCE_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "maintenance"

# --- server -------------------------------------------------------------


def require_unique_name(name: str) -> None:
    """servers.yaml и targets.yaml делят одно пространство имён (Site.server
    резолвится в любой из них по имени без квалификатора) — нельзя допустить
    коллизию между `hostme server add` и `hostme target add`."""
    if config.find_server(config.load_servers(), name) is not None:
        raise InvalidArguments(f"Имя {name!r} уже занято сервером (hostme server list)")
    if config.find_target(config.load_targets(), name) is not None:
        raise InvalidArguments(f"Имя {name!r} уже занято target'ом (hostme target list)")


def add_server(name: str, host: str, user: str, key: str, default: bool) -> dict:
    require_unique_name(name)
    servers = config.load_servers()
    if default:
        for s in servers:
            s.default = False
    is_first = not servers
    server = config.Server(name=name, host=host, user=user, ssh_key=key, default=default or is_first)
    servers.append(server)
    config.save_servers(servers)
    return {"message": f"Сервер {name} добавлен", "server": name, "host": host}


def init_server(ctx: typer.Context, name: str) -> dict:
    servers = config.load_servers()
    server = config.find_server(servers, name)
    if server is None:
        raise InvalidArguments(f"Сервер {name!r} не найден. Сначала `hostme server add`.")
    output.progress(ctx, f"Устанавливаю Webinoly на {server.name}...")
    webinoly.install(server)
    webinoly.enable_sftp(server)
    return {"message": f"Сервер {name} готов (Webinoly установлен)", "server": name}


def update_server(ctx: typer.Context, name: str) -> dict:
    """Обновить сам Webinoly на сервере (`sudo webinoly -update`) — не пакеты
    сервера (nginx/php/mysql), только сам Webinoly. Затем перезалить nginx-дефолты
    всем сайтам сервера из реестра: так их получают и сайты, которые давно не
    деплоились, после обновления самого hostme."""
    servers = config.load_servers()
    server = config.find_server(servers, name)
    if server is None:
        raise InvalidArguments(f"Сервер {name!r} не найден")
    output.progress(ctx, f"Обновляю Webinoly на {server.name}...")
    webinoly.update_webinoly(server)
    domains = [s.domain for s in config.load_sites() if s.server == name]
    for domain in domains:
        output.progress(ctx, f"nginx-дефолты: {domain}...")
        webinoly.apply_site_defaults(server, domain)
    return {
        "message": f"Webinoly на {name} обновлён, nginx-дефолты у {len(domains)} сайтов",
        "server": name,
        "sites": domains,
    }


def remove_server(name: str, force: bool) -> dict:
    servers = config.load_servers()
    server = config.find_server(servers, name)
    if server is None:
        raise InvalidArguments(f"Сервер {name!r} не найден")

    sites = config.load_sites()
    remaining = [s for s in sites if s.server == name]
    if remaining and not force:
        domains = ", ".join(s.domain for s in remaining)
        raise InvalidArguments(
            f"На сервере {name} остались сайты в реестре ({domains}). "
            f"Сначала `hostme <domain> teardown` их, либо повтори с --force."
        )

    servers.remove(server)
    config.save_servers(servers)
    return {"message": f"Сервер {name} удалён из реестра", "server": name}


# --- domain ---------------------------------------------------------------


def add_domain(server_name: str, domain: str, default: bool) -> dict:
    domain = config.normalize_domain(domain)
    servers = config.load_servers()
    server = config.find_server(servers, server_name)
    if server is None:
        raise InvalidArguments(f"Сервер {server_name!r} не найден")

    if any(d.name == domain for s in servers for d in s.base_domains):
        raise InvalidArguments(f"Домен {domain} уже зарегистрирован")

    has_default = config.default_base_domain(servers) is not None
    if default:
        for s in servers:
            for d in s.base_domains:
                d.default = False
    server.base_domains.append(config.BaseDomain(name=domain, default=default or not has_default))
    config.save_servers(servers)
    return {"message": f"Домен {domain} зарегистрирован за сервером {server_name}", "domain": domain}


def set_default_domain(domain: str) -> dict:
    domain = config.normalize_domain(domain)
    servers = config.load_servers()
    target = next((d for s in servers for d in s.base_domains if d.name == domain), None)
    if target is None:
        raise InvalidArguments(f"Домен {domain!r} не зарегистрирован. Сначала `hostme domain add`.")

    for s in servers:
        for d in s.base_domains:
            d.default = d is target
    config.save_servers(servers)
    return {"message": f"Домен {domain} теперь по умолчанию", "domain": domain}


def list_domains() -> list[tuple[str, config.BaseDomain]]:
    servers = config.load_servers()
    return [(s.name, d) for s in servers for d in s.base_domains]


def remove_domain(domain: str) -> dict:
    domain = config.normalize_domain(domain)
    servers = config.load_servers()
    server = next((s for s in servers if any(d.name == domain for d in s.base_domains)), None)
    if server is None:
        raise InvalidArguments(f"Домен {domain!r} не зарегистрирован")

    target = next(d for d in server.base_domains if d.name == domain)
    was_default = target.default
    server.base_domains.remove(target)

    remaining = [d for s in servers for d in s.base_domains]
    if was_default and remaining:
        remaining[0].default = True

    config.save_servers(servers)
    return {"message": f"Домен {domain} удалён из реестра", "domain": domain}


# --- target (сторонний хостинг, ftp/sftp/ssh, без Webinoly) ---------------


def add_target(
    name: str,
    connection: str,
    host: str,
    user: str,
    password: str | None,
    ssh_key: str | None,
    remote_path: str,
) -> dict:
    if connection not in ("ssh", "ftp", "sftp"):
        raise InvalidArguments(f"--connection должен быть ssh/ftp/sftp, получено {connection!r}")
    # Без --password — пароль, уже заданный в HOSTME_DEPLOY_<NAME>_PASSWORD (сервер под doppler) или в keychain.
    password = password or credentials.get_secret(name)
    if not password and not ssh_key:
        raise InvalidArguments(f"Укажи --password (или {credentials.env_var_name(name)}) либо --ssh-key")
    if connection in ("ftp", "sftp") and not password:
        raise InvalidArguments(f"--connection={connection} требует --password (ssh_key не подходит для {connection})")

    require_unique_name(name)
    targets = config.load_targets()
    target = config.Target(
        name=name,
        connection=connection,  # type: ignore[arg-type]
        host=host,
        user=user,
        remote_path=remote_path,
        password=password,
        ssh_key=ssh_key,
    )
    targets.append(target)
    config.save_targets(targets)
    return {"message": f"Target {name} добавлен", "target": name, "host": host, "connection": connection}


def remove_target(name: str, force: bool) -> dict:
    targets = config.load_targets()
    target = config.find_target(targets, name)
    if target is None:
        raise InvalidArguments(f"Target {name!r} не найден")

    sites = config.load_sites()
    remaining = [s for s in sites if s.server == name]
    if remaining and not force:
        domains = ", ".join(s.domain for s in remaining)
        raise InvalidArguments(
            f"На target {name} остались сайты в реестре ({domains}). "
            f"Сначала `hostme <domain> teardown` их, либо повтори с --force."
        )

    targets.remove(target)
    config.save_targets(targets)
    credentials.delete_secret(name)
    return {"message": f"Target {name} удалён из реестра", "target": name}


# --- deploy / list / teardown ----------------------------------------------


def detect_site_type(local_path: Path) -> webinoly.SiteType:
    return "php" if any(local_path.rglob("*.php")) else "html"


def confirm_target_action(ctx: typer.Context, action: str, target: config.Target, confirm: bool) -> None:
    """Target — сторонний хостинг (не наш VPS), часто чужая/клиентская
    инфраструктура — заметно более строгий гейт, чем у своих серверов."""
    output.require_confirmation(
        ctx, f"{action} на target {target.name!r} ({target.connection}, сторонний хостинг)", confirm
    )


def _target_backup_dir(target_name: str) -> Path:
    return config.TARGET_BACKUPS_DIR / target_name


def _target_backup_snapshots(target_name: str) -> list[Path]:
    backups_dir = _target_backup_dir(target_name)
    if not backups_dir.is_dir():
        return []
    return sorted(p for p in backups_dir.iterdir() if p.is_dir())


def _snapshot_time(snapshot: Path) -> datetime:
    try:
        return datetime.strptime(snapshot.name, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return datetime.fromtimestamp(snapshot.stat().st_mtime, UTC)


def _prune_target_backups(target_name: str, policy: config.BackupPolicy | None = None) -> list[Path]:
    """Политика config.BackupPolicy; самый свежий снепшот не трогаем никогда."""
    policy = policy or config.load_backup_policy()
    snapshots = _target_backup_snapshots(target_name)
    older = snapshots[:-1]
    expired = set(snapshots[: -policy.keep])
    if policy.max_age_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=policy.max_age_days)
        expired.update(p for p in older if _snapshot_time(p) < cutoff)
    removed = sorted(expired)
    for old in removed:
        shutil.rmtree(old, ignore_errors=True)
    return removed


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())


def _human_size(size: float) -> str:
    for unit in ("Б", "КБ", "МБ"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ГБ"


def _backup_target_before_deploy(ctx: typer.Context, target: config.Target) -> None:
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
    except StateError as exc:
        shutil.rmtree(snapshot, ignore_errors=True)
        output.progress(ctx, f"Бэкап перед деплоем не удался (возможно, это первый деплой на {target.name}): {exc}")
        return
    _prune_target_backups(target.name)


def deploy_to_target(
    ctx: typer.Context, local_path: Path, domain: str | None, target_name: str, confirm: bool, rebind: bool = False
) -> dict:
    """Деплой на сторонний хостинг (ftp/sftp/ssh, без Webinoly) — просто залить
    файлы, никакого create_site/SSL/releases (хостер уже сам всё настроил)."""
    if domain is None:
        raise InvalidArguments(
            "Для --target домен нужно указывать явно — у сторонних хостингов нет "
            "служебных (base) доменов для авто-генерации поддомена."
        )
    domain = config.normalize_domain(domain)

    target = config.find_target(config.load_targets(), target_name)
    if target is None:
        raise InvalidArguments(f"Target {target_name!r} не найден. Сначала `hostme target add`.")

    if output.is_dry_run(ctx):
        return {
            "message": f"(dry-run) Задеплоил бы {domain} на target {target.name}, изменений не внесено",
            "target": target.name,
            "domain": domain,
            "dry_run": True,
        }

    confirm_target_action(ctx, f"Деплой {domain}", target, confirm)

    sites = config.load_sites()
    config.check_collision(sites, domain, str(local_path), rebind)

    _backup_target_before_deploy(ctx, target)

    output.progress(ctx, f"Заливаю файлы на {target.name} ({target.connection})...")
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
    return {"message": f"Залито на {target.name}", "target": target.name, "domain": domain}


def teardown_target(target: config.Target) -> None:
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


def deploy(
    ctx: typer.Context,
    path: str,
    domain: str | None,
    server_name: str | None,
    target_name: str | None,
    confirm: bool,
    rebind: bool = False,
) -> dict:
    local_path = Path(path).expanduser().resolve()
    if not local_path.is_dir():
        raise InvalidArguments(f"{local_path} не является директорией")

    if target_name is not None:
        return deploy_to_target(ctx, local_path, domain, target_name, confirm, rebind)

    servers = config.load_servers()
    sites = config.load_sites()

    if domain is None:
        domain = config.default_domain(str(local_path), servers)
        if domain is None:
            raise InvalidArguments(
                "Домен не указан, и нет ни одного служебного домена по умолчанию. "
                "Укажи домен явно или сначала `hostme domain add`."
            )
    else:
        domain = config.normalize_domain(domain)

    server = config.resolve_server(servers, sites, domain, explicit_server=server_name)
    if server is None:
        raise InvalidArguments(f"Не удалось определить сервер для домена {domain}. Укажи --server явно.")

    config.check_collision(sites, domain, str(local_path), rebind)

    if output.is_dry_run(ctx):
        return {
            "message": f"(dry-run) Задеплоил бы {domain} на {server.name}, изменений не внесено",
            "domain": domain,
            "url": f"https://{domain}",
            "dry_run": True,
        }

    site_type = detect_site_type(local_path)
    is_new_site = not webinoly.site_exists(server, domain)
    if is_new_site:
        output.progress(ctx, f"Создаю сайт {domain} ({site_type}) на {server.name}...")
        webinoly.create_site(server, domain, site_type)

        base_domain = next(
            (d.name for d in server.base_domains if domain != d.name and domain.endswith(f".{d.name}")),
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

    # Releases-схема: htdocs — симлинк на releases/<ts>, заливка идёт в новую
    # директорию, а не поверх текущей — старый релиз остаётся как бэкап и
    # откатывается через `rollback` без повторной заливки файлов.
    webinoly.ensure_releases_layout(server, domain)
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    release = webinoly.release_path(domain, ts)
    output.progress(ctx, f"Заливаю файлы в новый релиз {ts}...")
    rsync_to(str(local_path), server, release)
    webinoly.fix_ownership_path(server, release)
    webinoly.apply_site_defaults(server, domain)
    webinoly.switch_release(server, domain, ts)
    webinoly.prune_releases(server, domain)

    site_record.deployed_at = datetime.now(UTC).isoformat()
    config.save_sites(sites)

    return {"message": f"Deployed to https://{domain}", "domain": domain, "url": f"https://{domain}"}


def list_sites() -> tuple[list[config.Site], list[tuple[str, str]]]:
    sites = config.load_sites()
    servers = config.load_servers()
    site_domains = {s.domain for s in sites}
    # Служебные (base) домены сами по себе не "сайты" (никогда не проходили
    # через hostme <path> <domain>), но домен на сервере реально есть (обычно
    # заглушка «Сайт в разработке» под будущие поддомены) — не показывать их
    # тут молча "как будто их нет", а явно пометить как служебные без деплоя.
    bare_base_domains = [(d.name, s.name) for s in servers for d in s.base_domains if d.name not in site_domains]
    return sites, bare_base_domains


def find_site(domain: str) -> config.Site:
    site = next((s for s in config.load_sites() if s.domain == domain), None)
    if site is None:
        raise InvalidArguments(f"Сайт {domain} не найден в реестре")
    return site


def require_site_server(domain: str) -> tuple[config.Site, config.Server]:
    """Для команд, которые умеют работать ТОЛЬКО с Webinoly-сервером (auth/config/
    debug/revs/rollback/rollfore — весь их смысл завязан на Webinoly). Если сайт
    задеплоен на Target (сторонний хостинг) — понятная ошибка вместо "сервер не
    найден в конфиге" (дело не в отсутствующем конфиге, а в том, что фича
    Webinoly-специфична и для target'ов не имеет смысла)."""
    site = find_site(domain)
    server = config.find_server(config.load_servers(), site.server)
    if server is not None:
        return site, server
    target = config.find_target(config.load_targets(), site.server)
    if target is not None:
        raise InvalidArguments(
            f"{domain} задеплоен на target {site.server!r} (сторонний хостинг, "
            f"connection={target.connection}) — эта команда Webinoly-специфична, "
            f"для target'ов не поддерживается"
        )
    raise InvalidArguments(f"Сервер {site.server!r} для сайта {domain} не найден в конфиге")


def get_revisions(domain: str) -> dict:
    _site, server = require_site_server(domain)
    releases = webinoly.list_releases(server, domain)
    current = webinoly.current_release(server, domain)
    return {"domain": domain, "current": current, "releases": releases}


def rollback_target(target: config.Target) -> None:
    """Одношаговый откат для Target — нет полноценной истории с указателем
    "текущей" позиции, как у Webinoly-releases (там она на сервере, тут только
    локальные снепшоты) — просто заливаем самый свежий локальный бэкап обратно."""
    snapshots = _target_backup_snapshots(target.name)
    if not snapshots:
        raise StateError(f"У target {target.name!r} нет локальных бэкапов для отката")
    snapshot = snapshots[-1]
    if target.connection == "ssh":
        rsync_to_target(str(snapshot), target)
    else:
        ftp.mirror_to(str(snapshot), target)


def rollback(ctx: typer.Context, domain: str, confirm: bool) -> dict:
    site = find_site(domain)

    server = config.find_server(config.load_servers(), site.server)
    if server is not None:
        releases = webinoly.list_releases(server, domain)
        current = webinoly.current_release(server, domain)
        if current is None or current not in releases:
            raise StateError(f"Не удалось определить текущий релиз {domain}")
        idx = releases.index(current)
        if idx == 0:
            raise StateError(f"У {domain} нет более старого релиза для отката (текущий — самый старый: {current})")
        release = releases[idx - 1]

        if output.is_dry_run(ctx):
            return {
                "message": f"(dry-run) Откатил бы {domain} на релиз {release}, изменений не внесено",
                "domain": domain,
                "release": release,
                "dry_run": True,
            }

        output.require_confirmation(ctx, f"Rollback {domain} на релиз {release}", confirm)
        webinoly.switch_release(server, domain, release)
        return {"message": f"{domain} откачен на релиз {release}", "domain": domain, "release": release}

    site_target = config.find_target(config.load_targets(), site.server)
    if site_target is None:
        raise InvalidArguments(f"Сервер/target {site.server!r} для сайта {domain} не найден в конфиге")

    if output.is_dry_run(ctx):
        return {
            "message": f"(dry-run) Откатил бы {domain} на последний бэкап target {site_target.name}, изменений не внесено",
            "domain": domain,
            "target": site_target.name,
            "dry_run": True,
        }

    confirm_target_action(ctx, f"Rollback {domain}", site_target, confirm)
    rollback_target(site_target)
    return {"message": f"{domain} откачен на предыдущий бэкап", "domain": domain, "target": site_target.name}


def rollfore(domain: str) -> dict:
    _site, server = require_site_server(domain)
    releases = webinoly.list_releases(server, domain)
    current = webinoly.current_release(server, domain)
    if current is None or current not in releases:
        raise StateError(f"Не удалось определить текущий релиз {domain}")
    idx = releases.index(current)
    if idx >= len(releases) - 1:
        raise StateError(f"У {domain} нет более нового релиза (текущий — самый новый: {current})")
    release = releases[idx + 1]
    webinoly.switch_release(server, domain, release)
    return {"message": f"{domain} переключён на релиз {release}", "domain": domain, "release": release}


def set_maintenance(ctx: typer.Context, domain: str, confirm: bool) -> dict:
    """Очистить сайт, оставив встроенный плейсхолдер "в разработке". Реестр
    (local_path) не трогаем — редеплой реальной сборки продолжает работать
    как раньше. Старое содержимое не теряется: для сервера это обычный новый
    релиз, для target — обычный бэкап перед заливкой — откат в обоих случаях
    через `rollback`."""
    site = find_site(domain)

    server = config.find_server(config.load_servers(), site.server)
    if server is not None:
        if output.is_dry_run(ctx):
            return {
                "message": f"(dry-run) Перевёл бы {domain} в режим обслуживания, изменений не внесено",
                "domain": domain,
                "dry_run": True,
            }
        output.require_confirmation(ctx, f"Maintenance {domain}", confirm)
        webinoly.ensure_releases_layout(server, domain)
        ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        release = webinoly.release_path(domain, ts)
        rsync_to(str(MAINTENANCE_TEMPLATE_DIR), server, release)
        webinoly.fix_ownership_path(server, release)
        webinoly.switch_release(server, domain, ts)
        webinoly.prune_releases(server, domain)
        return {
            "message": f"{domain} переведён в режим обслуживания (релиз {ts})",
            "domain": domain,
            "release": ts,
        }

    target = config.find_target(config.load_targets(), site.server)
    if target is None:
        raise InvalidArguments(f"Сервер/target {site.server!r} для сайта {domain} не найден в конфиге")

    if output.is_dry_run(ctx):
        return {
            "message": f"(dry-run) Перевёл бы {domain} в режим обслуживания на target {target.name}, изменений не внесено",
            "domain": domain,
            "target": target.name,
            "dry_run": True,
        }

    confirm_target_action(ctx, f"Maintenance {domain}", target, confirm)
    _backup_target_before_deploy(ctx, target)
    if target.connection == "ssh":
        rsync_to_target(str(MAINTENANCE_TEMPLATE_DIR), target)
    else:
        ftp.mirror_to(str(MAINTENANCE_TEMPLATE_DIR), target)
    return {
        "message": f"{domain} переведён в режим обслуживания на {target.name}",
        "domain": domain,
        "target": target.name,
    }


def teardown(ctx: typer.Context, domain: str, confirm: bool) -> dict:
    site = find_site(domain)

    server = config.find_server(config.load_servers(), site.server)
    target = None if server is not None else config.find_target(config.load_targets(), site.server)

    if output.is_dry_run(ctx):
        return {"message": f"(dry-run) Снёс бы сайт {domain}, изменений не внесено", "domain": domain, "dry_run": True}

    if target is not None:
        confirm_target_action(ctx, f"Teardown {domain}", target, confirm)
    else:
        output.require_confirmation(ctx, f"Снести сайт {domain} и убрать из реестра", confirm)

    if server is not None:
        webinoly.delete_site(server, domain)
    else:
        if target is None:
            raise InvalidArguments(f"Сервер/target {site.server!r} для сайта {domain} не найден в конфиге")
        teardown_target(target)

    sites = config.load_sites()
    sites.remove(next(s for s in sites if s.domain == domain))
    config.save_sites(sites)
    return {"message": f"Сайт {domain} удалён", "domain": domain}


def set_http_auth(domain: str, user: str | None, password: str | None, off: bool) -> dict:
    _, server = require_site_server(domain)  # упадёт понятной ошибкой для target'ов
    sites = config.load_sites()
    site = next(s for s in sites if s.domain == domain)

    if off:
        webinoly.disable_http_auth(server, domain)
        site.password_protect = None
        config.save_sites(sites)
        return {"message": f"Пароль снят с {domain}", "domain": domain}

    if not user or not password:
        raise InvalidArguments("Укажи --user и --pass, либо --off чтобы снять защиту")

    webinoly.set_http_auth(server, domain, user, password)
    # Пароль на сервер уже ушёл в открытом виде (ADR 0005 — решено: `--pass` в
    # аргументе командной строки ок для MVP, single user/локальная машина) —
    # локально в реестре его не храним, только факт защиты и логин.
    site.password_protect = {"enabled": True, "user": user}
    config.save_sites(sites)
    return {"message": f"Сайт {domain} защищён паролем (юзер {user})", "domain": domain}


def update_site_config(
    domain: str,
    cors: list[str],
    no_cors: bool,
    redirect: list[str],
    remove_redirect: list[str],
    force_https: bool,
    no_force_https: bool,
    nginx_snippet: str | None,
    no_nginx_snippet: bool,
) -> dict:
    """message=None в результате значит "изменений не запрошено" — вызывающий
    код должен напечатать текущий конфиг (result["site"]) вместо success."""
    if no_force_https:
        raise InvalidArguments(
            "Webinoly всегда включает редирект HTTP→HTTPS вместе с -ssl=on и не даёт его "
            "отключить (см. docs/usage/webinoly.md) — --no-force-https не поддерживается"
        )

    sites = config.load_sites()
    site = next((s for s in sites if s.domain == domain), None)
    if site is None:
        raise InvalidArguments(f"Сайт {domain} не найден в реестре")

    if force_https and not (cors or no_cors or redirect or remove_redirect):
        return {
            "message": (
                f"Force-https для {domain} уже всегда включён вместе с SSL (Webinoly, docs/usage/webinoly.md) — "
                f"ничего делать не нужно"
            ),
            "domain": domain,
            "site": site,
        }

    if nginx_snippet and no_nginx_snippet:
        raise InvalidArguments("--nginx-snippet и --no-nginx-snippet вместе не имеют смысла")

    snippet_content: str | None = None
    if nginx_snippet:
        snippet_path = Path(nginx_snippet).expanduser()
        if not snippet_path.is_file():
            raise InvalidArguments(f"{snippet_path} не найден")
        snippet_content = snippet_path.read_text()

    has_changes = (
        bool(cors) or no_cors or bool(redirect) or bool(remove_redirect) or bool(nginx_snippet) or no_nginx_snippet
    )
    if not has_changes:
        return {"message": None, "domain": domain, "site": site}

    _site, server = require_site_server(domain)

    for pair in redirect:
        frm, sep, to = pair.partition("=")
        if not sep:
            raise InvalidArguments(f"--redirect ожидает вид FROM=TO, получено {pair!r}")
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
    return {"message": f"Настройки {domain} обновлены", "domain": domain, "site": site}


def get_debug_info(domain: str, error: bool, lines: int) -> dict:
    _site, server = require_site_server(domain)
    status = http.head_status(domain)
    log_output = webinoly.tail_log(server, domain, error=error, lines=lines)
    return {"domain": domain, "http_status": status, "log": log_output}


# --- doctor -----------------------------------------------------------------


def _check(name: str, status: str, detail: str) -> dict:
    # `ok` — по Standard, Health; `warn` — не провал (healthy остаётся true).
    return {"name": name, "ok": status != "fail", "status": status, "detail": detail}


def run_doctor() -> dict:
    """Проверки окружения/конфига без обращения к удалённым серверам (быстро,
    безопасно вызывать часто) — права на ~/.config/hostme/, читаемость
    реестров, наличие бинарей, нужных выбранным serverʼам/targetʼам."""
    checks: list[dict] = []

    if config.CONFIG_DIR.exists():
        mode = config.CONFIG_DIR.stat().st_mode & 0o777
        checks.append(
            _check(
                "config_dir",
                "ok" if mode == 0o700 else "warn",
                f"{config.CONFIG_DIR} (права {oct(mode)})" if mode != 0o700 else str(config.CONFIG_DIR),
            )
        )
    else:
        checks.append(
            _check("config_dir", "warn", f"{config.CONFIG_DIR} ещё не создан (будет создан при первой команде)")
        )

    try:
        servers = config.load_servers()
        checks.append(_check("servers_yaml", "ok", f"{len(servers)} серверов"))
    except Exception as exc:  # noqa: BLE001
        servers = []
        checks.append(_check("servers_yaml", "fail", str(exc)))

    try:
        targets = config.load_targets()
        checks.append(_check("targets_yaml", "ok", f"{len(targets)} target'ов"))
    except Exception as exc:  # noqa: BLE001
        targets = []
        checks.append(_check("targets_yaml", "fail", str(exc)))

    try:
        sites = config.load_sites()
        checks.append(_check("sites_yaml", "ok", f"{len(sites)} сайтов ({config.SITES_FILE})"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("sites_yaml", "fail", str(exc)))

    backups_check, backups_info = _target_backups_report()
    checks.append(backups_check)

    # Имена литералами — release.py сверяет их с [[tool.rb.external]] (стандарт §12).
    for binary, path in (("ssh", shutil.which("ssh")), ("rsync", shutil.which("rsync"))):
        checks.append(_check(binary, "ok" if path else "fail", path or f"`{binary}` не найден в PATH"))

    needs_lftp = any(t.connection in ("ftp", "sftp") for t in targets)
    if needs_lftp:
        path = shutil.which("lftp")
        checks.append(
            _check("lftp", "ok" if path else "fail", path or "`lftp` не найден в PATH (нужен для ftp/sftp target'ов)")
        )

    needs_sshpass = any(t.connection == "ssh" and t.password and not t.ssh_key for t in targets)
    if needs_sshpass:
        path = shutil.which("sshpass")
        checks.append(
            _check(
                "sshpass",
                "ok" if path else "fail",
                path or "`sshpass` не найден в PATH (нужен для password-based SSH target'ов)",
            )
        )

    for server in servers:
        key_path = Path(server.ssh_key).expanduser()
        checks.append(
            _check(
                f"ssh_key:{server.name}",
                "ok" if key_path.exists() else "warn",
                str(key_path) if key_path.exists() else f"{key_path} не найден локально",
            )
        )
    for target in targets:
        if target.ssh_key:
            key_path = Path(target.ssh_key).expanduser()
            checks.append(
                _check(
                    f"ssh_key:{target.name}",
                    "ok" if key_path.exists() else "warn",
                    str(key_path) if key_path.exists() else f"{key_path} не найден локально",
                )
            )

    ok = not any(c["status"] == "fail" for c in checks)
    return {"healthy": ok, "checks": checks, "data_dir": str(config.DATA_DIR), "target_backups": backups_info}


def _target_backups_report() -> tuple[dict, dict]:
    """(check для doctor, сводка для JSON: путь, байты, снепшоты, политика)."""
    backups_dir = config.TARGET_BACKUPS_DIR
    snapshots = (
        sum(len(_target_backup_snapshots(t.name)) for t in backups_dir.iterdir() if t.is_dir())
        if backups_dir.is_dir()
        else 0
    )
    size = _dir_size(backups_dir) if backups_dir.is_dir() else 0
    info: dict = {"path": str(backups_dir), "bytes": size, "snapshots": snapshots}
    try:
        policy = config.load_backup_policy()
    except InvalidArguments as exc:
        return _check("target_backups", "fail", str(exc)), info
    info["policy"] = {"keep": policy.keep, "max_age_days": policy.max_age_days}
    policy_text = f"храним последние {policy.keep}" + (
        f", не старше {policy.max_age_days} дн." if policy.max_age_days else ""
    )
    detail = f"{backups_dir} — {_human_size(size)}, снепшотов: {snapshots}; {policy_text}"
    return _check("target_backups", "ok", detail), info
