from __future__ import annotations

import base64
import re
import shlex
from dataclasses import dataclass
from typing import Literal

from hostme.config import Server
from hostme.errors import HostmeError
from hostme.ssh import RemoteResult, run_remote

SiteType = Literal["html", "php"]

INSTALL_URL = "qrok.es/wy"
# Реальный формат `sudo site -list` (подтверждено на sites-first-beget,
# 2026-09-09): несколько отдельных скобочных групп подряд без разделителя,
# напр. " + e2edebug2.antagorapp.ru (HTML)(NoSSL) " — не "(HTML, NoSSL)".
_LIST_LINE_RE = re.compile(r"^\s*\+\s+(\S+)\s+((?:\([^)]*\))+)\s*$", re.MULTILINE)
_TAG_RE = re.compile(r"\(([^)]*)\)")


class WebinolyError(HostmeError):
    def __init__(self, message: str, result: RemoteResult | None = None) -> None:
        super().__init__(message)
        self.result = result


@dataclass
class SiteInfo:
    domain: str
    tags: list[str]

    @property
    def is_php(self) -> bool:
        return "PHP" in self.tags

    @property
    def has_ssl(self) -> bool:
        return "NoSSL" not in self.tags


def is_installed(server: Server) -> bool:
    result = run_remote(server, "command -v webinoly")
    return result.ok


def install(server: Server, mode: str = "-php") -> RemoteResult:
    """Ставит Webinoly (см. docs/webinoly.md: -php ставится полностью неинтерактивно).

    Идемпотентно: если Webinoly уже стоит, ничего не переустанавливает.
    """
    if is_installed(server):
        return run_remote(server, "webinoly -version")

    command = f"cd /root && wget -qO weby {INSTALL_URL} && bash weby {mode}"
    result = run_remote(server, command, timeout=300)
    if not result.ok:
        raise WebinolyError(f"Установка Webinoly на {server.name} провалилась: {result.stderr}", result)
    return result


def parse_site_list(output: str) -> list[SiteInfo]:
    sites = []
    for match in _LIST_LINE_RE.finditer(output):
        domain, groups_raw = match.groups()
        tags = [
            tag.strip()
            for group in _TAG_RE.findall(groups_raw)
            for tag in group.split(",")
            if tag.strip()
        ]
        sites.append(SiteInfo(domain=domain, tags=tags))
    return sites


def list_sites(server: Server) -> list[SiteInfo]:
    result = run_remote(server, "sudo site -list")
    return parse_site_list(result.stdout)


def site_exists(server: Server, domain: str) -> bool:
    return any(s.domain == domain for s in list_sites(server))


_PLACEHOLDER_HTML = (
    "<!doctype html>\n"
    '<html lang="ru"><head><meta charset="utf-8"><title>Сайт в разработке</title></head>\n'
    '<body style="font-family: sans-serif; text-align: center; margin-top: 15%;">\n'
    "<h1>Сайт в разработке</h1>\n"
    "</body></html>\n"
)


def create_site(server: Server, domain: str, site_type: SiteType) -> RemoteResult:
    flag = "-html" if site_type == "html" else "-php"
    result = run_remote(server, f"sudo site {domain} {flag}")
    if not result.ok:
        raise WebinolyError(f"Не удалось создать сайт {domain} на {server.name}: {result.stderr}", result)
    # Заглушка вместо голого 403 в промежутке между созданием сайта и заливкой
    # реального контента (nginx у Webinoly не отдаёт autoindex, try_files на
    # пустой htdocs даёт 403, не 404). Best-effort — не мешает deploy, если вдруг
    # не получилось: реальный контент всё равно перезапишет/переживёт это через rsync.
    write_placeholder_index(server, domain, site_type)
    return result


def write_placeholder_index(server: Server, domain: str, site_type: SiteType) -> RemoteResult:
    index_name = "index.php" if site_type == "php" else "index.html"
    path = f"{webroot(domain)}/{index_name}"
    encoded = base64.b64encode(_PLACEHOLDER_HTML.encode()).decode()
    result = run_remote(server, f"echo {encoded} | base64 -d > {shlex.quote(path)}")
    if result.ok:
        fix_ownership(server, domain)
    return result


