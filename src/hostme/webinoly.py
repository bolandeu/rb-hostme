from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from hostme.config import Server
from hostme.ssh import RemoteResult, run_remote

SiteType = Literal["html", "php"]

INSTALL_URL = "qrok.es/wy"
# Реальный формат `sudo site -list` (подтверждено на sites-first-beget,
# 2026-09-09): несколько отдельных скобочных групп подряд без разделителя,
# напр. " + e2edebug2.antagorapp.ru (HTML)(NoSSL) " — не "(HTML, NoSSL)".
_LIST_LINE_RE = re.compile(r"^\s*\+\s+(\S+)\s+((?:\([^)]*\))+)\s*$", re.MULTILINE)
_TAG_RE = re.compile(r"\(([^)]*)\)")


class WebinolyError(Exception):
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
    """Ставит Webinoly (см. AGENTS.md: -php ставится полностью неинтерактивно).

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


def create_site(server: Server, domain: str, site_type: SiteType) -> RemoteResult:
    flag = "-html" if site_type == "html" else "-php"
    result = run_remote(server, f"sudo site {domain} {flag}")
    if not result.ok:
        raise WebinolyError(f"Не удалось создать сайт {domain} на {server.name}: {result.stderr}", result)
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
    """Обязательный шаг после заливки файлов (см. AGENTS.md): без него nginx отдаёт 403."""
    result = run_remote(server, f"sudo chown -R www-data:www-data {webroot(domain)}")
    if not result.ok:
        raise WebinolyError(f"Не удалось поправить владельца файлов {domain}: {result.stderr}", result)
    return result
