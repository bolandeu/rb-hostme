import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("HOSTME_E2E_HOST"):
        return
    skip_e2e = pytest.mark.skip(
        reason="e2e тесты требуют реальный сервер: задай HOSTME_E2E_HOST (см. AGENTS.md)"
    )
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
