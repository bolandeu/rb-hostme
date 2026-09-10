from __future__ import annotations


class HostmeError(Exception):
    """Базовый класс ошибок hostme — ловится централизованно в cli.py.

    Любая ошибка этого типа доходит до пользователя/агента как понятное
    сообщение в stderr (или JSON-объект {"ok": false, "error": {code,
    message, action}} при --json) и exit code согласно `code`/`exit_code`,
    без трейсбека (раздел 9 PRD: агенты должны получать предсказуемый вывод).
    """

    code = "ERROR"
    exit_code = 1

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.action = action


class InvalidArgumentsError(HostmeError):
    """Некорректная комбинация флагов/аргументов, до любого обращения к
    серверу/target — например, --connection вне ssh/ftp/sftp или взаимно
    исключающие флаги вместе."""

    code = "INVALID_ARGUMENTS"
    exit_code = 2


class ConfirmationRequiredError(HostmeError):
    """Деструктивная операция без --yes в неинтерактивном режиме (--json
    и/или --non-interactive) — см. output.require_confirmation."""

    code = "CONFIRMATION_REQUIRED"
    exit_code = 2
