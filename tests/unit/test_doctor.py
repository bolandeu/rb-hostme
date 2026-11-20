"""Тесты `hostme doctor`: проверки только локальные — ни один тест не должен
пускать запрос на удалённый сервер (иначе доктор станет медленным и шумным)."""

from typing import Any
from unittest.mock import patch

from rb_hostme.config import Target
from rb_hostme.core import doctor


def make_target(**overrides) -> Target:
    defaults: dict[str, Any] = {
        "name": "top-ved.ru",
        "connection": "ssh",
        "host": "host.example",
        "user": "u12345",
        "remote_path": "top-ved.ru/public_html",
        "password": "secret",
    }
    defaults.update(overrides)
    return Target(**defaults)


def test_doctor_reports_ok_when_binaries_and_config_present() -> None:
    with (
        patch("rb_hostme.core.doctor.config.CONFIG_DIR") as mock_dir,
        patch("rb_hostme.core.doctor.config.load_servers", return_value=[]),
        patch("rb_hostme.core.doctor.config.load_targets", return_value=[]),
        patch("rb_hostme.core.doctor.config.load_sites", return_value=[]),
        patch("rb_hostme.core.doctor.shutil.which", return_value="/usr/bin/tool"),
    ):
        mock_dir.exists.return_value = True
        mock_dir.stat.return_value.st_mode = 0o700
        result = doctor.run_doctor()
    assert result["healthy"] is True
    names = [c["name"] for c in result["checks"]]
    assert "ssh" in names
    assert "rsync" in names


def test_doctor_fails_when_required_binary_missing() -> None:
    with (
        patch("rb_hostme.core.doctor.config.CONFIG_DIR") as mock_dir,
        patch("rb_hostme.core.doctor.config.load_servers", return_value=[]),
        patch("rb_hostme.core.doctor.config.load_targets", return_value=[]),
        patch("rb_hostme.core.doctor.config.load_sites", return_value=[]),
        patch("rb_hostme.core.doctor.shutil.which", return_value=None),
    ):
        mock_dir.exists.return_value = True
        mock_dir.stat.return_value.st_mode = 0o700
        result = doctor.run_doctor()
    assert result["healthy"] is False


def test_doctor_requires_lftp_only_when_ftp_targets_registered() -> None:
    target = make_target(name="ext1", connection="sftp")
    with (
        patch("rb_hostme.core.doctor.config.CONFIG_DIR") as mock_dir,
        patch("rb_hostme.core.doctor.config.load_servers", return_value=[]),
        patch("rb_hostme.core.doctor.config.load_targets", return_value=[target]),
        patch("rb_hostme.core.doctor.config.load_sites", return_value=[]),
        patch("rb_hostme.core.doctor.shutil.which", side_effect=lambda b: None if b == "lftp" else "/usr/bin/" + b),
    ):
        mock_dir.exists.return_value = True
        mock_dir.stat.return_value.st_mode = 0o700
        result = doctor.run_doctor()
    checks_by_name = {c["name"]: c for c in result["checks"]}
    assert "lftp" in checks_by_name
    assert checks_by_name["lftp"]["status"] == "fail"
    assert result["healthy"] is False
