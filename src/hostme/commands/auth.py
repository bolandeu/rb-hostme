"""The `auth` command group: `status` reports the health of the credentials of every provider, or an empty report when
the package has none.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import Annotated

import typer

from .. import output
from ..core.errors import InvalidArguments
from ..core.version import DEV_VERSION, cli_name, installed_version, module_exists, optional_module

# `auth status` exists in every CLI (the Standard, Health); a CLI
# generated without credentials (no credentials/ package, no commands/login.py)
# reports an empty `credentials` list and exits 0. Detected at runtime so this
# file needs no template logic — same approach as doctor.py.
_PACKAGE_NAME = __name__.split(".")[0]
_HAS_CREDENTIALS = module_exists(f"{_PACKAGE_NAME}.credentials.manager")

app = output.group("Доступы к серверам и target'ам: откуда берутся и работают ли (значения не печатаются).")


@app.command("status")
@output.guard
def auth_status(
    ctx: typer.Context,
    check: Annotated[
        bool,
        typer.Option(
            "--check", help="Ещё и проверить каждый доступ одним read-only входом (ssh true / lftp cls), 10 с."
        ),
    ] = False,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Только этот доступ: server:<имя> или target:<имя>.")
    ] = None,
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """hostme auth status [--check] [--provider server:N|target:N] — здоровье доступов (стандарт §8).

    Запись на каждый сервер (`server:<имя>`, ssh-ключ — файл) и target
    (`target:<имя>`: пароль из HOSTME_DEPLOY_<TARGET>_PASSWORD, иначе keychain
    `hostme:<target>`; или ssh-ключ). Без --check — только наличие (`unchecked`/
    `missing`). Exit 0 — всё в порядке, 3 — что-то missing/invalid/unreachable,
    2 — неизвестный --provider. Форма --json — контракт для tools-watch:
    `tool`, `version`, `checked_at`, `credentials[]` с `provider`, `required`,
    `fields`, `source`, `source_ref`, `status`, `expires_at`, `quota`, `message`.

    Example: hostme auth status --check --json
    """
    tool, version = cli_name(), installed_version() or DEV_VERSION
    if not _HAS_CREDENTIALS:
        if provider is not None:
            raise InvalidArguments(f"Unknown provider '{provider}' ({tool} stores no credentials).")
        checked_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        payload = {"tool": tool, "version": version, "checked_at": checked_at, "credentials": []}
        output.emit_report(ctx, payload, lambda _: output.human.echo(f"{tool} stores no credentials."), None)
        return
    health = importlib.import_module(f"{_PACKAGE_NAME}.credentials.health")
    payload, problem = health.status(tool, version, check=check, only=provider)
    output.emit_report(ctx, payload, health.render, problem)


if _login := optional_module(f"{_PACKAGE_NAME}.commands.login"):
    app.command("login")(_login.login)
    app.command("logout")(_login.logout)
