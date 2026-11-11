"""Провайдер Webinoly: единственное место, где hostme строит команды `site`, `httpauth`,
`webinoly` и разбирает их вывод на сервере.

Формы команд, форматы вывода и раскладка сайта — docs/usage/webinoly.md; найденные
на живых серверах отклонения от документации — docs/research/2026-09-08-webinoly-behaviour.md.
Наружу ошибки уходят только как WebinolyError.
"""

from __future__ import annotations

import base64
import re
import shlex
from dataclasses import dataclass
from typing import Literal

from hostme.config import Server
from hostme.core.errors import ProviderError
from hostme.data import load_nginx_defaults
from hostme.providers.ssh import RemoteResult, run_remote

SiteType = Literal["html", "php"]

INSTALL_URL = "qrok.es/wy"
# Реальный формат `sudo site -list` (подтверждено на sites-first-beget,
# 2026-09-09): несколько отдельных скобочных групп подряд без разделителя,
# напр. " + e2edebug2.antagorapp.ru (HTML)(NoSSL) " — не "(HTML, NoSSL)".
_LIST_LINE_RE = re.compile(r"^\s*\+\s+(\S+)\s+((?:\([^)]*\))+)\s*$", re.MULTILINE)
_TAG_RE = re.compile(r"\(([^)]*)\)")


class WebinolyError(ProviderError):
    provider = "webinoly"

    def __init__(self, message: str, result: RemoteResult | None = None) -> None:
        super().__init__(message)
        self.result = result


def _error_text(result: RemoteResult) -> str:
    """Webinoly сам пишет свои `[ERROR] ...` сообщения в stdout, не в stderr
    (поймано вживую 2026-09-09 на `httpauth -path=all -purge`: returncode=1,
    stderr пустой, реальный текст ошибки — в stdout) — без этого фолбэка
    исключение показывало бы пустой текст после двоеточия."""
    return result.stderr.strip() or result.stdout.strip() or "неизвестная ошибка"


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
    """Ставит Webinoly (см. docs/usage/webinoly.md: -php ставится полностью неинтерактивно).

    Идемпотентно: если Webinoly уже стоит, ничего не переустанавливает.
    """
    if is_installed(server):
        return run_remote(server, "webinoly -version")

    command = f"cd /root && wget -qO weby {INSTALL_URL} && bash weby {mode}"
    result = run_remote(server, command, timeout=300)
    if not result.ok:
        raise WebinolyError(f"Установка Webinoly на {server.name} провалилась: {_error_text(result)}", result)
    return result


def parse_site_list(output: str) -> list[SiteInfo]:
    sites = []
    for match in _LIST_LINE_RE.finditer(output):
        domain, groups_raw = match.groups()
        tags = [tag.strip() for group in _TAG_RE.findall(groups_raw) for tag in group.split(",") if tag.strip()]
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
        raise WebinolyError(f"Не удалось создать сайт {domain} на {server.name}: {_error_text(result)}", result)
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
        raise WebinolyError(f"Не удалось включить SSL для {domain} на {server.name}: {_error_text(result)}", result)
    return result


def delete_site(server: Server, domain: str, revoke_ssl: bool = True) -> RemoteResult:
    revoke = "-revoke=on" if revoke_ssl else "-revoke=off"
    result = run_remote(server, f"sudo site {domain} -delete=force {revoke}")
    if not result.ok:
        raise WebinolyError(f"Не удалось удалить сайт {domain} на {server.name}: {_error_text(result)}", result)
    return result


def webroot(domain: str) -> str:
    return f"/var/www/{domain}/htdocs"


def fix_ownership(server: Server, domain: str) -> RemoteResult:
    """Обязательный шаг после заливки файлов (см. docs/usage/webinoly.md): без него nginx отдаёт 403."""
    return fix_ownership_path(server, webroot(domain))


