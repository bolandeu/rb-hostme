import os

import keyring.errors
import pytest

from hostme import output
from hostme.credentials import manager as credentials


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
