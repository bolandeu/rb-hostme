from __future__ import annotations

import subprocess
from dataclasses import dataclass

from hostme.config import Server

DEFAULT_TIMEOUT = 30
LONG_TIMEOUT = 300  # server init / webinoly install


class SshError(Exception):
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


def _ssh_base_args(server: Server) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-i",
        server.ssh_key,
        server.ssh_target,
    ]


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
        f"ssh -o BatchMode=yes -o ConnectTimeout=10 -i {server.ssh_key}",
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
