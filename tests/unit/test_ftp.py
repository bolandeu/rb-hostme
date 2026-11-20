import os
import subprocess
import sys
from typing import Any
from unittest.mock import patch

import pytest

from rb_hostme.config import Target
from rb_hostme.core.errors import CliError
from rb_hostme.providers import ftp

# Подставной lftp на PATH: читает сценарий со stdin, пишет его в лог и делает
# то же, что сделал бы lftp — но в локальной папке FAKE_LFTP_ROOT. FAKE_LFTP_FAIL_AT
# роняет N-ю изменяющую команду, чтобы проверить «целиком или никак».
FAKE_LFTP = """#!{python}
import os
import shutil
import sys
from pathlib import Path

root = Path(os.environ["FAKE_LFTP_ROOT"])
log = Path(os.environ["FAKE_LFTP_LOG"])
counter = log.with_suffix(".steps")
fail_at = int(os.environ.get("FAKE_LFTP_FAIL_AT", "0"))

script = sys.stdin.read()
log.write_text((log.read_text() if log.exists() else "") + script)

def unquote(token):
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        token = token[1:-1]
    return token.replace('\\\\"', '"').replace("\\\\\\\\", "\\\\")

def remote(argument):
    return root / unquote(argument).lstrip("/")

# Счётчик изменяющих команд общий на весь прогон, а не на одно соединение.
steps = int(counter.read_text()) if counter.exists() else 0
for raw in script.splitlines():
    line = raw.strip()
    if not line or line.split()[0] in ("set", "open", "quit", "cls"):
        continue
    verb, _, rest = line.partition(" ")
    operands = [token for token in rest.split(" ") if not token.startswith("-")]
    force = "-f" in rest.split(" ")
    if verb == "mirror":
        local, staging = Path(unquote(operands[0])), remote(operands[1])
        def action(local=local, staging=staging):
            shutil.copytree(local, staging, dirs_exist_ok=True, copy_function=shutil.copy2)
    elif verb == "mv":
        source, target = remote(operands[0]), remote(operands[1])
        def action(source=source, target=target):
            source.rename(target)
    elif verb == "rm":
        victim = remote(operands[-1])
        def action(victim=victim, force=force):
            if victim.exists():
                shutil.rmtree(victim)
            elif not force:
                raise FileNotFoundError(victim)
    else:
        continue
    steps += 1
    counter.write_text(str(steps))
    if steps == fail_at:
        print(f"fake lftp: падение на команде {steps}", file=sys.stderr)
        sys.exit(1)
    action()
"""


