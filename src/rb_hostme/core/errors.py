"""Every error a command raises, with its exit code and error code, and the table of exit codes the Standard defines."""

from __future__ import annotations

import re

from .._distribution import DIST_NAME
from .version import cli_name

# The real command (may differ from the package name) for `action` hints;
# `uv tool upgrade` takes the distribution name, which is the package's.
_CLI = cli_name()
_DIST = DIST_NAME

# Every exit code a generated CLI uses and what it means — the same table as in
# the Standard, Errors, and `describe --json`'s `exitCodes`. tests/test_describe.py
# fails when a CliError below uses a code that isn't listed here.
EXIT_CODES: dict[int, str] = {
    0: "Success",
    1: "General error (incl. UNEXPECTED and ABORTED)",
    2: "Invalid arguments",
    3: "Authentication error",
    4: "Project not initialized",
    5: "Provider error (external service: network, timeout, 5xx, 429, bad body)",
    6: "CLI too old for this project or database",
}


class CliError(Exception):
    """Base error for all expected, user-facing CLI failures.

    Every raise carries a stable `code`, a human `message`, an optional
    `action` telling the caller (human or agent) how to recover, and the
    process exit code to use. Only named, expected failure modes get a
    subclass here; anything else that escapes a command is turned into an
    `UNEXPECTED` envelope by `output.guard`, so `--json` callers always get
    JSON back.
    """

    def __init__(self, code: str, message: str, *, action: str | None = None, exit_code: int = 1) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action
        self.exit_code = exit_code

    def to_dict(self) -> dict:
        payload: dict = {"code": self.code, "message": self.message}
        if self.action:
            payload["action"] = self.action
        return payload


class ProjectNotInitialized(CliError):
    def __init__(self, path: str) -> None:
        super().__init__(
            "PROJECT_NOT_INITIALIZED",
            f"No project found at or above '{path}'.",
            action=f"Run '{_CLI} init' in the project directory.",
            exit_code=4,
        )


class AuthRequired(CliError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            "AUTH_REQUIRED",
            f"Authentication is required for provider '{provider}'.",
            action=f"Run '{_CLI} auth login --provider {provider}'.",
            exit_code=3,
        )


class CredentialsUnhealthy(CliError):
    """`hostme auth status`: обязательный доступ не в порядке или какой-то неверен/истёк (Standard, Health)."""

    def __init__(self, problems: dict[str, str]) -> None:
        listed = ", ".join(f"{name}: {status}" for name, status in problems.items())
        super().__init__(
            "CREDENTIALS_UNHEALTHY",
            f"Проблемы с доступами: {listed}",
            action="Подробности — в `credentials[].message`; пароль target'а — HOSTME_DEPLOY_<TARGET>_PASSWORD или "
            "keychain `hostme:<target>`, ключ сервера — файл ssh_key из `hostme server list`.",
            exit_code=3,
        )


class DependencyTooOld(CliError):
    """Another CLI this one calls is missing or older than required (core/deps.py).

    `dist` is its distribution name — what `uv tool` knows it by (`rb-serp`
    for the `serp` command). With `install_url` the action is a
    pinned, runnable install; without it, what to install and no fake URL.
    """

    def __init__(
        self,
        name: str,
        installed: str | None,
        required: str | None,
        *,
        install_url: str | None = None,
        dist: str | None = None,
    ) -> None:
        dist = dist or name
        found = "is not installed" if installed is None else f"is {installed}"
        need = f"{name} >= {required}" if required else name
        if install_url:
            repo = install_url.removesuffix(".git")
            tag = f"v{required}" if required else "<latest release tag>"
            action = f"Run 'uv tool install \"{dist} @ git+{repo}.git@{tag}\" --force', then retry."
        elif installed is not None:
            action = f"Run 'uv tool upgrade {dist}', then retry."
        else:
            action = f"Install {need} (distribution {dist}; see its README for the install command), then retry."
        super().__init__(
            "DEPENDENCY_TOO_OLD",
            f"'{name}' {found}; {_CLI} needs {need}.",
            action=action,
            exit_code=1,
        )


