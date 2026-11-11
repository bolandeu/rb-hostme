"""
E2E-проверка реального сервера через Webinoly напрямую (SSH, через hostme.providers.ssh),
без CLI hostme: эти тесты автоматизируют то, что раньше проверялось вручную.

Переписать их на вызов самого CLI (subprocess до `hostme`), а не на
hostme.providers.ssh напрямую — idea `HOSTME-IDEA-009`.

Запуск:
  HOSTME_E2E_HOST=212.67.13.95 HOSTME_E2E_USER=root HOSTME_E2E_BASE_DOMAIN=antagorapp.ru \
  uv run pytest -m e2e
"""

import os
import subprocess
import time
import uuid

import pytest

from hostme.config import Server
from hostme.providers import ssh

pytestmark = pytest.mark.e2e


@pytest.fixture
def base_domain() -> str:
    domain = os.environ.get("HOSTME_E2E_BASE_DOMAIN")
    assert domain, "HOSTME_E2E_BASE_DOMAIN не задан (напр. antagorapp.ru)"
    return domain


@pytest.fixture
def test_domain(real_server: Server, base_domain: str):
    name = f"e2e-{uuid.uuid4().hex[:8]}.{base_domain}"
    yield name
    ssh.run_remote(real_server, f"sudo site {name} -delete=force -revoke=on")


def test_static_site_full_lifecycle(real_server: Server, base_domain: str, test_domain: str) -> None:
    create = ssh.run_remote(real_server, f"sudo site {test_domain} -html")
    assert create.ok, create.stderr

    ssl = ssh.run_remote(
        real_server,
        f"sudo site {test_domain} -ssl=on -add-to-wildcard={base_domain}",
    )
    assert ssl.ok, ssl.stderr

    marker = uuid.uuid4().hex
    upload = ssh.run_remote(
        real_server,
        f"echo '{marker}' | sudo tee /var/www/{test_domain}/htdocs/index.html "
        f"&& sudo chown -R www-data:www-data /var/www/{test_domain}/htdocs",
    )
    assert upload.ok, upload.stderr

    time.sleep(2)
    curl = subprocess.run(
        ["curl", "-s", "--max-time", "15", f"https://{test_domain}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert marker in curl.stdout

    listing = ssh.run_remote(real_server, "sudo site -list")
    assert test_domain in listing.stdout
