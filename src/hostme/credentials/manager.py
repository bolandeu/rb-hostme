"""The credential store of hostme: `rb-credentials` with this CLI's names.

"Провайдер" здесь — имя Target'а (сторонний ftp/sftp/ssh хостинг), единственные секреты, которые CLI хранит:
один пароль на target (ssh_key остаётся путём к файлу и через этот модуль не идёт).

Порядок поиска (стандарт §13, headless-серверы с переменными окружения из секрет-менеджера): переменная
`HOSTME_DEPLOY_<TARGET>_PASSWORD` (контракт ключей sysadmin), затем OS keychain `hostme:<target>`. Keychain
необязателен: на Linux без secret service чтение даёт «нет», а не ошибку.

Сам keychain, «прочитать один раз, предупредить один раз» и разбор недоступности — в общем `rb-credentials`;
здесь остаются имена hostme и маппинг ошибок на `CredentialStoreUnavailable`.
"""

from __future__ import annotations

import os
import re

import keyring  # патч-цель тестов (`hostme.credentials.manager.keyring.*`)
from rb_credentials import Store, StoreUnavailable

from hostme.core.errors import CredentialStoreUnavailable
from hostme.core.version import cli_name

_NAMESPACE = cli_name()


def _store() -> Store:
    """A store over the keyring module named here: the tests replace that module with an in-memory one."""
    return Store(_NAMESPACE, keyring=keyring, bare_field="password")


def service_name(provider: str) -> str:
    return _store().service_name(provider)


def env_var_name(provider: str, field: str = "password") -> str:
    # provider — часто домен/хостнейм Target'а (например "top-ved.ru"), в котором
    # "." и "-" не валидны в имени переменной окружения — заменяем на "_".
    safe_provider = re.sub(r"[^A-Za-z0-9]", "_", provider).upper()
    return f"{_NAMESPACE.upper()}_DEPLOY_{safe_provider}_{field.upper()}"


def read_fields_from_env(provider: str, fields: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in fields:
        value = os.environ.get(env_var_name(provider, field))
        if value is not None:
            result[field] = value
    return result


def _legacy(provider: str, fields: list[str]) -> dict[str, str]:
    return {field: env_var_name(provider, field) for field in fields}


def locate(provider: str, field: str = "password") -> tuple[str, str, str] | None:
    """(значение, источник, где) для поля — для `doctor` и `auth status`, никогда само значение."""
    located = _store().locate(provider, [field], legacy_env=_legacy(provider, [field]), legacy_env_first=True)
    return located.get(field)


def get_credential(provider: str, *, env_fields: list[str] | None = None) -> dict[str, str] | None:
    fields = env_fields or ["password"]
    return _store().get(provider, env_fields=fields, legacy_env=_legacy(provider, fields), legacy_env_first=True)


def store_credential(provider: str, fields: dict[str, str]) -> None:
    try:
        _store().store(provider, fields)
    except StoreUnavailable as exc:
        raise CredentialStoreUnavailable(provider, str(exc)) from exc


def delete_credential(provider: str) -> None:
    # Headless host without a keychain: nothing is stored there, so nothing to delete — not an error.
    try:
        _store().delete(provider, ignore_unavailable=True)
    except StoreUnavailable as exc:
        raise CredentialStoreUnavailable(provider, str(exc)) from exc


def get_secret(provider: str, field: str = "password") -> str | None:
    credential = get_credential(provider, env_fields=[field])
    return credential.get(field) if credential else None


def store_secret(provider: str, secret: str, field: str = "password") -> None:
    store_credential(provider, {field: secret})


def delete_secret(provider: str) -> None:
    delete_credential(provider)
