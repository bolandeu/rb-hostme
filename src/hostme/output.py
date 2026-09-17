from __future__ import annotations

import json
import sys
from typing import NoReturn

import typer
from rich.console import Console
from rich.markup import escape as rich_escape

from hostme.core.errors import AbortedError, HostmeError, InvalidArgumentsError

console = Console()
err_console = Console(stderr=True)

_json_mode = False
_non_interactive = False
_dry_run = False


def set_json_mode(enabled: bool) -> None:
    global _json_mode
    _json_mode = enabled


def is_json_mode() -> bool:
    return _json_mode


def set_non_interactive(enabled: bool) -> None:
    global _non_interactive
    _non_interactive = enabled


def is_non_interactive() -> bool:
    # --json подразумевает неинтерактивный вызов (агент), даже без явного
    # --non-interactive — иначе typer.confirm() ниже повис бы на stdin,
    # который агент не читает.
    return _non_interactive or _json_mode


def set_dry_run(enabled: bool) -> None:
    global _dry_run
    _dry_run = enabled


def is_dry_run() -> bool:
    return _dry_run


def success(message: str, **fields: object) -> None:
    if _json_mode:
        console.print_json(data={"ok": True, "message": message, **fields})
    else:
        # rich_escape — message может быть динамическим (домен, путь,
        # чужой вывод) и случайно содержать "[...]", которое иначе Rich
        # принял бы за markup-тег и молча съел бы из вывода.
        console.print(f"[green]✔[/green] {rich_escape(message)}")


def info(message: str, **fields: object) -> None:
    if _json_mode:
        console.print_json(data={"ok": True, "message": message, **fields})
    else:
        console.print(rich_escape(message))


def error(exc: HostmeError | str) -> NoReturn:
    if isinstance(exc, HostmeError):
        message, code, exit_code, action = exc.message, exc.code, exc.exit_code, exc.action
    else:
        message, code, exit_code, action = str(exc), "ERROR", 1, None

    if _json_mode:
        payload: dict[str, object] = {"ok": False, "error": {"code": code, "message": message}}
        if action:
            payload["error"]["action"] = action  # type: ignore[index]
        # Пишем в stderr напрямую, а не через Console.print() — Rich переносит
        # длинный текст по словам, что ломает однострочный JSON.
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    else:
        err_console.print(f"[red]✖[/red] {rich_escape(message)}")
        if action:
            err_console.print(f"  [dim]→ {rich_escape(action)}[/dim]")
    sys.exit(exit_code)


def require_confirmation(description: str, yes: bool) -> None:
    """Единый гейт подтверждения для деструктивных команд (teardown/rollback/
    maintenance — свой сервер и target одинаково, раздел 10 architecture.md).

    --yes закрывает вопрос сразу. Иначе в неинтерактивном режиме (--json
    и/или --non-interactive) требуем явный --yes отдельной ошибкой — не
    проходим молча и не зависаем на typer.confirm() без stdin. В
    интерактивном терминале — обычный запрос да/нет.
    """
    if yes:
        return
    if is_non_interactive():
        raise InvalidArgumentsError(
            f"{description} требует явного --yes в неинтерактивном режиме (--json/--non-interactive)",
            action="Повтори с --yes, если это осознанное решение.",
        )
    if not typer.confirm(f"{description}. Продолжить?"):
        raise AbortedError(description)
