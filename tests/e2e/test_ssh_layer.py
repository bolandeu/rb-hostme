"""
E2E для src/hostme/ssh.py на реальном сервере — юнит-тесты мокают subprocess
и не ловят реальные особенности (SSH-алиасы, форматы аргументов rsync и т.п.).

Запуск: HOSTME_E2E_HOST=<ip сервера> HOSTME_E2E_USER=root uv run pytest -m e2e
"""

import os
import tempfile
from pathlib import Path

import pytest

from hostme import ssh
from hostme.config import Server

pytestmark = pytest.mark.e2e


def test_run_remote_executes_real_command(real_server: Server) -> None:
    result = ssh.run_remote(real_server, "echo hostme-ssh-e2e")
    assert result.ok
    assert "hostme-ssh-e2e" in result.stdout


def test_run_remote_nonzero_exit_does_not_raise(real_server: Server) -> None:
    result = ssh.run_remote(real_server, "exit 7")
    assert not result.ok
    assert result.returncode == 7


def test_rsync_to_uploads_files(real_server: Server) -> None:
    marker = "hostme-rsync-e2e-marker"
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "index.html").write_text(marker)
        remote_dir = f"/tmp/hostme-e2e-{os.getpid()}"
        ssh.run_remote(real_server, f"mkdir -p {remote_dir}")
        try:
            ssh.rsync_to(tmp, real_server, remote_dir)
            check = ssh.run_remote(real_server, f"cat {remote_dir}/index.html")
            assert check.stdout.strip() == marker
        finally:
            ssh.run_remote(real_server, f"rm -rf {remote_dir}")