class InvalidArguments(CliError):
    """Некорректные аргументы, до любого обращения к серверу/target: взаимоисключающие флаги, несуществующее имя
    сервера/домена/target'а в реестре, деструктивная команда без --confirm в неинтерактивном режиме."""

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__("INVALID_ARGUMENTS", message, action=action, exit_code=2)


class CredentialStoreUnavailable(CliError):
    """Не удалось обратиться к OS keychain — см. credentials/manager.py."""

    def __init__(self, provider: str, reason: str) -> None:
        # Env var name должен совпадать с credentials.manager.env_var_name —
        # provider обычно домен/хостнейм target'а, "." и "-" в нём не валидны
        # в имени переменной окружения.
        safe_provider = re.sub(r"[^A-Za-z0-9]", "_", provider).upper()
        super().__init__(
            "CREDENTIAL_STORE_UNAVAILABLE",
            f"Не удалось обратиться к хранилищу учётных данных ОС для target {provider!r}: {reason}",
            action=f"Задай пароль через переменную окружения HOSTME_DEPLOY_{safe_provider}_PASSWORD вместо хранения в keychain.",
            exit_code=1,
        )


class ProviderError(CliError):
    """Внешний сервис не справился: ssh/rsync/lftp не найден или упал, Webinoly вернул ошибку, таймаут.

    Поднимается только из providers/ (подкласс на каждый: `provider` — его имя) —
    core/ и commands/ сами такие не конструируют. `provider` попадает в
    JSON-конверт, чтобы агент видел, какой слой отвалился.
    """

    provider = "unknown"

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__("PROVIDER_ERROR", message, action=action, exit_code=5)

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload["provider"] = self.provider
        return payload


class CliTooOld(CliError):
    def __init__(self, installed: str, required: str) -> None:
        super().__init__(
            "CLI_TOO_OLD",
            f"This project requires {_CLI} >= {required}, but {installed} is installed.",
            action=f"Run 'uv tool upgrade {_DIST}' (or lower cli.min_version in the project's config.toml).",
            exit_code=6,
        )


class Aborted(CliError):
    """Пользователь ответил «нет» на интерактивное подтверждение."""

    def __init__(self, description: str) -> None:
        super().__init__("ABORTED", f"{description}: отменено пользователем.", exit_code=1)


class StateError(CliError):
    """Осознанная, но не классифицированная ошибка состояния («у сайта нет более старого релиза»), exit 1.

    Это не баг (не UNEXPECTED) и не неверный аргумент (не INVALID_ARGUMENTS).
    """

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__("ERROR", message, action=action, exit_code=1)


class DatabaseUnavailable(CliError):
    """`<TOOL>_DATABASE_URL` is set but unusable: unreachable, wrong credentials, not PostgreSQL (core/db.py).

    Exit 5 like any external service. Never answered by falling back to the
    local SQLite file — data written there would silently miss the shared base.
    """

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__(
            "DATABASE_UNAVAILABLE",
            message,
            action=action or "Check the database URL and that the server is reachable; then retry.",
            exit_code=5,
        )


class DatabaseNotMigrated(CliError):
    """The shared database's schema is behind this CLI's migrations (core/db.py)."""

    def __init__(self, current: str | None, head: str) -> None:
        super().__init__(
            "DATABASE_NOT_MIGRATED",
            f"The database schema is at revision {current or 'none'}, this {_CLI} needs {head}.",
            action=f"Run '{_CLI} db upgrade' (it changes the shared database — run the released version).",
            exit_code=1,
        )


class DatabaseTooNew(CliError):
    """The database was migrated by a newer release than this one: the CLI is the one to update.

    The same `CLI_TOO_OLD` code and exit 6 as `CliTooOld` — the cure is the same.
    """

    def __init__(self, current: str) -> None:
        super().__init__(
            "CLI_TOO_OLD",
            f"The database schema is at revision {current}, which this {_CLI} doesn't know: a newer release migrated it.",
            action=f"Run 'uv tool upgrade {_DIST}', then retry.",
            exit_code=6,
        )
