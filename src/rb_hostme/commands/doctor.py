"""The `doctor` command: checks of this CLI's own setup, one line per check."""

from __future__ import annotations

import typer

from .. import output
from ..core.doctor import run_doctor
from ..core.version import DEV_VERSION, installed_version

_ICONS = {"ok": "[green]✔[/green]", "warn": "[yellow]![/yellow]", "fail": "[red]✖[/red]"}


@output.guard
def doctor(
    ctx: typer.Context,
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
    verbose: bool = output.VerboseOption,
) -> None:
    """hostme doctor — проверка локального окружения и реестров (без обращения к серверам).

    Бинарии (ssh/rsync/lftp/sshpass — по тому, что реально нужно зарегистрированным
    серверам и target'ам), права и читаемость реестров (servers.yaml в ~/.config/hostme,
    sites.yaml в каталоге данных), путь, размер и политика хранения бэкапов target'ов
    (settings.yaml → target_backups: keep / max_age_days), наличие объявленных
    ssh-ключей на диске. Всегда exit 0 — сам отчёт и есть результат,
    `healthy` говорит, все ли проверки прошли; у каждой проверки `ok` и `status` (ok/warn/fail).

    Example: hostme doctor --json
    """
    report = run_doctor()
    checks: list[dict] = [{"name": "python", "ok": True, "status": "ok"}]
    checks.append({"name": "cli_version", "ok": True, "status": "ok", "detail": installed_version() or DEV_VERSION})
    report["checks"] = checks + report["checks"]

    def render(d: dict) -> None:
        for check in d["checks"]:
            detail = f": {check['detail']}" if check.get("detail") else ""
            output.human.console.print(f"{_ICONS[check['status']]} {check['name']}{detail}")

    output.emit_success(ctx, report, render_human=render)
