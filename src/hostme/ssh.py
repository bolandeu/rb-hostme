from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hostme.config import Server
from hostme.errors import HostmeError

DEFAULT_TIMEOUT = 30
LONG_TIMEOUT = 300  # server init / webinoly install

# Много коротких SSH-подключений подряд (site_exists → create_site → enable_ssl →
# rsync → chown за один deploy) поймали rate-limit/fail2ban на реальном сервере
# (AGENTS.md, TODO.md 1.2). Фикс — переиспользовать одно соединение через
# ControlMaster/ControlPersist: первая команда поднимает мультиплексирующий сокет,
# все последующие (в т.ч. rsync через -e) переиспользуют его без нового хендшейка.
_CONTROL_DIR = Path.home() / ".cache" / "hostme" / "ssh-control"
_CONTROL_PERSIST = "60s"  # держим сокет после последней команды — не оставлять сессию навечно


class SshError(HostmeError):
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
    try:
        proc = subprocess.run(
            [*_ssh_base_args(server), command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SshError(
            f"Команда на {server.name} не завершилась за {timeout}с: {command!r}"
        ) from exc
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
