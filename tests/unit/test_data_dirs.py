from datetime import UTC, datetime, timedelta

import pytest

from rb_hostme import config
from rb_hostme.core import doctor, services
from rb_hostme.core.errors import InvalidArguments


def _snapshot(target: str, ts: datetime) -> None:
    path = config.TARGET_BACKUPS_DIR / target / ts.strftime("%Y%m%d%H%M%S")
    path.mkdir(parents=True)
    (path / "index.html").write_text("x" * 10)


def _write_settings(text: str) -> None:
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config.SETTINGS_FILE.write_text(text)


# --- migration -------------------------------------------------------------


def test_migrate_moves_sites_includes_and_backups():
    legacy = config.CONFIG_DIR
    (legacy / "sites.d").mkdir(parents=True)
    (legacy / "sites.yaml").write_text("include:\n  - sites.d/clients.yaml\nsites: []\n")
    (legacy / "sites.d" / "clients.yaml").write_text("sites: []\n")
    (legacy / "servers.yaml").write_text("servers: []\n")
    (legacy / "target-backups" / "ext1" / "20260101000000").mkdir(parents=True)

    moved = config.migrate_legacy_data()

    assert len(moved) == 3
    assert config.SITES_FILE.exists()
    assert (config.DATA_DIR / "sites.d" / "clients.yaml").exists()
    assert (config.TARGET_BACKUPS_DIR / "ext1" / "20260101000000").is_dir()
    assert not (legacy / "sites.yaml").exists()
    assert not (legacy / "sites.d").exists()
    assert not (legacy / "target-backups").exists()
    assert (legacy / "servers.yaml").exists()
    assert config.migrate_legacy_data() == []


def test_migrate_does_not_overwrite_existing_data():
    (config.CONFIG_DIR / "target-backups" / "ext1" / "20260101000000").mkdir(parents=True)
    (config.CONFIG_DIR / "sites.yaml").write_text("sites: []\n")
    config.DATA_DIR.mkdir(parents=True)
    config.SITES_FILE.write_text("sites: [new]\n")
    (config.TARGET_BACKUPS_DIR / "ext1" / "20260101000000").mkdir(parents=True)

    moved = config.migrate_legacy_data()

    assert config.SITES_FILE.read_text() == "sites: [new]\n"
    assert (config.CONFIG_DIR / "sites.yaml").exists()
    assert (config.CONFIG_DIR / "target-backups" / "ext1" / "20260101000000").is_dir()
    assert moved and "частично" in moved[0]


def test_migrate_nothing_to_do():
    assert config.migrate_legacy_data() == []


# --- policy ------------------------------------------------------------------


def test_backup_policy_defaults_without_settings():
    assert config.load_backup_policy() == config.BackupPolicy(keep=5, max_age_days=None)


def test_backup_policy_from_settings():
    _write_settings("target_backups:\n  keep: 3\n  max_age_days: 14\n")
    assert config.load_backup_policy() == config.BackupPolicy(keep=3, max_age_days=14)


@pytest.mark.parametrize("body", ["keep: 0", "keep: many", "max_age_days: -1"])
def test_backup_policy_rejects_bad_values(body):
    _write_settings(f"target_backups:\n  {body}\n")
    with pytest.raises(InvalidArguments):
        config.load_backup_policy()


def test_prune_keeps_last_n():
    base = datetime.now(UTC)
    for i in range(4):
        _snapshot("ext1", base - timedelta(minutes=i))

    removed = services._prune_target_backups("ext1", config.BackupPolicy(keep=2))

    assert len(removed) == 2
    assert len(services.target_backup_snapshots("ext1")) == 2


def test_prune_by_age_but_never_the_newest():
    now = datetime.now(UTC)
    _snapshot("ext1", now - timedelta(days=40))
    _snapshot("ext1", now - timedelta(days=20))
    _snapshot("ext1", now - timedelta(days=1))
    _snapshot("ext2", now - timedelta(days=100))

    policy = config.BackupPolicy(keep=10, max_age_days=7)
    services._prune_target_backups("ext1", policy)
    services._prune_target_backups("ext2", policy)

    assert [p.name for p in services.target_backup_snapshots("ext1")] == [
        (now - timedelta(days=1)).strftime("%Y%m%d%H%M%S")
    ]
    assert len(services.target_backup_snapshots("ext2")) == 1


def test_prune_reads_policy_from_settings():
    _write_settings("target_backups:\n  keep: 1\n")
    base = datetime.now(UTC)
    for i in range(3):
        _snapshot("ext1", base - timedelta(minutes=i))

    services._prune_target_backups("ext1")

    assert len(services.target_backup_snapshots("ext1")) == 1


# --- doctor ------------------------------------------------------------------


def test_doctor_reports_backups_path_and_size():
    _snapshot("ext1", datetime.now(UTC))

    report = doctor.run_doctor()

    check = next(c for c in report["checks"] if c["name"] == "target_backups")
    assert check["status"] == "ok"
    assert str(config.TARGET_BACKUPS_DIR) in check["detail"]
    assert report["target_backups"]["bytes"] == 10
    assert report["target_backups"]["snapshots"] == 1
    assert report["target_backups"]["policy"] == {"keep": 5, "max_age_days": None}


def test_doctor_fails_on_bad_policy():
    _write_settings("target_backups:\n  keep: 0\n")

    report = doctor.run_doctor()

    check = next(c for c in report["checks"] if c["name"] == "target_backups")
    assert check["status"] == "fail"
    assert report["healthy"] is False


# --- isolation guard -----------------------------------------------------------


def test_tests_never_touch_real_user_dirs(tmp_path_factory):
    """Страховка: conftest.isolated_dirs уводит все пути hostme во временный каталог,
    иначе тесты prune/миграции удаляли бы настоящие бэкапы и sites.yaml."""
    from rb_hostme.providers import ssh

    tmp_root = tmp_path_factory.getbasetemp()
    paths = [
        config.CONFIG_DIR,
        config.SERVERS_FILE,
        config.SETTINGS_FILE,
        config.DATA_DIR,
        config.SITES_FILE,
        config.TARGET_BACKUPS_DIR,
        ssh._CONTROL_DIR,
    ]
    for path in paths:
        assert path.is_relative_to(tmp_root), path
