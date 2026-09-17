from __future__ import annotations

from importlib.metadata import PackageNotFoundError, metadata
from importlib.metadata import version as pkg_version

_PACKAGE_NAME = "hostme"

DEV_VERSION = "0.0.0-dev"


def package_summary() -> str:
    """Однострочный `description` из pyproject.toml — как установлен."""
    try:
        return metadata(_PACKAGE_NAME)["Summary"] or ""
    except PackageNotFoundError:
        return ""


def installed_version() -> str | None:
    """Версия установленного пакета, или None, если пакет не установлен вовсе
    (запуск из исходников без даже editable-установки) — «dev-сборка»."""
    try:
        return pkg_version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return None
