from __future__ import annotations

from typing import Annotated

import typer

from hostme import output
from hostme.core import services

app = output.group("Служебные (base) домены — для авто-генерации поддоменов при деплое.")


@app.command("add")
@output.guard
def add(
    server_name: Annotated[str, typer.Argument(help="Имя сервера из `hostme server list`.")],
    domain: Annotated[str, typer.Argument(help="Домен, чей wildcard (*.domain) указывает на этот сервер.")],
    default: Annotated[bool, typer.Option("--default", help="Использовать для деплоя без явного домена.")] = False,
) -> None:
    """hostme domain add <server> <domain> [--default] — зарегистрировать служебный домен.

    После этого `hostme ./dist` без домена получает `<slug-папки>.<default-домен>`.
    DNS (wildcard A-запись) и wildcard-SSL настраиваются вручную — WILDCARD-SSL.md.

    Example: hostme domain add sites-first example.com --default
    """
    result = services.add_domain(server_name, domain, default)
    output.success(result.pop("message"), **result)


@app.command("default")
@output.guard
def default(domain: Annotated[str, typer.Argument(help="Уже зарегистрированный служебный домен.")]) -> None:
    """hostme domain default <domain> — сделать служебный домен дефолтным.

    Example: hostme domain default example.com
    """
    result = services.set_default_domain(domain)
    output.success(result.pop("message"), **result)


@app.command("remove")
@output.guard
def remove(domain: Annotated[str, typer.Argument(help="Служебный домен из `hostme domain list`.")]) -> None:
    """hostme domain remove <domain> — убрать служебный домен из реестра (сайты на нём не трогаются).

    Example: hostme domain remove example.com
    """
    result = services.remove_domain(domain)
    output.success(result.pop("message"), **result)


@app.command("list")
@output.guard
def list_() -> None:
    """hostme domain list — служебные домены и какой сервер за каждым стоит.

    Example: hostme domain list
    """

    def render(d: dict) -> None:
        if not d["domains"]:
            output.console.print("Служебных доменов пока нет. `hostme domain add ...`")
            return
        for row in d["domains"]:
            mark = " (default)" if row["default"] else ""
            output.console.print(f"{row['domain']}{mark} — {row['server']}")

    rows = services.list_domains()
    output.emit_success(
        {"domains": [{"domain": d.name, "server": server_name, "default": d.default} for server_name, d in rows]},
        render_human=render,
    )
