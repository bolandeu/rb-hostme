from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ruamel.yaml import YAML

from hostme.core.errors import InvalidArgumentsError
from hostme.credentials import manager as credentials

CONFIG_DIR = Path.home() / ".config" / "hostme"
SERVERS_FILE = CONFIG_DIR / "servers.yaml"
SITES_FILE = CONFIG_DIR / "sites.yaml"
# Локальные снепшоты "состояние на сервере перед деплоем" для Target-сайтов
# (сторонний хостинг, без Webinoly-releases) — см. cli._backup_target_before_deploy.
# Вне git-репозитория проекта по тому же принципу, что servers.yaml/sites.yaml
# (PRD §8) — это runtime-состояние конкретной машины, не исходный код hostme.
TARGET_BACKUPS_DIR = CONFIG_DIR / "target-backups"

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)


@dataclass
class BaseDomain:
    name: str
    default: bool = False


@dataclass
class Server:
    name: str
    host: str
    user: str
    ssh_key: str
    default: bool = False
    base_domains: list[BaseDomain] = field(default_factory=list)

    @property
    def ssh_target(self) -> str:
        return f"{self.user}@{self.host}"


TargetConnection = Literal["ssh", "ftp", "sftp"]


@dataclass
class Target:
    """Сторонний хостинг (не наш VPS, без Webinoly) — просто "куда залить файлы".
    В отличие от Server: нет ssh_key-only допущения (часто только логин/пароль
    от хостинг-панели, одинаковый для любого протокола), нет base_domains/SSL/
    releases — хостер уже сам всё настроил, hostme тут просто транспорт.
    connection определяет ТОЛЬКО механизм заливки (rsync по ssh vs lftp), не
    подразумевает никакого управления сервером."""

    name: str
    connection: TargetConnection
    host: str
    user: str
    remote_path: str = "/"
    password: str | None = None
    ssh_key: str | None = None


@dataclass
class Site:
    domain: str
    server: str
    local_path: str
    php: bool = False
    ssl: bool = True
    force_https: bool = True
    cors: list[str] = field(default_factory=list)
    redirects: list[dict] = field(default_factory=list)
    password_protect: dict | None = None
    deployed_at: str | None = None
    # Относительный путь include-файла (sites.d/*.yaml), откуда сайт был прочитан
    # load_sites(); None значит "живёт в главном sites.yaml". Используется только
    # save_sites(), чтобы писать обновление обратно в тот же файл, а не всегда в
    # главный (раздел 2.5 TODO). Не сериализуется в сам YAML.
    source_file: str | None = field(default=None, compare=False, repr=False)


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def load_servers() -> list[Server]:
    if not SERVERS_FILE.exists():
        return []
    data = _yaml.load(SERVERS_FILE.read_text()) or {}
    servers = []
    for raw in data.get("servers", []):
        domains = [BaseDomain(name=d["name"], default=d.get("default", False)) for d in raw.get("base_domains", [])]
        servers.append(
            Server(
                name=raw["name"],
                host=raw["host"],
                user=raw["user"],
                ssh_key=raw["ssh_key"],
                default=raw.get("default", False),
                base_domains=domains,
            )
        )
    return servers


def save_servers(servers: list[Server]) -> None:
    # targets: живёт в том же файле (см. save_targets) — сохраняем, чтобы не
    # затереть при обновлении одних только servers.
    _ensure_config_dir()
    data = {}
    if SERVERS_FILE.exists():
        existing = _yaml.load(SERVERS_FILE.read_text()) or {}
        if "targets" in existing:
            data["targets"] = existing["targets"]
    data["servers"] = [
        {
            "name": s.name,
            "host": s.host,
            "user": s.user,
            "ssh_key": s.ssh_key,
            "default": s.default,
            "base_domains": [{"name": d.name, **({"default": True} if d.default else {})} for d in s.base_domains],
        }
        for s in servers
    ]
    with SERVERS_FILE.open("w") as f:
        _yaml.dump(data, f)
    SERVERS_FILE.chmod(0o600)