def enable_ssl(
    server: Server,
    domain: str,
    *,
    wildcard: bool = False,
    add_to_wildcard: str | None = None,
) -> RemoteResult:
    if add_to_wildcard:
        command = f"sudo site {domain} -ssl=on -add-to-wildcard={add_to_wildcard}"
    elif wildcard:
        command = f"sudo site {domain} -ssl=on -wildcard"
    else:
        command = f"sudo site {domain} -ssl=on"
    result = run_remote(server, command, timeout=120)
    if not result.ok:
        raise WebinolyError(f"Не удалось включить SSL для {domain} на {server.name}: {result.stderr}", result)
    return result


def delete_site(server: Server, domain: str, revoke_ssl: bool = True) -> RemoteResult:
    revoke = "-revoke=on" if revoke_ssl else "-revoke=off"
    result = run_remote(server, f"sudo site {domain} -delete=force {revoke}")
    if not result.ok:
        raise WebinolyError(f"Не удалось удалить сайт {domain} на {server.name}: {result.stderr}", result)
    return result


def webroot(domain: str) -> str:
    return f"/var/www/{domain}/htdocs"


def fix_ownership(server: Server, domain: str) -> RemoteResult:
    """Обязательный шаг после заливки файлов (см. docs/webinoly.md): без него nginx отдаёт 403."""
    return fix_ownership_path(server, webroot(domain))


def fix_ownership_path(server: Server, path: str) -> RemoteResult:
    result = run_remote(server, f"sudo chown -R www-data:www-data {shlex.quote(path)}")
    if not result.ok:
        raise WebinolyError(f"Не удалось поправить владельца {path}: {result.stderr}", result)
    return result


# --- releases/rollback (TODO 3.2) -------------------------------------------
#
# Webinoly жёстко ожидает root в /var/www/<domain>/htdocs (это генерируемый им же
# nginx-конфиг, руками не трогаем) — поэтому вместо настоящей директории htdocs
# становится симлинком на releases/<таймстамп>, а сама заливка каждый раз идёт в
# новую директорию. Старый релиз не удаляется сразу — это и есть "бэкап перед
# пушем" и основа для rollback: откат — это просто перекладка симлинка, без
# повторной заливки файлов.

_KEEP_RELEASES = 5


def releases_dir(domain: str) -> str:
    return f"/var/www/{domain}/releases"


def release_path(domain: str, ts: str) -> str:
    return f"{releases_dir(domain)}/{ts}"


def ensure_releases_layout(server: Server, domain: str) -> RemoteResult:
    """Идемпотентно переводит сайт на releases-схему. Если htdocs уже симлинк —
    no-op. Если это обычная директория с контентом (свежесозданный Webinoly-сайт,
    либо сайт, задеплоенный до появления этой схемы) — переносит её содержимое в
    releases/<ts>-migrated как первый релиз, ничего не теряя."""
    root = f"/var/www/{domain}"
    script = (
        # releases/ создаётся под root (SSH-сессия root) -> www-data не может даже
        # зайти внутрь без chown (nginx работает от www-data, 404 на весь сайт
        # несмотря на верные права у файлов глубже) — поймано вживую 2026-09-09.
        f"cd {shlex.quote(root)} && mkdir -p releases && sudo chown www-data:www-data releases && "
        "if [ -L htdocs ]; then exit 0; fi; "
        "if [ -d htdocs ]; then "
        "ts=$(date +%Y%m%d%H%M%S)-migrated && "
        "mv htdocs releases/$ts && ln -s releases/$ts htdocs; "
        "fi"
    )
    result = run_remote(server, script)
    if not result.ok:
        raise WebinolyError(f"Не удалось перевести {domain} на releases-схему: {result.stderr}", result)
    return result


