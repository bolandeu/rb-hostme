"""The static deploy a foreign project does, walked through the CLI on a real server.

Every call goes to the real `hostme` in a subprocess (tests/e2e/conftest.py): the surge
grammar (`hostme <path> <domain>`), the guard, the exit codes and the `--json` envelope
are what is under test here. Fails when the served bytes differ from the folder.

Запуск:
  HOSTME_E2E_HOST=212.67.13.95 HOSTME_E2E_USER=root HOSTME_E2E_BASE_DOMAIN=antagorapp.ru \
  uv run pytest -m e2e tests/e2e/test_webinoly_smoke.py
"""

import json
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_static_site_full_lifecycle(
    cli: Callable[..., subprocess.CompletedProcess[str]],
    e2e_server: str,
    cli_domain: str,
    tmp_path: Path,
    web_get: Callable[[str], str],
) -> None:
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    page = f"<html><body><h1>{uuid.uuid4().hex}</h1></body></html>"
    (site_dir / "index.html").write_text(page)

    deploy = cli(str(site_dir), cli_domain, "--server", e2e_server, "--json")
    assert deploy.returncode == 0, deploy.stderr
    payload = json.loads(deploy.stdout)
    # json.loads already proves stdout is one clean object, with no progress lines in it.
    assert payload["ok"] is True
    assert payload["url"] == f"https://{cli_domain}"

    assert web_get(payload["url"]) == page

    listing = cli("list", "--json")
    assert listing.returncode == 0, listing.stderr
    assert cli_domain in [site["domain"] for site in json.loads(listing.stdout)["sites"]]

    # The guard on a destructive command: no --confirm, no TTY — exit 2 and the error envelope.
    refused = cli(cli_domain, "teardown", "--json")
    assert refused.returncode == 2
    error = json.loads(refused.stdout)
    assert error["ok"] is False
    assert error["error"]["code"] == "INVALID_ARGUMENTS"

    teardown = cli(cli_domain, "teardown", "--confirm", "--json")
    assert teardown.returncode == 0, teardown.stderr
    listing = cli("list", "--json")
    assert cli_domain not in [site["domain"] for site in json.loads(listing.stdout)["sites"]]
