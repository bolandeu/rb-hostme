from __future__ import annotations

import re


class HostmeError(Exception):
    """Базовый класс ожидаемых, понятных пользователю ошибок hostme.

    Любая ошибка этого типа доходит до пользователя/агента как понятное
    сообщение в stderr (или JSON-объект {"ok": false, "error": {code,
    message, action}} в stdout при --json) и exit code согласно
    `code`/`exit_code`, без трейсбека (раздел 9 PRD, conventions.md
    cli-builder). Подклассы ниже — фиксированная таблица кодов из
    conventions.md; всё, что не попало ни в один из них, `output.guard`
    превращает в UNEXPECTED.

    `code = "ERROR"` (exit 1) — осознанная, но не классифицированная
    ошибка состояния («у сайта нет более старого релиза»): это не баг
    (не UNEXPECTED) и не неверный аргумент (не INVALID_ARGUMENTS).
    """

    code = "ERROR"
    exit_code = 1

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.action = action

    def to_dict(self) -> dict:
        payload: dict = {"code": self.code, "message": self.message}
        if self.action:
            payload["action"] = self.action
        return payload


class InvalidArgumentsError(HostmeError):
    """Некорректные аргументы, до любого обращения к серверу/target:
    взаимоисключающие флаги, несуществующее имя сервера/домена/target'а в
    реестре, деструктивная команда без --confirm в неинтерактивном режиме."""

    code = "INVALID_ARGUMENTS"
    exit_code = 2


class ProviderError(HostmeError):
    """Внешний сервис не справился: ssh/rsync/lftp не найден или упал,
    Webinoly вернул ошибку, таймаут. Поднимается только из providers/ —
    core/ и commands/ сами такие не конструируют. `provider` попадает в
    JSON-конверт, чтобы агент видел, какой слой отвалился."""

    code = "PROVIDER_ERROR"
    exit_code = 5
    provider = "unknown"

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload["provider"] = self.provider
        return payload


class CredentialStoreUnavailableError(HostmeError):
    """Не удалось обратиться к OS keychain — см. credentials/manager.py."""

    code = "CREDENTIAL_STORE_UNAVAILABLE"
    exit_code = 1

    def __init__(self, provider: str, reason: str) -> None:
        # Env var name должен совпадать с credentials.manager._env_var_name —
        # provider обычно домен/хостнейм target'а, "." и "-" в нём не валидны
        # в имени переменной окружения.
        safe_provider = re.sub(r"[^A-Za-z0-9]", "_", provider).upper()
        super().__init__(
            f"Не удалось обратиться к хранилищу учётных данных ОС для target {provider!r}: {reason}",
            action=f"Задай пароль через переменную окружения HOSTME_DEPLOY_{safe_provider}_PASSWORD вместо хранения в keychain.",
        )


class CredentialsUnhealthyError(HostmeError):
    """`hostme auth status`: обязательный доступ не в порядке или какой-то неверен/истёк (стандарт §8)."""

    code = "CREDENTIALS_UNHEALTHY"
    exit_code = 3

    def __init__(self, problems: dict[str, str]) -> None:
        listed = ", ".join(f"{name}: {status}" for name, status in problems.items())
        super().__init__(
            f"Проблемы с доступами: {listed}",
            action="Подробности — в `credentials[].message`; пароль target'а — HOSTME_DEPLOY_<TARGET>_PASSWORD или "
            "keychain `hostme:<target>`, ключ сервера — файл ssh_key из `hostme server list`.",
        )


class AbortedError(HostmeError):
    """Пользователь ответил «нет» на интерактивное подтверждение."""

    code = "ABORTED"
    exit_code = 1

    def __init__(self, description: str) -> None:
        super().__init__(f"{description}: отменено пользователем.")


class UnexpectedError(HostmeError):
    """Страховочная сетка `output.guard`: исключение, которое никто не
    сопоставил с HostmeError. Агент под --json всё равно получает конверт;
    трейсбек — в stderr под --verbose. Если один и тот же UNEXPECTED
    повторяется — ему пора завести свой подкласс выше."""

    code = "UNEXPECTED"
    exit_code = 1

    def __init__(self, exc: BaseException) -> None:
        super().__init__(
            f"{type(exc).__name__}: {exc}",
            action="Повтори с --verbose, чтобы увидеть трейсбек; если повторяется — сообщи вместе с ним.",
        )
