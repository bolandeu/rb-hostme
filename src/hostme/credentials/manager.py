from __future__ import annotations

import json
import os
import re

import keyring
import keyring.errors

from hostme.core.errors import CredentialStoreUnavailableError

_PACKAGE_NAME = "hostme"

# "Провайдер" здесь — свой смысл под hostme: имя Target'а (сторонний ftp/sftp/ssh
# хостинг), т.к. это единственные секреты, которые CLI вообще хранит (architecture.md
# §4, "per-target credentials"). Один секрет на target — пароль; ssh_key остаётся
# путём к локальному файлу ключа, не строкой-секретом, и через этот модуль не идёт.


def _service_name(provider: str) -> str:
    return f"{_PACKAGE_NAME}:{provider}"


def _env_var_name(provider: str, field: str) -> str:
    # provider — часто домен/хостнейм Target'а (например "top-ved.ru"), в котором
    # "." и "-" не валидны в имени переменной окружения — заменяем на "_".
    safe_provider = re.sub(r"[^A-Za-z0-9]", "_", provider).upper()
    return f"{_PACKAGE_NAME.upper()}_{safe_provider}_{field.upper()}"


def read_fields_from_env(provider: str, fields: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in fields:
        value = os.environ.get(_env_var_name(provider, field))
        if value is not None:
            result[field] = value
    return result


def get_credential(provider: str, *, env_fields: list[str] | None = None) -> dict[str, str] | None:
    """Переменные окружения побеждают построчно то, что лежит в keychain —
    так можно переопределить один ротированный пароль, не трогая остальное."""
    try:
        stored_raw = keyring.get_password(_service_name(provider), provider)
    except keyring.errors.KeyringError as exc:
        raise CredentialStoreUnavailableError(provider, str(exc)) from exc
    stored: dict[str, str] = json.loads(stored_raw) if stored_raw else {}
    fields_to_check = env_fields or list(stored.keys()) or ["password"]
    merged = {**stored, **read_fields_from_env(provider, fields_to_check)}
    return merged or None


def store_credential(provider: str, fields: dict[str, str]) -> None:
    try:
        keyring.set_password(_service_name(provider), provider, json.dumps(fields))
    except keyring.errors.KeyringError as exc:
        raise CredentialStoreUnavailableError(provider, str(exc)) from exc


def delete_credential(provider: str) -> None:
    try:
        keyring.delete_password(_service_name(provider), provider)
    except keyring.errors.PasswordDeleteError:
        pass  # уже отсутствует — удаление несуществующего секрета не ошибка
    except keyring.errors.KeyringError as exc:
        raise CredentialStoreUnavailableError(provider, str(exc)) from exc


# Обёртки для частого случая "один секрет на provider" (у hostme это пароль Target'а).


def get_secret(provider: str, field: str = "password") -> str | None:
    credential = get_credential(provider, env_fields=[field])
    return credential.get(field) if credential else None


def store_secret(provider: str, secret: str, field: str = "password") -> None:
    store_credential(provider, {field: secret})


def delete_secret(provider: str) -> None:
    delete_credential(provider)
