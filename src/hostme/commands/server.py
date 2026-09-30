from __future__ import annotations

from typing import Annotated

import typer

from hostme import config, output
from hostme.core import services

app = output.group("Управление серверами (свои VPS с Webinoly).")


@app.command("add")
@output.guard
def add(
    name: Annotated[str, typer.Option("--name", help="Имя сервера в реестре hostme (любое короткое).")],
    host: Annotated[str, typer.Option("--host", help="Хост или IP для SSH.")],
    user: Annotated[str, typer.Option("--user", help="SSH-пользователь с passwordless sudo.")] = "root",
    key: Annotated[str, typer.Option("--key", help="Путь к приватному SSH-ключу.")] = "~/.ssh/id_ed25519",
    default: Annotated[bool, typer.Option("--default", help="Сделать сервером по умолчанию для деплоя.")] = False,
) -> None:
    """hostme server add --name N --host H [--user U] [--key PATH] [--default] — зарегистрировать сервер.

    Только запись в реестр (~/.config/hostme/servers.yaml): сервер не трогается.
    Требования к серверу (Ubuntu LTS, порты 22/80/443, ключ + passwordless sudo)
    — README.md. Дальше `hostme server init <name>` ставит Webinoly.

    Example: hostme server add --name vps1 --host 203.0.113.10 --key ~/.ssh/id_ed25519 --default
    """
    result = services.add_server(name, host, user, key, default)
    output.success(result.pop("message"), **result)


@app.command("init")
@output.guard
def init(name: Annotated[str, typer.Argument(help="Имя сервера из `hostme server list`.")]) -> None:
    """hostme server init <name> — поставить (или проверить) Webinoly на сервере.

    Идемпотентно: на сервере с уже установленным Webinoly ничего не переустанавливает.
    Сама ОС должна быть подготовлена заранее (apt upgrade, reboot) — README.md.

    Example: hostme server init vps1
    """
    result = services.init_server(name)
    output.success(result.pop("message"), **result)


@app.command("update")
@output.guard
def update(name: Annotated[str, typer.Argument(help="Имя сервера из `hostme server list`.")]) -> None:
    """hostme server update <name> — обновить сам Webinoly на сервере (не системные пакеты).

    Example: hostme server update vps1
    """
    result = services.update_server(name)
    output.success(result.pop("message"), **result)


@app.command("list")
@output.guard
def list_() -> None:
    """hostme server list — все зарегистрированные серверы (имя, user@host, default).

    Example: hostme server list --json
    """

    def render(d: dict) -> None:
        if not d["servers"]:
            output.console.print("Серверов пока нет. `hostme server add ...`")
            return
        for s in d["servers"]:
            mark = " (default)" if s["default"] else ""
            output.console.print(f"{s['name']}{mark} — {s['user']}@{s['host']}")

    servers = config.load_servers()
    output.emit_success(
        {"servers": [{"name": s.name, "host": s.host, "user": s.user, "default": s.default} for s in servers]},
        render_human=render,
    )


@app.command("remove")
@output.guard
def remove(
    name: Annotated[str, typer.Argument(help="Имя сервера из `hostme server list`.")],
    force: Annotated[bool, typer.Option("--force", help="Убрать, даже если на нём числятся сайты.")] = False,
) -> None:
    """hostme server remove <name> [--force] — убрать сервер из локального реестра.

    Сервер и сайты на нём не трогаются — только запись в ~/.config/hostme.
    Без --force отказывается, пока за сервером числятся сайты (сначала teardown).

    Example: hostme server remove vps1
    """
    result = services.remove_server(name, force)
    output.success(result.pop("message"), **result)