def load_targets() -> list[Target]:
    if not SERVERS_FILE.exists():
        return []
    data = _yaml.load(SERVERS_FILE.read_text()) or {}
    targets = []
    has_legacy_password = False
    for raw in data.get("targets", []):
        name = raw["name"]
        legacy_password = raw.get("password")
        if legacy_password:
            # Миграция со старой версии, где password лежал открытым текстом в
            # servers.yaml — save_targets() ниже перенесёт его в OS keychain и
            # перепишет файл уже без поля password.
            has_legacy_password = True
            password = legacy_password
        else:
            password = credentials.get_secret(name)
        targets.append(
            Target(
                name=name,
                connection=raw["connection"],
                host=raw["host"],
                user=raw["user"],
                remote_path=raw.get("remote_path", "/"),
                password=password,
                ssh_key=raw.get("ssh_key"),
            )
        )
    if has_legacy_password:
        save_targets(targets)
    return targets


def save_targets(targets: list[Target]) -> None:
    # servers: живёт в том же файле (см. save_servers) — та же логика "не затереть".
    # password НЕ пишем в servers.yaml — секрет уходит только в OS keychain
    # (credentials/manager.py), сюда — только не-секретные поля подключения.
    # Секрет — до записи yaml: без keychain (headless) store_secret падает с
    # подсказкой про HOSTME_<TARGET>_PASSWORD, и реестр не получает target без пароля.
    # Пароль, который уже и так отдаёт env/keychain, не переписываем — иначе
    # пароль из env (сервер под doppler) каждый раз копировался бы в keychain.
    for t in targets:
        if t.password and credentials.get_secret(t.name) != t.password:
            credentials.store_secret(t.name, t.password)
    _ensure_config_dir()
    data = {}
    if SERVERS_FILE.exists():
        existing = _yaml.load(SERVERS_FILE.read_text()) or {}
        if "servers" in existing:
            data["servers"] = existing["servers"]
    data["targets"] = [
        {
            "name": t.name,
            "connection": t.connection,
            "host": t.host,
            "user": t.user,
            "remote_path": t.remote_path,
            "ssh_key": t.ssh_key,
        }
        for t in targets
    ]
    with SERVERS_FILE.open("w") as f:
        _yaml.dump(data, f)
    SERVERS_FILE.chmod(0o600)


def find_target(targets: list[Target], name: str) -> Target | None:
    return next((t for t in targets if t.name == name), None)


def load_sites() -> list[Site]:
    if not SITES_FILE.exists():
        return []
    data = _yaml.load(SITES_FILE.read_text()) or {}
    sites = [_site_from_raw(raw, source_file=None) for raw in data.get("sites", [])]
    for included in data.get("include", []):
        included_path = SITES_FILE.parent / included
        if not included_path.exists():
            continue
        included_data = _yaml.load(included_path.read_text()) or {}
        sites.extend(_site_from_raw(raw, source_file=included) for raw in included_data.get("sites", []))
    return sites


def _site_from_raw(raw: dict, source_file: str | None) -> Site:
    return Site(
        domain=raw["domain"],
        server=raw["server"],
        local_path=raw["local_path"],
        php=raw.get("php", False),
        ssl=raw.get("ssl", True),
        force_https=raw.get("force_https", True),
        cors=raw.get("cors", []),
        redirects=raw.get("redirects", []),
        password_protect=raw.get("password_protect"),
        deployed_at=raw.get("deployed_at"),
        source_file=source_file,
    )


def _site_to_raw(s: Site) -> dict:
    return {
        "domain": s.domain,
        "server": s.server,
        "local_path": s.local_path,
        "php": s.php,
        "ssl": s.ssl,
        "force_https": s.force_https,
        "cors": s.cors,
        "redirects": s.redirects,
        "password_protect": s.password_protect,
        "deployed_at": s.deployed_at,
    }