def make_target(**overrides) -> Target:
    defaults: dict[str, Any] = {
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


@pytest.fixture
def fake_lftp(tmp_path, monkeypatch):
    """Ставит подставной lftp первым в PATH; возвращает (папка «сервера», лог сценариев)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "lftp"
    fake.write_text(FAKE_LFTP.replace("{python}", sys.executable))
    fake.chmod(0o755)
    remote_root = tmp_path / "remote"
    remote_root.mkdir()
    log = tmp_path / "lftp.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LFTP_ROOT", str(remote_root))
    monkeypatch.setenv("FAKE_LFTP_LOG", str(log))
    return remote_root, log


@pytest.fixture
def site_dir(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>new</h1>")
    (site / "style.css").write_text("body{}")
    return site


def test_mirror_to_passes_credentials_via_stdin_not_argv():
    with patch("rb_hostme.providers.ftp.subprocess.run", return_value=fake_completed()) as mock_run:
        ftp.mirror_to("/local/path", make_target())
    call = mock_run.call_args
    # argv — только сама команда lftp, без -u/пароля голым текстом
    assert call[0][0] == ["lftp"]
    script = call.kwargs["input"]
    assert "s3cr3t" in script  # пароль реально передан...
    assert "open -u u12345,s3cr3t sftp://host.example" in script  # ...именно в скрипте на stdin


def test_mirror_to_uploads_into_staging_not_into_remote_path():
    with patch("rb_hostme.providers.ftp.subprocess.run", return_value=fake_completed()) as mock_run:
        ftp.mirror_to("/local/path", make_target())
    upload = mock_run.call_args_list[0].kwargs["input"]
    assert "mirror --reverse --delete" in upload
    assert '"/local/path/" "/www.hostme-staging"' in upload


def test_mirror_to_script_keeps_file_times():
    with patch("rb_hostme.providers.ftp.subprocess.run", return_value=fake_completed()) as mock_run:
        ftp.mirror_to("/local/path", make_target())
    script = mock_run.call_args.kwargs["input"]
    assert "set ftp:use-mdtm yes" in script
    assert "set ftp:use-site-utime2 yes" in script
    assert "--ignore-time" not in script


def test_mirror_to_without_password_raises():
    with pytest.raises(CliError, match="password"):
        ftp.mirror_to("/local/path", make_target(password=None))


def test_mirror_to_refuses_account_root_as_remote_path():
    with pytest.raises(CliError, match="remote_path"):
        ftp.mirror_to("/local/path", make_target(remote_path="/"))


def test_mirror_to_raises_on_failure():
    with (
        patch(
            "rb_hostme.providers.ftp.subprocess.run", return_value=fake_completed(returncode=1, stderr="Login failed")
        ),
        pytest.raises(ftp.FtpError, match="Login failed"),
    ):
        ftp.mirror_to("/local/path", make_target())


def test_mirror_to_timeout_raises():
    with (
        patch("rb_hostme.providers.ftp.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="lftp", timeout=5)),
        pytest.raises(ftp.FtpError, match="не завершился"),
    ):
        ftp.mirror_to("/local/path", make_target(), timeout=5)


def test_mirror_to_missing_lftp_raises():
    with (
        patch("rb_hostme.providers.ftp.subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(ftp.FtpError, match="lftp"),
    ):
        ftp.mirror_to("/local/path", make_target())


@pytest.mark.parametrize("connection", ["ftp", "sftp"])
def test_mirror_to_swap_leaves_only_new_files_and_removes_stale_dirs(fake_lftp, site_dir, connection):
    remote_root, _log = fake_lftp
    live = remote_root / "www"
    (live / "index.html").parent.mkdir(parents=True)
    (live / "index.html").write_text("<h1>old</h1>")
    (live / "legacy.html").write_text("gone")
    (remote_root / "www.hostme-staging").mkdir()  # мусор прошлой неудачной заливки
    (remote_root / "www.hostme-staging" / "half.html").write_text("half")
    (remote_root / "www.hostme-old").mkdir()

    ftp.mirror_to(str(site_dir), make_target(connection=connection))

    assert (live / "index.html").read_text() == "<h1>new</h1>"
    assert (live / "style.css").read_text() == "body{}"
    assert not (live / "legacy.html").exists()
    assert sorted(p.name for p in remote_root.iterdir()) == ["www"]


def test_mirror_to_first_deploy_needs_no_live_directory(fake_lftp, site_dir):
    remote_root, _log = fake_lftp

    ftp.mirror_to(str(site_dir), make_target())

    assert (remote_root / "www" / "index.html").read_text() == "<h1>new</h1>"
    assert sorted(p.name for p in remote_root.iterdir()) == ["www"]


def test_mirror_to_failed_upload_keeps_previous_files(fake_lftp, site_dir, monkeypatch):
    remote_root, _log = fake_lftp
    live = remote_root / "www"
    live.mkdir()
    (live / "index.html").write_text("<h1>old</h1>")
    monkeypatch.setenv("FAKE_LFTP_FAIL_AT", "3")  # 3-я изменяющая команда — сама заливка

    with pytest.raises(ftp.FtpError):
        ftp.mirror_to(str(site_dir), make_target())

    assert (live / "index.html").read_text() == "<h1>old</h1>"
    assert not (live / "style.css").exists()


def test_mirror_to_failed_swap_returns_previous_files_and_raises(fake_lftp, site_dir, monkeypatch):
    remote_root, _log = fake_lftp
    live = remote_root / "www"
    live.mkdir()
    (live / "index.html").write_text("<h1>old</h1>")
    monkeypatch.setenv("FAKE_LFTP_FAIL_AT", "5")  # 5-я — rename staging -> live

    with pytest.raises(ftp.FtpError, match="подменить"):
        ftp.mirror_to(str(site_dir), make_target())

    assert (live / "index.html").read_text() == "<h1>old</h1>"
    assert not (live / "style.css").exists()


def test_check_target_maps_login_failure_to_invalid_and_keeps_password_off_argv():
    failed = fake_completed(1, stderr="ls: Login failed: 530 Login incorrect.")
    with patch("rb_hostme.providers.ftp.subprocess.run", return_value=failed) as mock_run:
        assert ftp.check_target(make_target(), 10)[0] == "invalid"
    assert mock_run.call_args.args[0] == ["lftp"]
    assert "cls" in mock_run.call_args.kwargs["input"]
    with patch("rb_hostme.providers.ftp.subprocess.run", return_value=fake_completed(0)):
        assert ftp.check_target(make_target(), 10) == ("ok", None)
    with patch("rb_hostme.providers.ftp.subprocess.run", side_effect=subprocess.TimeoutExpired("lftp", 10)):
        assert ftp.check_target(make_target(), 10)[0] == "unreachable"
