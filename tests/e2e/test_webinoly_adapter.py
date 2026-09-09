"""
E2E для src/hostme/webinoly.py на реальном сервере — юнит-тесты в
test_webinoly.py мокают run_remote и не ловят реальный вывод/поведение Webinoly.

Запуск:
  HOSTME_E2E_HOST=212.67.13.95 HOSTME_E2E_USER=root HOSTME_E2E_BASE_DOMAIN=antagorapp.ru \
  uv run pytest -m e2e tests/e2e/test_webinoly_adapter.py
"""

import os
import subprocess
import time
import uuid

import pytest

from hostme import webinoly
from hostme.config import Server
from hostme.ssh import run_remote

pytestmark = pytest.mark.e2e


@pytest.fixture
def base_domain() -> str:
    domain = os.environ.get("HOSTME_E2E_BASE_DOMAIN")
    assert domain, "HOSTME_E2E_BASE_DOMAIN не задан"
    return domain


@pytest.fixture
def domain(real_server: Server, base_domain: str):
    name = f"e2e-adapter-{uuid.uuid4().hex[:8]}.{base_domain}"
    yield name
    try:
        webinoly.delete_site(real_server, name)
    except webinoly.WebinolyError:
        pass


def test_is_installed_true_on_real_server(real_server: Server) -> None:
    assert webinoly.is_installed(real_server) is True


def test_install_is_noop_when_already_installed(real_server: Server) -> None:
    result = webinoly.install(real_server)
    assert result.ok
    assert "Webinoly version" in result.stdout


def test_full_static_site_lifecycle(real_server: Server, base_domain: str, domain: str) -> None:
    webinoly.create_site(real_server, domain, "html")
    assert webinoly.site_exists(real_server, domain) is True

    webinoly.enable_ssl(real_server, domain, add_to_wildcard=base_domain)

    marker = uuid.uuid4().hex
    upload = run_remote(
        real_server, f"echo '{marker}' | sudo tee {webinoly.webroot(domain)}/index.html"
    )
    assert upload.ok
    webinoly.fix_ownership(real_server, domain)

    time.sleep(2)
    curl = subprocess.run(
        ["curl", "-s", "--max-time", "15", f"https://{domain}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert marker in curl.stdout

    webinoly.delete_site(real_server, domain)
    assert webinoly.site_exists(real_server, domain) is False
