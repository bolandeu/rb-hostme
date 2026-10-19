from __future__ import annotations

from typing import Annotated

import typer

from hostme import config, output
from hostme.core import services

app = output.group("Сторонние хостинги (ftp/sftp/ssh, без Webinoly) — только заливка файлов.")


@app.command("add")
@output.guard
def add(
    name: Annotated[str, typer.Option("--name", help="Имя target'а (удобно — сам домен сайта).")],
    connection: Annotated[str, typer.Option("--connection", help="ssh (rsync) | sftp | ftp (lftp mirror).")],
    host: Annotated[str, typer.Option("--host", help="Хост хостинга.")],
    user: Annotated[str, typer.Option("--user", help="Логин.")],
    password: Annotated[
        str | None,
        typer.Option(
            "--password",
            help="Пароль — уходит в OS keychain, не в servers.yaml; без него — из HOSTME_DEPLOY_<NAME>_PASSWORD.",
        ),
    ] = None,
    ssh_key: Annotated[str | None, typer.Option("--ssh-key", help="Путь к ключу (только для ssh).")] = None,
    remote_path: Annotated[
        str, typer.Option("--path", help="Каталог сайта на хостинге; у shared-хостингов часто относительный.")
    ] = "/",
) -> None:
    """hostme target add --name N --connection ssh|ftp|sftp --host H --user U [--password P] [--ssh-key PATH] [--path REMOTE] — зарегистрировать сторонний хостинг.

    Target — чужая инфраструктура (shared-хостинг клиента и т.п.): hostme тут только
    транспорт, без SSL/релизов/nginx. Пароль: сначала переменная окружения
    HOSTME_DEPLOY_<NAME>_PASSWORD (тогда --password не нужен), иначе OS keychain
    `hostme:<name>`; в реестре — только has_password.

    Example: hostme target add --name client.ru --connection sftp --host sftp.host.ru --user u123 --path www
    """
    result = services.add_target(name, connection, host, user, password, ssh_key, remote_path)
    output.success(result.pop("message"), **result)


@app.command("list")
@output.guard
def list_() -> None:
    """hostme target list — зарегистрированные target'ы (без паролей — только факт их наличия).

    Example: hostme target list --json
    """

    def render(d: dict) -> None:
        if not d["targets"]:
            output.console.print("Target'ов пока нет. `hostme target add ...`")
            return
        for t in d["targets"]:
            output.console.print(f"{t['name']} ({t['connection']}) — {t['user']}@{t['host']}:{t['remote_path']}")

    targets = config.load_targets()
    output.emit_success(
        {
            "targets": [
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
            ]
        },
        render_human=render,
    )


@app.command("remove")
@output.guard
def remove(
    name: Annotated[str, typer.Argument(help="Имя target'а из `hostme target list`.")],
    force: Annotated[bool, typer.Option("--force", help="Убрать, даже если на нём числятся сайты.")] = False,
) -> None:
    """hostme target remove <name> [--force] — убрать target из реестра и его пароль из keychain.

    Файлы на хостинге не трогаются. Без --force отказывается, пока за target'ом
    числятся сайты.

    Example: hostme target remove client.ru
    """
    result = services.remove_target(name, force)
    output.success(result.pop("message"), **result)
