"""The path a new user walks first, from a bare Ubuntu box to a site over HTTPS, through the CLI.

The other e2e files assume Webinoly is already installed; this one runs `hostme server init`
(Webinoly install + sftp) itself, so a clean server, its SSH key and passwordless sudo are
required, and the A record of HOSTME_E2E_BASE_DOMAIN must point at it — Let's Encrypt
validates over HTTP-01. The box is not clean after the run: Webinoly stays installed.

Запуск:
  HOSTME_E2E_HOST=212.67.13.95 HOSTME_E2E_USER=root HOSTME_E2E_BASE_DOMAIN=antagorapp.ru \
  HOSTME_E2E_SSH_KEY=~/.ssh/id_ed25519 uv run pytest -m e2e tests/e2e/test_from_zero.py
"""

import json
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_bare_server_to_https_site(
    cli: Callable[..., subprocess.CompletedProcess[str]],
    server_add: Callable[[str], None],
    base_domain: str,
    cli_domain: str,
    tmp_path: Path,
    web_get: Callable[[str], str],
) -> None:
    name = "from-zero"
    server_add(name)

    # Minutes: Webinoly downloads and installs nginx, php, mysql.
    init = cli("server", "init", name, "--json")
    assert init.returncode == 0, init.stderr
    assert json.loads(init.stdout)["server"] == name

    added = cli("domain", "add", name, base_domain, "--default", "--json")
    assert added.returncode == 0, added.stderr

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    page = f"<html><body><h1>{uuid.uuid4().hex}</h1></body></html>"
    (site_dir / "index.html").write_text(page)

    deploy = cli(str(site_dir), cli_domain, "--server", name, "--json")
    assert deploy.returncode == 0, deploy.stderr
    payload = json.loads(deploy.stdout)
    assert payload["ok"] is True
    assert payload["url"] == f"https://{cli_domain}"

    # urllib checks the certificate: a self-signed or expired one fails here.
    assert web_get(payload["url"]) == page
