"""Fixtures for the e2e files that walk the CLI itself: real `hostme` in a subprocess, a real server.

The subprocess gets its own HOME: it reads and writes a throwaway registry, not the
owner's live `~/.config/hostme` and `user_data_dir("hostme")` (AGENTS.md). `~/.ssh` is
symlinked into that HOME, so ssh keeps the owner's config, known_hosts and keys.

The env-var gate (`HOSTME_E2E_HOST`) and the `-m e2e` marker stay in tests/conftest.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

# A site gets its certificate on the first deploy, so the first GET can lose a race with nginx.
GET_DEADLINE_S = 60.0

Cli = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    """Run the real `hostme` CLI; every call sees the throwaway registry from this test's tmp_path."""

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        home = tmp_path / "home"
        if not home.is_dir():
            home.mkdir()
            real_ssh = Path.home() / ".ssh"
            if real_ssh.is_dir():
                (home / ".ssh").symlink_to(real_ssh)
        return subprocess.run(
            [sys.executable, "-m", "hostme.cli", *args],
            env={**os.environ, "HOME": str(home)},
            capture_output=True,
            text=True,
            check=False,
        )

    return run


@pytest.fixture
def server_add(cli: Cli, e2e_host: str) -> Callable[[str], None]:
    """`hostme server add` for the e2e host under the given name, as the default server."""

    def add(name: str) -> None:
        # expanduser here: inside the subprocess HOME is the throwaway folder, and ~ would point there.
        key = str(Path(os.environ.get("HOSTME_E2E_SSH_KEY", "~/.ssh/bolandau")).expanduser())
        added = cli(
            "server",
            "add",
            "--name",
            name,
            "--host",
            e2e_host,
            "--user",
            os.environ.get("HOSTME_E2E_USER", "root"),
            "--key",
            key,
            "--default",
        )
        assert added.returncode == 0, added.stderr

    return add


@pytest.fixture
def e2e_server(server_add: Callable[[str], None], cli: Cli) -> str:
    """Register the test server through the CLI, plus its base domain when HOSTME_E2E_BASE_DOMAIN is set."""
    server_add("e2e")
    base = os.environ.get("HOSTME_E2E_BASE_DOMAIN")
    if base:
        domain = cli("domain", "add", "e2e", base, "--default")
        assert domain.returncode == 0, domain.stderr
    return "e2e"


@pytest.fixture
def base_domain() -> str:
    domain = os.environ.get("HOSTME_E2E_BASE_DOMAIN")
    assert domain, "HOSTME_E2E_BASE_DOMAIN не задан (напр. antagorapp.ru)"
    return domain


@pytest.fixture
def cli_domain(cli: Cli, base_domain: str) -> Iterator[str]:
    """A fresh domain under the base domain; removed through the CLI after the test, pass or fail."""
    domain = f"e2e-cli-{uuid.uuid4().hex[:8]}.{base_domain}"
    yield domain
    cli(domain, "teardown", "--confirm", "--json")


@pytest.fixture
def web_get() -> Callable[[str], str]:
    """GET the URL until nginx answers, then return the body; the certificate must be valid (urllib checks it)."""

    def get(url: str) -> str:
        deadline = time.monotonic() + GET_DEADLINE_S
        problem: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 — https URL built by the test
                    return response.read().decode()
            except (urllib.error.URLError, OSError) as exc:
                problem = exc
                time.sleep(1)
        raise AssertionError(f"{url} не ответил за {GET_DEADLINE_S:.0f} с: {problem}")

    return get
