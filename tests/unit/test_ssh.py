import subprocess
from unittest.mock import patch

import pytest

from hostme import ssh
from hostme.config import Server


def make_server() -> Server:
    return Server(name="vps1", host="1.2.3.4", user="root", ssh_key="~/.ssh/id")


def fake_completed(returncode=0, stdout="ok", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_remote_success():
    with patch("hostme.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        result = ssh.run_remote(make_server(), "echo hi")

    assert result.ok
    assert result.stdout == "ok"
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "ssh"
    assert "echo hi" in call_args


def test_run_remote_nonzero_exit_returns_result_without_raising():
    with patch("hostme.ssh.subprocess.run", return_value=fake_completed(returncode=1, stderr="boom")):
        result = ssh.run_remote(make_server(), "false")

    assert not result.ok
    assert result.returncode == 1
    assert result.stderr == "boom"


def test_run_remote_connection_failure_raises():
    with patch(
        "hostme.ssh.subprocess.run",
        return_value=fake_completed(returncode=255, stderr="Permission denied"),
    ), pytest.raises(ssh.SshError, match="Permission denied"):
        ssh.run_remote(make_server(), "echo hi")


def test_run_remote_timeout_raises():
    with patch(
        "hostme.ssh.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ssh", timeout=10),
    ), pytest.raises(ssh.SshError, match="не завершилась"):
        ssh.run_remote(make_server(), "echo hi", timeout=10)


def test_run_remote_missing_ssh_binary_raises():
    with (
        patch("hostme.ssh.subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(ssh.SshError, match="ssh"),
    ):
        ssh.run_remote(make_server(), "echo hi")


def test_rsync_to_success():
    with patch("hostme.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        result = ssh.rsync_to("/local/path", make_server(), "/remote/path")

    assert result.ok
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "rsync"
    assert "--delete" in call_args
    assert "/local/path/" in call_args
    assert "root@1.2.3.4:/remote/path/" in call_args


def test_rsync_to_without_delete():
    with patch("hostme.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        ssh.rsync_to("/local/path", make_server(), "/remote/path", delete=False)

    call_args = mock_run.call_args[0][0]
    assert "--delete" not in call_args


def test_rsync_to_failure_raises():
    with (
        patch(
            "hostme.ssh.subprocess.run",
            return_value=fake_completed(returncode=23, stderr="rsync error"),
        ),
        pytest.raises(ssh.SshError, match="rsync error"),
    ):
        ssh.rsync_to("/local/path", make_server(), "/remote/path")


def test_rsync_to_timeout_raises():
    with patch(
        "hostme.ssh.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="rsync", timeout=5),
    ), pytest.raises(ssh.SshError, match="не завершился"):
        ssh.rsync_to("/local/path", make_server(), "/remote/path", timeout=5)
