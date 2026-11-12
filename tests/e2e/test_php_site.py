"""A PHP site from a folder to a URL, walked through the CLI on a real server.

The folder holds one `index.php`; the served body must be what PHP computed, not the
source. Fails when the deploy created an html site (`-html` in Webinoly), because the
script would come back as text.

Запуск:
  HOSTME_E2E_HOST=212.67.13.95 HOSTME_E2E_USER=root HOSTME_E2E_BASE_DOMAIN=antagorapp.ru \
  uv run pytest -m e2e tests/e2e/test_php_site.py
"""

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_php_site_serves_computed_output(
    cli: Callable[..., subprocess.CompletedProcess[str]],
    e2e_server: str,
    cli_domain: str,
    tmp_path: Path,
    web_get: Callable[[str], str],
) -> None:
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.php").write_text(f'<?php echo "php-ok-" . {6 * 7}; ?>')

    deploy = cli(str(site_dir), cli_domain, "--server", e2e_server, "--json")
    assert deploy.returncode == 0, deploy.stderr
    payload = json.loads(deploy.stdout)
    assert payload["ok"] is True
    assert payload["url"] == f"https://{cli_domain}"

    assert web_get(payload["url"]) == "php-ok-42"

    listing = cli("list", "--json")
    assert listing.returncode == 0, listing.stderr
    site = next(s for s in json.loads(listing.stdout)["sites"] if s["domain"] == cli_domain)
    assert site["php"] is True
