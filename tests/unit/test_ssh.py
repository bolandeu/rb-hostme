import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hostme.config import Server, Target
from hostme.core.errors import InvalidArguments
from hostme.providers import ssh


def make_server() -> Server:
    return Server(name="vps1", host="1.2.3.4", user="root", ssh_key="~/.ssh/id")


def fake_completed(returncode=0, stdout="ok", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def calls_of(mock_run, program: str) -> list[list[str]]:
    """argv всех вызовов subprocess.run за одной программой: сначала rsync в
    staging, за ним ssh со скриптом замены."""
    return [call[0][0] for call in mock_run.call_args_list if call[0][0][0] == program]


# ssh и rsync на PATH вместо сети: ssh выполняет свой скрипт в каталоге хоста,
# rsync копирует файлы с сохранением времени — тест видит настоящую раскладку
# удалённой стороны и записанный argv каждого вызова.
_FAKE_TOOL = """
import json, os, shutil, subprocess, sys
from pathlib import Path

log = Path(os.environ["HOSTME_FAKE_LOG"])
calls = json.loads(log.read_text()) if log.exists() else []
program = Path(sys.argv[0]).name
seen = sum(1 for c in calls if c["program"] == program) + 1
calls.append({"program": program, "argv": sys.argv[1:], "sshpass": os.environ.get("SSHPASS")})
log.write_text(json.dumps(calls))

code = json.loads(os.environ.get("HOSTME_FAKE_FAIL", "{}")).get(f"{program}:{seen}", 0)
remote = Path(os.environ["HOSTME_FAKE_REMOTE"])

if program == "ssh":
    sys.exit(subprocess.run(["/bin/sh", "-c", sys.argv[-1]], cwd=remote).returncode)

if os.environ.get("HOSTME_FAKE_RSYNC_EMPTY"):
    sys.exit(code)
destination = remote / sys.argv[-1].split(":", 1)[1]
destination.mkdir(parents=True, exist_ok=True)
entries = sorted(Path(sys.argv[-2]).iterdir())
for entry in entries[:1] if code else entries:
    if entry.is_dir():
        shutil.copytree(entry, destination / entry.name)
    else:
        shutil.copy2(entry, destination / entry.name)
sys.exit(code)
"""


def fake_remote(tmp_path: Path, monkeypatch, remote_path: str = "srv/www", **overrides) -> tuple[Path, Target]:
    """Каталог «хостинга» + Target к нему: ssh и rsync на PATH работают с ним же."""
    remote = tmp_path / "remote"
    remote.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("rsync", "ssh"):
        tool = bin_dir / name
        tool.write_text(f"#!{sys.executable}\n{_FAKE_TOOL}")
        tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOSTME_FAKE_LOG", str(tmp_path / "calls.json"))
    monkeypatch.setenv("HOSTME_FAKE_REMOTE", str(remote))
    return remote, make_target(remote_path=remote_path, ssh_key="~/.ssh/id", **overrides)


def recorded(tmp_path: Path) -> list[dict]:
    return json.loads((tmp_path / "calls.json").read_text())


def local_site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>new</h1>")
    (site / "style.css").write_text("body{}")
    return site


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

    defaults: dict = {
        "name": "ext1",
        "connection": "ssh",
        "host": "host.example",
        "user": "u12345",
        "remote_path": "/www",
    }
    defaults.update(overrides)
    return Target(**defaults)


def test_rsync_to_target_with_ssh_key_uses_key_not_sshpass():
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        ssh.rsync_to_target("/local/path", make_target(ssh_key="~/.ssh/id"))
    rsync = calls_of(mock_run, "rsync")[0]
    rsh = rsync[rsync.index("-e") + 1]
    assert "-i ~/.ssh/id" in rsh
    assert "sshpass" not in rsh
    assert all(call.kwargs.get("env") is None for call in mock_run.call_args_list)


def test_rsync_to_target_with_password_uses_sshpass_env_not_argv():
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        ssh.rsync_to_target("/local/path", make_target(password="s3cr3t"))
    rsync = calls_of(mock_run, "rsync")[0]
    assert rsync[rsync.index("-e") + 1].startswith("sshpass -e ssh")
    # пароль не должен светиться голым текстом ни в одном argv-элементе команды
    assert not any("s3cr3t" in arg for call in mock_run.call_args_list for arg in call[0][0])
    assert mock_run.call_args_list[0].kwargs["env"]["SSHPASS"] == "s3cr3t"


def test_rsync_to_target_without_key_or_password_raises():
    with pytest.raises(InvalidArguments, match="ssh_key или password"):
        ssh.rsync_to_target("/local/path", make_target())


def test_rsync_to_target_refuses_root_remote_path():
    # В корень staging не переименовать: менять местами с живым каталогом нечего.
    with pytest.raises(InvalidArguments, match="нужен каталог сайта"):
        ssh.rsync_to_target("/local/path", make_target(remote_path="/", ssh_key="~/.ssh/id"))


# --- заливка целиком или никак: staging + замена переименованием ---


def test_rsync_to_target_uploads_into_staging_and_keeps_file_times(tmp_path, monkeypatch):
    remote, target = fake_remote(tmp_path, monkeypatch)
    site = local_site(tmp_path)
    built_at = 1_600_000_000
    for built in site.iterdir():
        os.utime(built, (built_at, built_at))

    ssh.rsync_to_target(str(site), target)

    rsync_call = recorded(tmp_path)[0]
    assert rsync_call["program"] == "rsync"
    flags = {char for arg in rsync_call["argv"] if arg.startswith("-") and not arg.startswith("--") for char in arg[1:]}
    assert "a" in flags  # -a несёт -t: время файла переживает заливку
    assert rsync_call["argv"][-1].startswith("u12345@host.example:srv/www.hostme-staging-")
    served = remote / "srv" / "www" / "index.html"
    assert served.read_text() == "<h1>new</h1>"
    assert int(served.stat().st_mtime) == built_at


def test_rsync_to_target_first_deploy_creates_live_and_drops_staging(tmp_path, monkeypatch):
    remote, target = fake_remote(tmp_path, monkeypatch)

    ssh.rsync_to_target(str(local_site(tmp_path)), target)

    parent = remote / "srv"
    assert [entry.name for entry in parent.iterdir()] == ["www"]
    assert sorted(entry.name for entry in (parent / "www").iterdir()) == ["index.html", "style.css"]


def test_rsync_to_target_failed_upload_leaves_previous_site(tmp_path, monkeypatch):
    remote, target = fake_remote(tmp_path, monkeypatch)
    live = remote / "srv" / "www"
    live.mkdir(parents=True)
    (live / "index.html").write_text("<h1>old</h1>")
    monkeypatch.setenv("HOSTME_FAKE_FAIL", json.dumps({"rsync:1": 23}))

    with pytest.raises(ssh.SshError, match="rsync на ext1"):
        ssh.rsync_to_target(str(local_site(tmp_path)), target)

    assert [entry.name for entry in live.iterdir()] == ["index.html"]
    assert (live / "index.html").read_text() == "<h1>old</h1>"
    assert not any(call["program"] == "ssh" for call in recorded(tmp_path))  # замены не было


def test_rsync_to_target_restores_live_when_staging_cannot_be_renamed(tmp_path, monkeypatch):
    remote, target = fake_remote(tmp_path, monkeypatch)
    live = remote / "srv" / "www"
    live.mkdir(parents=True)
    (live / "index.html").write_text("<h1>old</h1>")
    # rsync отрапортовал успех, но staging не создан: второй mv не удастся —
    # старую копию обязано вернуть на место, иначе посетитель останется без сайта.
    monkeypatch.setenv("HOSTME_FAKE_RSYNC_EMPTY", "1")

    with pytest.raises(ssh.SshError, match="завершился с ошибкой"):
        ssh.rsync_to_target(str(local_site(tmp_path)), target)

    assert [entry.name for entry in live.iterdir()] == ["index.html"]
    assert (live / "index.html").read_text() == "<h1>old</h1>"


def test_rsync_to_target_removes_stale_staging_and_old_of_earlier_runs(tmp_path, monkeypatch):
    remote, target = fake_remote(tmp_path, monkeypatch)
    parent = remote / "srv"
    (parent / "www.hostme-staging-20200101000000").mkdir(parents=True)
    (parent / "www.hostme-old-20200101000000").mkdir()

    ssh.rsync_to_target(str(local_site(tmp_path)), target)

    assert [entry.name for entry in parent.iterdir()] == ["www"]


def test_rsync_to_target_keeps_relative_remote_path():
    # Реальный баг, пойманный вживую 2026-09-09 на Beget shared-хостинге:
    # путь к сайту там относительный от домашней директории аккаунта
    # ("top-ved.ru/public_html"), а не абсолютный — форсировать ведущий "/"
    # ломает деплой ("/top-ved.ru/public_html" на сервере просто не существует).
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed()) as mock_run:
        ssh.rsync_to_target("/local/path", make_target(remote_path="top-ved.ru/public_html", password="x"))
    destination = calls_of(mock_run, "rsync")[0][-1]
    assert destination.startswith("u12345@host.example:top-ved.ru/public_html.hostme-staging-")
    command = mock_run.call_args_list[-1][0][0][-1]  # пароль — sshpass, поэтому последний вызов
    assert "mv top-ved.ru/public_html top-ved.ru/public_html.hostme-old-" in command
    assert "mv top-ved.ru/public_html.hostme-staging-" in command
    assert " /top-ved.ru" not in command


