from __future__ import annotations

from typing import Annotated

import typer

from hostme import output
from hostme.core.version import DEV_VERSION, installed_version
from hostme.credentials import health

app = output.group("Доступы к серверам и target'ам: откуда берутся и работают ли (значения не печатаются).")


@app.command("status")
@output.guard
def auth_status(
    check: Annotated[
        bool,
        typer.Option(
            "--check", help="Ещё и проверить каждый доступ одним read-only входом (ssh true / lftp cls), 10 с."
        ),
    ] = False,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Только этот доступ: server:<имя> или target:<имя>.")
    ] = None,
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
    payload, problem = health.status("hostme", installed_version() or DEV_VERSION, check=check, only=provider)
    output.emit_report(payload, health.render, problem)
