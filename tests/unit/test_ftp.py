import subprocess
from unittest.mock import patch

import pytest

from hostme import ftp
from hostme.config import Target
from hostme.errors import HostmeError


def make_target(**overrides):
    defaults = {
        "name": "ext1",
        "connection": "sftp",
        "host": "host.example",
        "user": "u12345",
        "remote_path": "/www",
        "password": "s3cr3t",
    }
    defaults.update(overrides)
    return Target(**defaults)


def fake_completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_mirror_to_passes_credentials_via_stdin_not_argv():
    with patch("hostme.ftp.subprocess.run", return_value=fake_completed()) as mock_run:
        ftp.mirror_to("/local/path", make_target())
    call = mock_run.call_args
    # argv — только сама команда lftp, без -u/пароля голым текстом
    assert call[0][0] == ["lftp"]
    script = call.kwargs["input"]
    assert "s3cr3t" in script  # пароль реально передан...
    assert "open -u u12345,s3cr3t sftp://host.example" in script  # ...именно в скрипте на stdin


def test_mirror_to_builds_reverse_delete_mirror_command():
    with patch("hostme.ftp.subprocess.run", return_value=fake_completed()) as mock_run:
        ftp.mirror_to("/local/path", make_target())
    script = mock_run.call_args.kwargs["input"]
    assert "mirror --reverse --delete" in script
    assert '"/local/path/"' in script
    assert '"/www"' in script


def test_mirror_to_without_password_raises():
    with pytest.raises(HostmeError, match="password"):
        ftp.mirror_to("/local/path", make_target(password=None))


def test_mirror_to_raises_on_failure():
    with (
        patch("hostme.ftp.subprocess.run", return_value=fake_completed(returncode=1, stderr="Login failed")),
        pytest.raises(ftp.FtpError, match="Login failed"),
    ):
        ftp.mirror_to("/local/path", make_target())


def test_mirror_to_timeout_raises():
    with (
        patch("hostme.ftp.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="lftp", timeout=5)),
        pytest.raises(ftp.FtpError, match="не завершился"),
    ):
        ftp.mirror_to("/local/path", make_target(), timeout=5)


def test_mirror_to_missing_lftp_raises():
    with (
        patch("hostme.ftp.subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(ftp.FtpError, match="lftp"),
    ):
        ftp.mirror_to("/local/path", make_target())