def switch_release(server: Server, domain: str, ts: str) -> RemoteResult:
    """Атомарная перекладка симлинка htdocs -> releases/<ts> (общая для deploy,
    rollback и rollfore — везде это одна и та же безопасная операция)."""
    root = f"/var/www/{domain}"
    rel = f"releases/{ts}"
    script = (
        f"cd {shlex.quote(root)} && "
        f"[ -d {shlex.quote(rel)} ] || {{ echo 'release {ts} not found' >&2; exit 1; }}; "
        f"ln -sfn {shlex.quote(rel)} htdocs_tmp && mv -Tf htdocs_tmp htdocs"
    )
    result = run_remote(server, script)
    if not result.ok:
        raise WebinolyError(f"Не удалось переключить {domain} на релиз {ts}: {result.stderr}", result)
    # nginx.conf у Webinoly включает open_file_cache (valid=30s) — без reload сайт
    # отдаёт старый контент по кэшированному файловому дескриптору ещё до ~30с
    # после смены симлинка (поймано вживую 2026-09-09, tests/e2e-стиль прогон).
    return _reload_nginx(server, domain, action="переключение релиза")


def list_releases(server: Server, domain: str) -> list[str]:
    result = run_remote(server, f"ls -1 {shlex.quote(releases_dir(domain))} 2>/dev/null | sort")
    return [line for line in result.stdout.splitlines() if line.strip()]


def current_release(server: Server, domain: str) -> str | None:
    result = run_remote(server, f"readlink {shlex.quote(webroot(domain))}")
    target = result.stdout.strip()
    if not result.ok or not target:
        return None
    return target.rsplit("/", 1)[-1]


def prune_releases(server: Server, domain: str, keep: int = _KEEP_RELEASES) -> RemoteResult | None:
    releases = list_releases(server, domain)
    if len(releases) <= keep:
        return None
    current = current_release(server, domain)
    # никогда не удаляем текущий релиз, даже если он старше последних `keep`
    to_remove = [r for r in releases[:-keep] if r != current]
    if not to_remove:
        return None
    paths = " ".join(shlex.quote(release_path(domain, r)) for r in to_remove)
    result = run_remote(server, f"rm -rf {paths}")
    if not result.ok:
        raise WebinolyError(f"Не удалось почистить старые релизы {domain}: {result.stderr}", result)
    return result


def enable_sftp(server: Server) -> RemoteResult:
    return run_remote(server, "sudo webinoly -sftp=on")


def set_http_auth(server: Server, domain: str, username: str, password: str) -> RemoteResult:
    """`hostme <domain> auth --user U --pass P` (раздел 5 PRD). Логин/пароль уходят
    в команду через shlex.quote — они приходят от пользователя (CLI-аргумент), и
    без экранирования это была бы command injection в свою же root-сессию по SSH."""
    creds = shlex.quote(f"[{username},{password}]")
    add_result = run_remote(server, f"sudo httpauth {domain} -add={creds}")
    if not add_result.ok:
        raise WebinolyError(
            f"Не удалось создать httpauth-юзера для {domain}: {add_result.stderr}", add_result
        )
    path_result = run_remote(server, f"sudo httpauth {domain} -path=/")
    if not path_result.ok:
        raise WebinolyError(
            f"Не удалось включить защиту паролем для {domain}: {path_result.stderr}", path_result
        )
    return path_result


def disable_http_auth(server: Server, domain: str) -> RemoteResult:
    result = run_remote(server, f"sudo httpauth {domain} -path=all -purge")
    if not result.ok:
        raise WebinolyError(f"Не удалось снять пароль с {domain}: {result.stderr}", result)
    return result


def add_redirect(server: Server, domain: str, from_path: str, to: str, http_code: int = 302) -> RemoteResult:
    command = (
        f"sudo site {domain} -redirection -from={shlex.quote(from_path)} "
        f"-to={shlex.quote(to)} -http-code={http_code}"
    )
    result = run_remote(server, command)
    if not result.ok:
        raise WebinolyError(
            f"Не удалось добавить redirect {from_path} -> {to} для {domain}: {result.stderr}", result
        )
    return result


def remove_redirect(server: Server, domain: str, from_path: str) -> RemoteResult:
    result = run_remote(server, f"sudo site {domain} -redirection -delete -from={shlex.quote(from_path)}")
    if not result.ok:
        raise WebinolyError(f"Не удалось удалить redirect {from_path} для {domain}: {result.stderr}", result)
    return result


_CORS_SNIPPET_NAME = "hostme-cors-nginx.conf"


