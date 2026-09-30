from __future__ import annotations

from hostme import output
from hostme.core import services

_ICONS = {"ok": "[green]✔[/green]", "warn": "[yellow]![/yellow]", "fail": "[red]✖[/red]"}


@output.guard
def doctor() -> None:
    """hostme doctor — проверка окружения без обращения к серверам.

    Бинарии (ssh/rsync/lftp/sshpass — по тому, что реально нужно зарегистрированным
    серверам и target'ам), права и читаемость реестров в ~/.config/hostme, наличие
    объявленных ssh-ключей на диске. Всегда exit 0 — сам отчёт и есть результат,
    `ok` говорит, все ли проверки прошли.

    Example: hostme doctor --json
    """

    def render(d: dict) -> None:
        for check in d["checks"]:
            output.console.print(f"{_ICONS[check['status']]} {check['name']}: {check['detail']}")

    output.emit_success(services.run_doctor(), render_human=render)