# --- health check для auth status --check ---


def test_check_server_ok_and_invalid():
    from hostme.providers.ssh import check_server

    server = Server(name="s", host="h", user="root", ssh_key="~/.ssh/id")
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed(0)) as run:
        assert check_server(server, 10) == ("ok", None)
    args = run.call_args.args[0]
    assert args[0] == "ssh" and args[-1] == "true" and "ControlPath=none" in args
    denied = fake_completed(255, stderr="root@h: Permission denied (publickey).")
    with patch("hostme.providers.ssh.subprocess.run", return_value=denied):
        assert check_server(server, 10)[0] == "invalid"
    with patch("hostme.providers.ssh.subprocess.run", side_effect=subprocess.TimeoutExpired("ssh", 10)):
        assert check_server(server, 10)[0] == "unreachable"


def test_check_target_password_uses_sshpass_env():
    from hostme.providers.ssh import check_target

    target = Target(name="t", connection="ssh", host="h", user="u", password="pw")
    with patch("hostme.providers.ssh.subprocess.run", return_value=fake_completed(0)) as run:
        assert check_target(target, 10) == ("ok", None)
    assert run.call_args.args[0][:3] == ["sshpass", "-e", "ssh"]
    assert "pw" not in run.call_args.args[0]
    assert run.call_args.kwargs["env"]["SSHPASS"] == "pw"
