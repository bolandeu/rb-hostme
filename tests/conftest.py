"""Shared fixtures: rerun a test file under the CI environment; isolate the config/data dirs, the keychain and stdin."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable

import keyring.errors
import pytest
import typer
import typer.core

from hostme import config, output
from hostme.credentials import manager as credentials
from hostme.providers import ssh

# Typer reads these once, at import, and then forces terminal output — what a CI runner sets.
CI_ENV = {"GITHUB_ACTIONS": "true", "FORCE_COLOR": "1", "PY_COLORS": "1"}


@pytest.fixture
def same_in_ci(request: pytest.FixtureRequest) -> Callable[[str], None]:
    """Rerun this file's tests matching `-k` under CI_ENV in a fresh interpreter: the only way to set a value read at import."""
    if request.config.getoption("--snapshot-update"):
        pytest.skip("the snapshots are being written; there is nothing to compare yet")

    def run(selection: str) -> None:
        options = ["-k", selection, "-p", "no:cacheprovider", "--no-cov", "-q"]
        command = [sys.executable, "-m", "pytest", str(request.path), *options]
        env = {**os.environ, **CI_ENV}
        result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout[-3000:]

    return run


class _FakeKeyring:
    """In-memory замена keyring: тесты не должны трогать реальный OS keychain.

    Поймано CI: на Mac разработчика тесты молча писали `hostme:ext1` в настоящий
    login.keychain, а на Linux-раннере без бэкенда падали с NoKeyringError.
    Тот же интерфейс, что у модуля keyring (включая `errors`, на который
    ссылаются except-ветки в credentials/manager.py).
    """

    errors = keyring.errors

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError(f"{service}/{username} not found")
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    # Ни один тест (включая CliRunner с миграцией в root-callback) не должен
    # трогать настоящие ~/.config/hostme и user_data_dir.
    root = tmp_path_factory.mktemp("hostme-home")
    config_dir, data_dir = root / "config", root / "data"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "SERVERS_FILE", config_dir / "servers.yaml")
    monkeypatch.setattr(config, "SETTINGS_FILE", config_dir / "settings.yaml")
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "SITES_FILE", data_dir / "sites.yaml")
    monkeypatch.setattr(config, "TARGET_BACKUPS_DIR", data_dir / "target-backups")
    monkeypatch.setattr(ssh, "_CONTROL_DIR", root / "cache" / "ssh-control")


@pytest.fixture(autouse=True)
def tty_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    # pytest подменяет stdin не-терминалом; интерактивные ветки тестируются с «как будто TTY»,
    # ветка без TTY — отдельным тестом, который возвращает False.
    monkeypatch.setattr(output, "_stdin_is_tty", lambda: True)


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> _FakeKeyring:
    fake = _FakeKeyring()
    monkeypatch.setattr(credentials, "keyring", fake)
    return fake


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("HOSTME_E2E_HOST"):
        return
    skip_e2e = pytest.mark.skip(reason="e2e тесты требуют реальный сервер: задай HOSTME_E2E_HOST (см. AGENTS.md)")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)


@pytest.fixture
def e2e_host() -> str:
    host = os.environ.get("HOSTME_E2E_HOST")
    assert host, "HOSTME_E2E_HOST не задан"
    return host


@pytest.fixture
def real_server(e2e_host: str):
    from hostme.config import Server

    user = os.environ.get("HOSTME_E2E_USER", "root")
    key = os.environ.get("HOSTME_E2E_KEY", "~/.ssh/bolandau")
    return Server(name="e2e", host=e2e_host, user=user, ssh_key=key)


@pytest.fixture
def make_ctx() -> Callable[..., typer.Context]:
    """A command's ctx with the given modes in ctx.obj (json, quiet, verbose, non_interactive, dry_run), all off by default.

    Что root-callback (cli.main_options) кладёт в ctx.obj — для тестов output и сервисов без запуска CLI.
    """

    def make(**modes: bool) -> typer.Context:
        obj = {"json": False, "quiet": False, "verbose": False, "non_interactive": False, "dry_run": False}
        return typer.Context(typer.core.TyperCommand("test"), obj={**obj, **modes})

    return make