def _cors_snippet_path(domain: str) -> str:
    return f"/var/www/{domain}/{_CORS_SNIPPET_NAME}"


def _render_cors_snippet(origins: list[str]) -> str:
    """У Webinoly нет per-site CORS-флага (docs/webinoly.md, «Кастомный Nginx-конфиг»).
    Сниппет живёт на уровне server{} (НЕ location /) — location / уже объявлен самим
    Webinoly в основном конфиге сайта, второй location / в этом же server-блоке —
    ошибка nginx. На server-уровне add_header корректно наследуется в location /,
    т.к. там своих add_header нет. Для статики (css/js/шрифты/картинки) у Webinoly
    уже есть свой location с `Access-Control-Allow-Origin: *` — наш сниппет туда не
    попадает (та location сама объявляет заголовки, поэтому не наследует server-уровень),
    так что CORS для статики остаётся как есть у Webinoly, а наш список origin'ов
    касается всего остального (HTML/PHP-ответов через location /).
    """
    pattern = "|".join(re.escape(o) for o in origins)
    return (
        "# Managed by hostme (`hostme <domain> config --cors`).\n"
        "# Перегенерируется целиком при каждом изменении списка origin'ов — не редактировать руками.\n"
        'set $hostme_cors_origin "";\n'
        f'if ($http_origin ~* "^({pattern})$") {{\n'
        "    set $hostme_cors_origin $http_origin;\n"
        "}\n"
        "add_header 'Access-Control-Allow-Origin' $hostme_cors_origin always;\n"
        "add_header 'Vary' 'Origin' always;\n"
    )


def set_cors(server: Server, domain: str, origins: list[str]) -> RemoteResult:
    path = _cors_snippet_path(domain)
    quoted_path = shlex.quote(path)

    if not origins:
        result = run_remote(server, f"rm -f {quoted_path}")
        if not result.ok:
            raise WebinolyError(f"Не удалось убрать CORS-сниппет для {domain}: {result.stderr}", result)
        return _reload_nginx(server, domain, action="удаление CORS")

    content = _render_cors_snippet(origins)
    encoded = base64.b64encode(content.encode()).decode()
    write_result = run_remote(server, f"echo {encoded} | base64 -d > {quoted_path}")
    if not write_result.ok:
        raise WebinolyError(f"Не удалось залить CORS-сниппет для {domain}: {write_result.stderr}", write_result)

    return _reload_nginx(server, domain, action="включение CORS", rollback=lambda: run_remote(server, f"rm -f {quoted_path}"))


def tail_log(server: Server, domain: str, *, error: bool = False, lines: int = 10, seconds: int = 3) -> str:
    """`sudo log <domain>` у Webinoly по умолчанию стримит в реальном времени
    (`tail -f`, никогда сам не завершается) — без ограничения по времени наш
    run_remote() (ждёт завершения процесса) провисел бы до таймаута. Оборачиваем
    в `timeout <seconds>` на самом сервере, чтобы гарантированно вернуться —
    `; true` гасит код возврата 124 (SIGTERM от timeout), это ожидаемо, не ошибка.
    """
    flag = "-error" if error else ""
    command = f"sudo timeout {seconds} log {domain} {flag} -lines={lines}; true"
    result = run_remote(server, command, timeout=seconds + 15)
    return result.stdout


def _reload_nginx(server: Server, domain: str, *, action: str, rollback=None) -> RemoteResult:
    # `nginx -t` валидирует ВЕСЬ конфиг сервера (все сайты), не только этот файл —
    # если наш сниппет что-то сломал, откатываем его и не трогаем работающий nginx.
    test_result = run_remote(server, "sudo nginx -t")
    if not test_result.ok:
        if rollback is not None:
            rollback()
        raise WebinolyError(
            f"nginx -t провалился после {action} для {domain} (изменение откачено, "
            f"nginx не перезагружался): {test_result.stderr}",
            test_result,
        )
    reload_result = run_remote(server, "sudo systemctl reload nginx")
    if not reload_result.ok:
        raise WebinolyError(f"Не удалось перезагрузить nginx после {action} для {domain}: {reload_result.stderr}", reload_result)
    return reload_result
