"""`hostme doctor`: проверки собственной настройки hostme — права и читаемость
реестров, наличие бинарей, нужных зарегистрированным серверам и target'ам, место
и политика локальных бэкапов target'ов, объявленные ssh-ключи. Ни одного обращения
к удалённому серверу: быстро и безопасно вызывать часто."""

from __future__ import annotations

import shutil
from pathlib import Path

from hostme import config
from hostme.core.errors import InvalidArguments
from hostme.core.services import target_backup_snapshots


def _check(name: str, status: str, detail: str) -> dict:
    # `ok` — по Standard, Health; `warn` — не провал (healthy остаётся true).
    return {"name": name, "ok": status != "fail", "status": status, "detail": detail}

def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())

def _human_size(size: float) -> str:
    for unit in ("Б", "КБ", "МБ"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ГБ"

def run_doctor() -> dict:
    """Проверки окружения/конфига без обращения к удалённым серверам (быстро,
    безопасно вызывать часто) — права на ~/.config/hostme/, читаемость
    реестров, наличие бинарей, нужных выбранным serverʼам/targetʼам."""
    checks: list[dict] = []

    if config.CONFIG_DIR.exists():
        mode = config.CONFIG_DIR.stat().st_mode & 0o777
        checks.append(
            _check(
                "config_dir",
                "ok" if mode == 0o700 else "warn",
                f"{config.CONFIG_DIR} (права {oct(mode)})" if mode != 0o700 else str(config.CONFIG_DIR),
            )
        )
    else:
        checks.append(
            _check("config_dir", "warn", f"{config.CONFIG_DIR} ещё не создан (будет создан при первой команде)")
        )

    try:
        servers = config.load_servers()
        checks.append(_check("servers_yaml", "ok", f"{len(servers)} серверов"))
    except Exception as exc:  # noqa: BLE001
        servers = []
        checks.append(_check("servers_yaml", "fail", str(exc)))

    try:
        targets = config.load_targets()
        checks.append(_check("targets_yaml", "ok", f"{len(targets)} target'ов"))
    except Exception as exc:  # noqa: BLE001
        targets = []
        checks.append(_check("targets_yaml", "fail", str(exc)))

    try:
        sites = config.load_sites()
        checks.append(_check("sites_yaml", "ok", f"{len(sites)} сайтов ({config.SITES_FILE})"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("sites_yaml", "fail", str(exc)))

    backups_check, backups_info = _target_backups_report()
    checks.append(backups_check)

    # Имена литералами — release.py сверяет их с [[tool.rb.external]] (стандарт §12).
    for binary, path in (("ssh", shutil.which("ssh")), ("rsync", shutil.which("rsync"))):
        checks.append(_check(binary, "ok" if path else "fail", path or f"`{binary}` не найден в PATH"))

    needs_lftp = any(t.connection in ("ftp", "sftp") for t in targets)
    if needs_lftp:
        path = shutil.which("lftp")
        checks.append(
            _check("lftp", "ok" if path else "fail", path or "`lftp` не найден в PATH (нужен для ftp/sftp target'ов)")
        )

    needs_sshpass = any(t.connection == "ssh" and t.password and not t.ssh_key for t in targets)
    if needs_sshpass:
        path = shutil.which("sshpass")
        checks.append(
            _check(
                "sshpass",
                "ok" if path else "fail",
                path or "`sshpass` не найден в PATH (нужен для password-based SSH target'ов)",
            )
        )

    for server in servers:
        key_path = Path(server.ssh_key).expanduser()
        checks.append(
            _check(
                f"ssh_key:{server.name}",
                "ok" if key_path.exists() else "warn",
                str(key_path) if key_path.exists() else f"{key_path} не найден локально",
            )
        )
    for target in targets:
        if target.ssh_key:
            key_path = Path(target.ssh_key).expanduser()
            checks.append(
                _check(
                    f"ssh_key:{target.name}",
                    "ok" if key_path.exists() else "warn",
                    str(key_path) if key_path.exists() else f"{key_path} не найден локально",
                )
            )

    ok = not any(c["status"] == "fail" for c in checks)
    return {"healthy": ok, "checks": checks, "data_dir": str(config.DATA_DIR), "target_backups": backups_info}

def _target_backups_report() -> tuple[dict, dict]:
    """(check для doctor, сводка для JSON: путь, байты, снепшоты, политика)."""
    backups_dir = config.TARGET_BACKUPS_DIR
    snapshots = (
        sum(len(target_backup_snapshots(t.name)) for t in backups_dir.iterdir() if t.is_dir())
        if backups_dir.is_dir()
        else 0
    )
    size = _dir_size(backups_dir) if backups_dir.is_dir() else 0
    info: dict = {"path": str(backups_dir), "bytes": size, "snapshots": snapshots}
    try:
        policy = config.load_backup_policy()
    except InvalidArguments as exc:
        return _check("target_backups", "fail", str(exc)), info
    info["policy"] = {"keep": policy.keep, "max_age_days": policy.max_age_days}
    policy_text = f"храним последние {policy.keep}" + (
        f", не старше {policy.max_age_days} дн." if policy.max_age_days else ""
    )
    detail = f"{backups_dir} — {_human_size(size)}, снепшотов: {snapshots}; {policy_text}"
    return _check("target_backups", "ok", detail), info