def save_sites(sites: list[Site]) -> None:
    """Каждый сайт пишется обратно в тот файл, откуда его прочитал load_sites()
    (главный sites.yaml или include-файл из sites.d/) — иначе сайт, once заведённый
    в отдельный include-файл вручную, при первом же обновлении из hostme переехал
    бы в главный sites.yaml (раздел 2.5 TODO)."""
    _ensure_config_dir()
    by_file: dict[str, list[Site]] = {}
    main_sites: list[Site] = []
    for s in sites:
        if s.source_file:
            by_file.setdefault(s.source_file, []).append(s)
        else:
            main_sites.append(s)

    data = {}
    if SITES_FILE.exists():
        existing = _yaml.load(SITES_FILE.read_text()) or {}
        if "include" in existing:
            data["include"] = existing["include"]
    data["sites"] = [_site_to_raw(s) for s in main_sites]
    with SITES_FILE.open("w") as f:
        _yaml.dump(data, f)
    SITES_FILE.chmod(0o600)

    for rel_path, file_sites in by_file.items():
        path = SITES_FILE.parent / rel_path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("w") as f:
            _yaml.dump({"sites": [_site_to_raw(s) for s in file_sites]}, f)
        path.chmod(0o600)


def find_server(servers: list[Server], name: str) -> Server | None:
    return next((s for s in servers if s.name == name), None)


def default_server(servers: list[Server]) -> Server | None:
    return next((s for s in servers if s.default), servers[0] if servers else None)


def default_base_domain(servers: list[Server]) -> tuple[Server, BaseDomain] | None:
    """Первый когда-либо зарегистрированный служебный домен (PRD, раздел 4)."""
    for s in servers:
        for d in s.base_domains:
            if d.default:
                return s, d
    return None


def resolve_server_for_domain(servers: list[Server], domain: str) -> Server | None:
    for s in servers:
        for d in s.base_domains:
            if domain == d.name or domain.endswith(f".{d.name}"):
                return s
    return None


def resolve_server(
    servers: list[Server],
    sites: list[Site],
    domain: str,
    explicit_server: str | None = None,
) -> Server | None:
    """Порядок (PRD, раздел 4): --server > уже известный домен в sites.yaml > base_domains серверов."""
    if explicit_server:
        return find_server(servers, explicit_server)

    existing_site = next((s for s in sites if s.domain == domain), None)
    if existing_site is not None:
        server = find_server(servers, existing_site.server)
        if server is not None:
            return server

    return resolve_server_for_domain(servers, domain)


def normalize_domain(domain: str) -> str:
    """Домен, введённый пользователем напрямую как аргумент CLI (не через slugify
    имени папки), может быть кириллическим целиком — `растаможка-авто.рф`. DNS и
    Let's Encrypt понимают только ASCII, поэтому приводим к punycode целиком через
    встроенный кодек `str.encode("idna")` (в отличие от `slugify()` он сам бьёт
    домен по точкам и ToASCII-кодирует каждый лейбл отдельно, включая TLD — `.рф`
    → `.xn--p1ai`). ASCII-домены проходят как есть.
    """
    if domain.isascii():
        return domain
    try:
        return domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidArgumentsError(f"Не удалось привести домен {domain!r} к ASCII/punycode: {exc}") from exc


def slugify(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-") or "site"
    if slug.isascii():
        return slug
    # Не-ASCII буквы (например, кириллица в имени папки) — DNS-лейбл допускает
    # только ASCII, поэтому кодируем в punycode (тот же алгоритм, что у браузеров/DNS):
    # "под-проект" → "xn----...". Раскодируется обратно любым IDNA-совместимым резолвером.
    try:
        return f"xn--{slug.encode('punycode').decode('ascii')}"
    except UnicodeError:
        return "site"


def default_domain(local_path: str, servers: list[Server]) -> str | None:
    """<slug(имя-папки)>.<первый зарегистрированный служебный домен> (PRD, раздел 2)."""
    result = default_base_domain(servers)
    if result is None:
        return None
    _, base_domain = result
    folder_name = Path(local_path).resolve().name
    return f"{slugify(folder_name)}.{base_domain.name}"


def check_collision(sites: list[Site], domain: str, local_path: str) -> None:
    existing = next((s for s in sites if s.domain == domain), None)
    if existing is None:
        return
    existing_path = str(Path(existing.local_path).resolve())
    new_path = str(Path(local_path).resolve())
    if existing_path != new_path:
        raise InvalidArgumentsError(
            f"Домен {domain} уже используется другим сайтом "
            f"(local_path={existing.local_path}). "
            f"Укажи другой домен или удали существующий сайт (teardown)."
        )
