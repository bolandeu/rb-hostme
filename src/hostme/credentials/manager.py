from __future__ import annotations

import json
import logging
import os
import re

import keyring
import keyring.errors

from hostme.core.errors import CredentialStoreUnavailableError

_PACKAGE_NAME = "hostme"
_log = logging.getLogger(__name__)

# "Провайдер" здесь — свой смысл под hostme: имя Target'а (сторонний ftp/sftp/ssh
# хостинг), т.к. это единственные секреты, которые CLI вообще хранит (architecture.md
# §4, "per-target credentials"). Один секрет на target — пароль; ssh_key остаётся
# путём к локальному файлу ключа, не строкой-секретом, и через этот модуль не идёт.
#
# Порядок (стандарт §13, headless-серверы под `doppler run`): сначала переменная
# окружения HOSTME_DEPLOY_<TARGET>_PASSWORD (контракт ключей sysadmin, правило 6), потом
# OS keychain `hostme:<target>`. Keychain необязателен: на Linux без secret service
# чтение молча даёт «нет», а не ошибку. Старое имя HOSTME_<TARGET>_PASSWORD читается
# запасным на один релиз — пока sysadmin переименовывает ключи в Doppler.


def service_name(provider: str) -> str:
    return f"{_PACKAGE_NAME}:{provider}"


def env_var_name(provider: str, field: str = "password") -> str:
    # provider — часто домен/хостнейм Target'а (например "top-ved.ru"), в котором
    # "." и "-" не валидны в имени переменной окружения — заменяем на "_".
    safe_provider = re.sub(r"[^A-Za-z0-9]", "_", provider).upper()
    return f"{_PACKAGE_NAME.upper()}_DEPLOY_{safe_provider}_{field.upper()}"


def _legacy_env_var_name(provider: str, field: str = "password") -> str:
    # TODO: убрать в следующем релизе после переименования ключей в Doppler.
    safe_provider = re.sub(r"[^A-Za-z0-9]", "_", provider).upper()
    return f"{_PACKAGE_NAME.upper()}_{safe_provider}_{field.upper()}"


def _from_env(provider: str, field: str) -> tuple[str, str] | None:
    """(значение, имя переменной): новое имя, иначе старое — с предупреждением."""
    name = env_var_name(provider, field)
    if (value := os.environ.get(name)) is not None:
        return value, name
    legacy = _legacy_env_var_name(provider, field)
    if (value := os.environ.get(legacy)) is not None:
        _log.warning("%s устарело — переименуй в %s", legacy, name)
        return value, legacy
    return None


def read_fields_from_env(provider: str, fields: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in fields:
        if (found := _from_env(provider, field)) is not None:
            result[field] = found[0]
    return result


# Первая ошибка keychain в процессе (headless Linux, CI): дальше — только env,
# и в лог об этом один раз на DEBUG, чтобы сервер с ключами в env не шумел.
_keychain_problem: str | None = None


def _stored(provider: str) -> dict[str, str]:
    global _keychain_problem
    try:
        raw = keyring.get_password(service_name(provider), provider)
    except keyring.errors.KeyringError as exc:
        if _keychain_problem is None:
            _keychain_problem = str(exc)
            _log.debug("OS keychain недоступен (%s) — только переменные окружения", exc)
        return {}
    return json.loads(raw) if raw else {}


def locate(provider: str, field: str = "password") -> tuple[str, str, str] | None:
    """(значение, источник "env" | "keychain", где: имя переменной или сервис keychain) — для `auth status`."""
    if (found := _from_env(provider, field)) is not None:
        return found[0], "env", found[1]
    stored = _stored(provider)
    if field in stored:
        return stored[field], "keychain", service_name(provider)
    return None


def get_credential(provider: str, *, env_fields: list[str] | None = None) -> dict[str, str] | None:
    """Переменные окружения побеждают построчно то, что лежит в keychain —
    так можно переопределить один ротированный пароль, не трогая остальное."""
    fields = env_fields or ["password"]
    from_env = read_fields_from_env(provider, fields)
    # Всё нужное уже в env — keychain не трогаем вовсе (на сервере его может не быть).
    stored = {} if len(from_env) == len(fields) else _stored(provider)
    merged = {**stored, **from_env}
    return merged or None


def store_credential(provider: str, fields: dict[str, str]) -> None:
    try:
        keyring.set_password(service_name(provider), provider, json.dumps(fields))
    except keyring.errors.KeyringError as exc:
        raise CredentialStoreUnavailableError(provider, str(exc)) from exc


def delete_credential(provider: str) -> None:
    try:
        keyring.delete_password(service_name(provider), provider)
    except keyring.errors.PasswordDeleteError:
        pass  # уже отсутствует — удаление несуществующего секрета не ошибка
    except keyring.errors.KeyringError as exc:
        # Хранилища нет (headless) — значит, и удалять там нечего.
        _log.debug("OS keychain недоступен при удалении %s (%s)", provider, exc)


# Обёртки для частого случая "один секрет на provider" (у hostme это пароль Target'а).


def get_secret(provider: str, field: str = "password") -> str | None:
    credential = get_credential(provider, env_fields=[field])
    return credential.get(field) if credential else None


def store_secret(provider: str, secret: str, field: str = "password") -> None:
    store_credential(provider, {field: secret})


def delete_secret(provider: str) -> None:
    delete_credential(provider)
