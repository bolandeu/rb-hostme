"""SSH и rsync через системные бинарники: единственное место, где hostme запускает `ssh`/`rsync`.

Почему через subprocess, а не paramiko — ADR 0002: так работают `~/.ssh/config`, агент и ключи
пользователя. Ошибки наружу уходят только как `ProviderError`. Соединение переиспользуется
через ControlMaster (см. `_CONTROL_DIR`), потому что поток коротких подключений подряд ловил
rate-limit/fail2ban на реальном сервере.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hostme.config import Server, Target
from hostme.core.errors import InvalidArguments, ProviderError

DEFAULT_TIMEOUT = 30
_log = logging.getLogger(__name__)
LONG_TIMEOUT = 300  # server init / webinoly install

# Много коротких SSH-подключений подряд (site_exists → create_site → enable_ssl →
# rsync → chown за один deploy) поймали rate-limit/fail2ban на реальном сервере
# (AGENTS.md). Фикс — переиспользовать одно соединение через
# ControlMaster/ControlPersist: первая команда поднимает мультиплексирующий сокет,
# все последующие (в т.ч. rsync через -e) переиспользуют его без нового хендшейка.
_CONTROL_DIR = Path.home() / ".cache" / "hostme" / "ssh-control"
_CONTROL_PERSIST = "60s"  # держим сокет после последней команды — не оставлять сессию навечно


class SshError(ProviderError):
    provider = "ssh"

    def __init__(self, message: str, result: RemoteResult | None = None) -> None:
        super().__init__(message)
        self.result = result


@dataclass
class RemoteResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _control_path(server: Server) -> str:
    # Короткий хэш вместо user@host напрямую — у sockaddr_un есть жёсткий лимит
    # длины пути (~104 байта на macOS), а домашняя директория может быть длинной.
    _CONTROL_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(f"{server.user}@{server.host}".encode()).hexdigest()[:16]
    return str(_CONTROL_DIR / key)


def _ssh_options(server: Server) -> list[str]:
    """Опции, общие для run_remote и rsync (-e) — оба должны бить в один и тот же
    ControlPath, чтобы реально шарить соединение, а не только каждый сам по себе."""
    return [
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={_control_path(server)}",
        "-o",
        f"ControlPersist={_CONTROL_PERSIST}",
    ]


def _ssh_base_args(server: Server) -> list[str]:
    return ["ssh", *_ssh_options(server), "-i", server.ssh_key, server.ssh_target]


def _ssh_command_string(server: Server) -> str:
    """Строка для rsync `-e` — rsync сам разбивает её по пробелам, без участия шелла."""
    return "ssh " + " ".join(_ssh_options(server)) + f" -i {server.ssh_key}"


def run_remote(server: Server, command: str, timeout: int = DEFAULT_TIMEOUT) -> RemoteResult:
    _log.debug("ssh %s: %s", server.ssh_target, command)
    try:
        proc = subprocess.run(
            [*_ssh_base_args(server), command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SshError(f"Команда на {server.name} не завершилась за {timeout}с: {command!r}") from exc
    except FileNotFoundError as exc:
        raise SshError("Команда `ssh` не найдена в системе") from exc

    result = RemoteResult(stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode)
    if proc.returncode == 255:
        raise SshError(
            f"Не удалось подключиться к {server.name} ({server.ssh_target}): "
            f"{proc.stderr.strip() or 'неизвестная ошибка SSH'}",
            result=result,
        )
    return result


def rsync_to(
    local_path: str,
    server: Server,
    remote_path: str,
    delete: bool = True,
    timeout: int = LONG_TIMEOUT,
) -> RemoteResult:
    local = local_path.rstrip("/") + "/"
    remote = remote_path.rstrip("/") + "/"
    args = [
        "rsync",
        "-az",
        *(["--delete"] if delete else []),
        "-e",
        _ssh_command_string(server),
        local,
        f"{server.ssh_target}:{remote}",
    ]
    _log.debug("%s", shlex.join(args))
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SshError(f"rsync на {server.name} не завершился за {timeout}с") from exc
    except FileNotFoundError as exc:
        raise SshError("Команда `rsync` не найдена в системе") from exc

    result = RemoteResult(stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode)
    if not result.ok:
        raise SshError(
            f"rsync на {server.name} завершился с ошибкой: {proc.stderr.strip()}",
            result=result,
        )
    return result


def _target_remote_path(target: Target) -> str:
    # НЕ форсировать ведущий "/" — у многих shared-хостингов (напр. Beget) путь
    # к сайту относительный от домашней директории аккаунта ("domain.ru/public_html",
    # без слэша), а не абсолютный ("/domain.ru/public_html" — такого пути там
    # просто нет). Уважаем то, что явно указано в remote_path, включая пусто/"/".
    return target.remote_path.rstrip("/") + "/" if target.remote_path.strip("/") else target.remote_path


def _target_ssh_transport(target: Target) -> tuple[str, dict[str, str] | None]:
    """rsh-команда для rsync `-e` + env под connection=ssh Target — общее и для
    заливки (deploy), и для скачивания (бэкап перед деплоем, см. cli.py).
    Ключ (как у Server) или пароль через sshpass — частый случай для сторонних
    хостингов, где SSH дают, но ключ туда не загрузить, только тот же логин/
    пароль, что и для FTP/панели."""
    if target.ssh_key:
        return (
            f"ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -i {target.ssh_key}",
            None,
        )
    if not target.password:
        raise InvalidArguments(f"Target {target.name!r}: для connection=ssh нужен ssh_key или password")

    # BatchMode=yes НЕЛЬЗЯ здесь (в отличие от ключевой ветки выше) — эта опция
    # отключает у ssh вообще любой запрос пароля, включая тот самый prompt,
    # который должен перехватывать sshpass; с ней password-auth падает с
    # "Permission denied" даже при верном пароле. Поймано вживую 2026-09-09
    # на реальном Beget-хостинге — ручной sshpass-тест без BatchMode прошёл,
    # а тот же вызов внутри rsync_to_target с BatchMode=yes — нет.
    rsh = "sshpass -e ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new"
    # Пароль через переменную окружения SSHPASS (sshpass -e), не флагом -p —
    # флаг был бы виден в `ps aux` всем локальным пользователям машины.
    env = {**os.environ, "SSHPASS": target.password}
    return rsh, env


def _run_target_rsync(args: list[str], target: Target, timeout: int, env: dict[str, str] | None) -> RemoteResult:
    _log.debug("%s", shlex.join(args))  # пароль сюда не попадает — он в env SSHPASS, не в argv
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SshError(f"rsync на {target.name} не завершился за {timeout}с") from exc
    except FileNotFoundError as exc:
        # sshpass отсутствующим тут не поймать: его запускает сам rsync как
        # дочерний процесс (через -e), а не Python напрямую — эта ветка бывает
        # только если не найден сам rsync.
        raise SshError("Команда `rsync` не найдена в системе") from exc

    result = RemoteResult(stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode)
    if not result.ok:
        hint = ""
        if target.password and not target.ssh_key and "sshpass" in result.stderr.lower():
            hint = " (похоже, не установлен sshpass — нужен для password-based SSH на Target)"
        raise SshError(
            f"rsync на {target.name} завершился с ошибкой: {proc.stderr.strip()}{hint}",
            result=result,
        )
    return result


def rsync_to_target(local_path: str, target: Target, timeout: int = LONG_TIMEOUT) -> RemoteResult:
    """Заливка на Target с connection=ssh — тот же rsync, что и у Server, но без
    ControlMaster (Target — обычно один rsync-вызов на деплой, не серия команд,
    как у Webinoly-пайплайна) и без ssh_key-only допущения (см. _target_ssh_transport)."""
    rsh, env = _target_ssh_transport(target)
    local = local_path.rstrip("/") + "/"
    destination = f"{target.user}@{target.host}:{_target_remote_path(target)}"
    args = ["rsync", "-az", "--delete", "-e", rsh, local, destination]
    return _run_target_rsync(args, target, timeout, env)


def rsync_from_target(target: Target, local_dir: str, timeout: int = LONG_TIMEOUT) -> RemoteResult:
    """Скачивает текущее содержимое remote_path в local_dir — бэкап перед
    деплоем на Target (см. cli._backup_target_before_deploy), не rollback как
    таковой. Без --delete: local_dir — свежая пустая директория под конкретный
    таймстамп, синхронизировать с ней нечего, только заполнить."""
    rsh, env = _target_ssh_transport(target)
    local = local_dir.rstrip("/") + "/"
    source = f"{target.user}@{target.host}:{_target_remote_path(target)}"
    args = ["rsync", "-az", "-e", rsh, source, local]
    return _run_target_rsync(args, target, timeout, env)


# --- health check для `hostme auth status --check` (стандарт §8) --------------------


def _auth_probe(args: list[str], env: dict[str, str] | None, timeout: float) -> tuple[str, str | None]:
    """Один `ssh ... true` — дешёвая read-only проверка доступа. (status, message)."""
    _log.debug("%s", shlex.join(args))
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env, check=False)
    except subprocess.TimeoutExpired:
        return "unreachable", f"нет ответа за {timeout:.0f}с"
    except FileNotFoundError as exc:
        return "unreachable", f"`{exc.filename or args[0]}` не найден в PATH"
    if proc.returncode == 0:
        return "ok", None
    stderr = proc.stderr.strip()
    if "permission denied" in stderr.lower() or "authentication failed" in stderr.lower():
        return "invalid", stderr.splitlines()[-1] if stderr else "доступ отклонён"
    return "unreachable", (stderr.splitlines()[-1] if stderr else f"ssh завершился с кодом {proc.returncode}")


def check_server(server: Server, timeout: float) -> tuple[str, str | None]:
    """Пускает ли сервер по ключу (без ControlMaster — проверяем сам ключ, а не живой сокет)."""
    args = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={int(timeout)}",
        "-o",
        "ControlPath=none",
        "-i",
        server.ssh_key,
        server.ssh_target,
        "true",
    ]
    return _auth_probe(args, None, timeout)


def check_target(target: Target, timeout: float) -> tuple[str, str | None]:
    """ssh-target: тот же транспорт, что у rsync (ключ или sshpass), команда `true`."""
    rsh, env = _target_ssh_transport(target)
    return _auth_probe([*shlex.split(rsh), f"{target.user}@{target.host}", "true"], env, timeout)