def fix_ownership_path(server: Server, path: str) -> RemoteResult:
    result = run_remote(server, f"sudo chown -R www-data:www-data {shlex.quote(path)}")
    if not result.ok:
        raise WebinolyError(f"Не удалось поправить владельца {path}: {_error_text(result)}", result)
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
        raise WebinolyError(f"Не удалось перевести {domain} на releases-схему: {_error_text(result)}", result)
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
        raise WebinolyError(f"Не удалось переключить {domain} на релиз {ts}: {_error_text(result)}", result)
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
        raise WebinolyError(f"Не удалось почистить старые релизы {domain}: {_error_text(result)}", result)
    return result


def enable_sftp(server: Server) -> RemoteResult:
    return run_remote(server, "sudo webinoly -sftp=on")


def update_webinoly(server: Server) -> RemoteResult:
    """`hostme server update <name>` — обновляет только сам Webinoly (не пакеты
    сервера типа nginx/php, для этого `sudo stack ...`, не используется Hostme).
    Неинтерактивен (`webinoly -update` просто вызывает webinoly_update(), без
    вопросов — тот же принцип, что и у install, docs/usage/webinoly.md)."""
    result = run_remote(server, "sudo webinoly -update", timeout=120)
    if not result.ok:
        raise WebinolyError(f"Не удалось обновить Webinoly на {server.name}: {_error_text(result)}", result)
    return result


def set_http_auth(server: Server, domain: str, username: str, password: str) -> RemoteResult:
    """`hostme <domain> auth --user U --pass P` (раздел 5 PRD). Логин/пароль уходят
    в команду через shlex.quote — они приходят от пользователя (CLI-аргумент), и
    без экранирования это была бы command injection в свою же root-сессию по SSH."""
    creds = shlex.quote(f"[{username},{password}]")
    add_result = run_remote(server, f"sudo httpauth {domain} -add={creds}")
    if not add_result.ok:
        raise WebinolyError(f"Не удалось создать httpauth-юзера для {domain}: {_error_text(add_result)}", add_result)
    path_result = run_remote(server, f"sudo httpauth {domain} -path=/")
    if not path_result.ok:
        raise WebinolyError(f"Не удалось включить защиту паролем для {domain}: {_error_text(path_result)}", path_result)
    return path_result


def disable_http_auth(server: Server, domain: str) -> RemoteResult:
    # -purge не существует у httpauth (шапка /usr/bin/httpauth: "Options: -add,
    # -delete, -list, -wp-admin, -whitelist, -path") — это ошибка в публичной
    # доке Webinoly, а не наша. Реальный флаг снятия защиты — -delete.
    # Поймано вживую 2026-09-09 на roksdigital.ru: -purge падал с
    # "[ERROR] Please, enter a valid URL path!" (returncode=1, текст в stdout,
    # см. _error_text).
    result = run_remote(server, f"sudo httpauth {domain} -path=all -delete")
    if not result.ok:
        raise WebinolyError(f"Не удалось снять пароль с {domain}: {_error_text(result)}", result)
    return result


def add_redirect(server: Server, domain: str, from_path: str, to: str, http_code: int = 302) -> RemoteResult:
    command = (
        f"sudo site {domain} -redirection -from={shlex.quote(from_path)} -to={shlex.quote(to)} -http-code={http_code}"
    )
    result = run_remote(server, command)
    if not result.ok:
        raise WebinolyError(
            f"Не удалось добавить redirect {from_path} -> {to} для {domain}: {_error_text(result)}", result
        )
    return result


def remove_redirect(server: Server, domain: str, from_path: str) -> RemoteResult:
    result = run_remote(server, f"sudo site {domain} -redirection -delete -from={shlex.quote(from_path)}")
    if not result.ok:
        raise WebinolyError(f"Не удалось удалить redirect {from_path} для {domain}: {_error_text(result)}", result)
    return result


_CORS_SNIPPET_NAME = "hostme-cors-nginx.conf"


def _cors_snippet_path(domain: str) -> str:
    return f"/var/www/{domain}/{_CORS_SNIPPET_NAME}"


