import subprocess
from unittest.mock import patch

import pytest

from hostme.config import Server
from hostme.core.errors import InvalidArgumentsError
from hostme.providers import ssh


def make_server() -> Server:
    return Server(name="vps1", host="1.2.3.4", user="root", ssh_key="~/.ssh/id")


def fake_completed(returncode=0, stdout="ok", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_remote_success():
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        result = ssh.run_remote(make_server(), "echo hi")

    assert result.ok
    assert result.stdout == "ok"
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "ssh"
    assert "echo hi" in call_args


def test_run_remote_nonzero_exit_returns_result_without_raising():
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed(returncode=1, stderr="boom")):
        result = ssh.run_remote(make_server(), "false")

    assert not result.ok
    assert result.returncode == 1
    assert result.stderr == "boom"


def test_run_remote_connection_failure_raises():
    with (
        patch(
            "hostme.providers.ssh.subprocess.run",
            return_value=fake_completed(returncode=255, stderr="Permission denied"),
        ),
        pytest.raises(ssh.SshError, match="Permission denied"),
    ):
        ssh.run_remote(make_server(), "echo hi")


def test_run_remote_timeout_raises():
    with (
        patch(
            "hostme.providers.ssh.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ssh", timeout=10),
        ),
        pytest.raises(ssh.SshError, match="не завершилась"),
    ):
        ssh.run_remote(make_server(), "echo hi", timeout=10)


def test_run_remote_missing_ssh_binary_raises():
    with (
        patch("hostme.providers.ssh.subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(ssh.SshError, match="ssh"),
    ):
        ssh.run_remote(make_server(), "echo hi")


def test_rsync_to_success():
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        result = ssh.rsync_to("/local/path", make_server(), "/remote/path")

    assert result.ok
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "rsync"
    assert "--delete" in call_args
    assert "/local/path/" in call_args
    assert "root@1.2.3.4:/remote/path/" in call_args


def test_rsync_to_without_delete():
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        ssh.rsync_to("/local/path", make_server(), "/remote/path", delete=False)

    call_args = mock_run.call_args[0][0]
    assert "--delete" not in call_args


def test_rsync_to_failure_raises():
    with (
        patch(
            "hostme.providers.ssh.subprocess.run",
            return_value=fake_completed(returncode=23, stderr="rsync error"),
        ),
        pytest.raises(ssh.SshError, match="rsync error"),
    ):
        ssh.rsync_to("/local/path", make_server(), "/remote/path")


def test_rsync_to_timeout_raises():
    with (
        patch(
            "hostme.providers.ssh.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="rsync", timeout=5),
        ),
        pytest.raises(ssh.SshError, match="не завершился"),
    ):
        ssh.rsync_to("/local/path", make_server(), "/remote/path", timeout=5)


# --- rsync_to_target: Target-транспорт (connection=ssh), ключ или sshpass ---


def make_target(**overrides):
    from hostme.config import Target

    defaults = {"name": "ext1", "connection": "ssh", "host": "host.example", "user": "u12345", "remote_path": "/www"}
    defaults.update(overrides)
    return Target(**defaults)


def test_rsync_to_target_with_ssh_key_uses_key_not_sshpass():
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        ssh.rsync_to_target("/local/path", make_target(ssh_key="~/.ssh/id"))
    call = mock_run.call_args
    rsh = call[0][0][call[0][0].index("-e") + 1]
    assert "-i ~/.ssh/id" in rsh
    assert "sshpass" not in rsh
    assert call.kwargs.get("env") is None


def test_rsync_to_target_with_password_uses_sshpass_env_not_argv():
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        ssh.rsync_to_target("/local/path", make_target(password="s3cr3t"))
    call = mock_run.call_args
    args = call[0][0]
    rsh = args[args.index("-e") + 1]
    assert rsh.startswith("sshpass -e ssh")
    # пароль не должен светиться голым текстом ни в одном argv-элементе команды
    assert not any("s3cr3t" in a for a in args)
    assert call.kwargs["env"]["SSHPASS"] == "s3cr3t"


def test_rsync_to_target_without_key_or_password_raises():
    with pytest.raises(InvalidArgumentsError, match="ssh_key или password"):
        ssh.rsync_to_target("/local/path", make_target())


def test_rsync_to_target_keeps_relative_remote_path():
    # Реальный баг, пойманный вживую 2026-09-09 на Beget shared-хостинге:
    # путь к сайту там относительный от домашней директории аккаунта
    # ("top-ved.ru/public_html"), а не абсолютный — форсировать ведущий "/"
    # ломает деплой ("/top-ved.ru/public_html" на сервере просто не существует).
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        ssh.rsync_to_target("/local/path", make_target(remote_path="top-ved.ru/public_html", password="x"))
    destination = mock_run.call_args[0][0][-1]
    assert destination == "u12345@host.example:top-ved.ru/public_html/"
