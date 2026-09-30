from __future__ import annotations

from importlib.metadata import Distribution, PackageNotFoundError, distribution

from hostme._distribution import DIST_NAME, DIST_NAME_LEGACY

DEV_VERSION = "0.0.0-dev"


def _distribution() -> Distribution:
    """Установленный дистрибутив: по DIST_NAME, иначе по DIST_NAME_LEGACY (переименование в процессе, стандарт §10)."""
    for name in (DIST_NAME, DIST_NAME_LEGACY):
        if name:
            try:
                return distribution(name)
            except PackageNotFoundError:
                continue
    raise PackageNotFoundError(DIST_NAME)


def package_summary() -> str:
    """Однострочный `description` из pyproject.toml — как установлен."""
    try:
        return _distribution().metadata["Summary"] or ""
    except PackageNotFoundError:
        return ""


def installed_version() -> str | None:
    """Версия установленного пакета, или None, если пакет не установлен вовсе
    (запуск из исходников без даже editable-установки) — «dev-сборка»."""
    try:
        return _distribution().version
    except PackageNotFoundError:
        return None