def _render_cors_snippet(origins: list[str]) -> str:
    """У Webinoly нет per-site CORS-флага (docs/usage/webinoly.md, «Кастомный Nginx-конфиг»).
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


def _write_snippet_or_remove(server: Server, domain: str, path: str, content: str, *, label: str) -> RemoteResult:
    """Общая безопасная заливка nginx-сниппета: пустой content -> удалить файл,
    иначе залить + nginx -t + reload, с откатом файла при поломке конфига.
    Используется и для CORS, и для произвольных пользовательских сниппетов."""
    quoted_path = shlex.quote(path)

    if not content:
        result = run_remote(server, f"rm -f {quoted_path}")
        if not result.ok:
            raise WebinolyError(f"Не удалось убрать {label} для {domain}: {_error_text(result)}", result)
        return _reload_nginx(server, domain, action=f"удаление {label}")

    encoded = base64.b64encode(content.encode()).decode()
    write_result = run_remote(server, f"echo {encoded} | base64 -d > {quoted_path}")
    if not write_result.ok:
        raise WebinolyError(f"Не удалось залить {label} для {domain}: {_error_text(write_result)}", write_result)

    return _reload_nginx(
        server, domain, action=f"включение {label}", rollback=lambda: run_remote(server, f"rm -f {quoted_path}")
    )


def set_cors(server: Server, domain: str, origins: list[str]) -> RemoteResult:
    content = _render_cors_snippet(origins) if origins else ""
    return _write_snippet_or_remove(server, domain, _cors_snippet_path(domain), content, label="CORS-сниппет")


_CUSTOM_SNIPPET_NAME = "hostme-custom-nginx.conf"


def custom_nginx_snippet_path(domain: str) -> str:
    return f"/var/www/{domain}/{_CUSTOM_SNIPPET_NAME}"


def set_custom_nginx_snippet(server: Server, domain: str, content: str) -> RemoteResult:
    """`hostme <domain> config --nginx-snippet PATH` / `--no-nginx-snippet`.
    Webinoly не даёт кастомных per-site nginx-настроек из коробки (docs/usage/webinoly.md,
    «Кастомный Nginx-конфиг») — общий механизм для того, чего нет в стандартных
    флагах Hostme (config --cors/--redirect) и дефолтах (apply_site_defaults): кастомный error_page,
    что угодно ещё. В отличие от CORS-сниппета содержимое произвольное — за
    корректность отвечает пользователь, но безопасность та же: nginx -t перед
    reload, откат файла при поломке (сломанный конфиг никогда не попадёт в
    работающий nginx). Как и у CORS-сниппета — на уровне server{}, не своя
    location / (её уже объявил сам Webinoly, дублировать нельзя)."""
    return _write_snippet_or_remove(
        server, domain, custom_nginx_snippet_path(domain), content, label="custom nginx-сниппет"
    )


_DEFAULTS_SNIPPET_NAME = "hostme-defaults-nginx.conf"


def apply_site_defaults(server: Server, domain: str) -> RemoteResult:
    """Дефолты каждого сайта (политика закрывающего слэша, кэш `/_astro/`) —
    `data/nginx-defaults.conf`. Пишется в `/var/www/<domain>/*-nginx.conf`: такие
    файлы Webinoly подключает сам и не перезаписывает при `webinoly -update`.
    Перезаливаем на каждом деплое и `server update` — новая версия hostme
    доезжает до всех сайтов без отдельной миграции."""
    return _write_snippet_or_remove(
        server, domain, f"/var/www/{domain}/{_DEFAULTS_SNIPPET_NAME}", load_nginx_defaults(), label="nginx-дефолты"
    )


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
            f"nginx не перезагружался): {_error_text(test_result)}",
            test_result,
        )
    reload_result = run_remote(server, "sudo systemctl reload nginx")
    if not reload_result.ok:
        raise WebinolyError(
            f"Не удалось перезагрузить nginx после {action} для {domain}: {_error_text(reload_result)}", reload_result
        )
    return reload_result
