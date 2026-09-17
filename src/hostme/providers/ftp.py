from __future__ import annotations

import subprocess

from hostme.config import Target
from hostme.core.errors import InvalidArgumentsError, ProviderError

DEFAULT_TIMEOUT = 300


class FtpError(ProviderError):
    provider = "lftp"


def _lftp_quote(value: str) -> str:
    """lftp разбирает команды по своим (shell-подобным) правилам — двойные кавычки
    + экранирование `\\`/`"` внутри, а не Python repr()."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _remote_path(target: Target) -> str:
    # НЕ форсировать ведущий "/" — у многих shared-хостингов путь к сайту
    # относительный от домашней директории аккаунта (напр. "domain.ru/public_html"
    # у Beget), а не абсолютный. Уважаем то, что указано в remote_path как есть.
    return target.remote_path.rstrip("/") or "/"


def _run_lftp(script: str, target: Target, timeout: int) -> None:
    try:
        proc = subprocess.run(["lftp"], input=script, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise FtpError(f"lftp на {target.name} не завершился за {timeout}с") from exc
    except FileNotFoundError as exc:
        raise FtpError("Команда `lftp` не найдена в системе (нужна для ftp/sftp-таргетов)") from exc

    if proc.returncode != 0:
        raise FtpError(f"lftp на {target.name} завершился с ошибкой: {(proc.stderr or proc.stdout).strip()}")


def _open_script(target: Target) -> str:
    # lftp `-u user,pass` бьёт по первой запятой — запятая в пароле сломает парсинг,
    # известное ограничение (редкий случай, не стали городить экранирование под это).
    return (
        "set sftp:auto-confirm yes\n"
        "set ssl:verify-certificate no\n"
        f"open -u {target.user},{target.password} {target.connection}://{target.host}\n"
    )


def mirror_to(local_path: str, target: Target, timeout: int = DEFAULT_TIMEOUT) -> None:
    """Заливка на Target с connection=ftp/sftp через lftp (та же `mirror --reverse
    --delete`, что уже используется в существующих Makefile-пайплайнах для таких
    хостингов — не изобретаем новый подход, переиспользуем проверенный).

    Логин/пароль идут в lftp через сценарий на stdin (`open -u user,pass`), а не
    аргументом командной строки (`-u user,pass` в argv) — иначе пароль был бы
    виден в `ps aux` всем локальным пользователям машины.
    """
    if not target.password:
        raise InvalidArgumentsError(f"Target {target.name!r}: для connection={target.connection} нужен password")

    local = local_path.rstrip("/") + "/"
    script = (
        _open_script(target)
        + f"mirror --reverse --delete --verbose=0 {_lftp_quote(local)} {_lftp_quote(_remote_path(target))}\n"
        + "quit\n"
    )
    _run_lftp(script, target, timeout)


def mirror_from(target: Target, local_dir: str, timeout: int = DEFAULT_TIMEOUT) -> None:
    """Скачивает текущее содержимое remote_path в local_dir — бэкап перед деплоем
    на Target (см. cli._backup_target_before_deploy), не rollback как таковой.
    Без --delete: local_dir — свежая пустая директория под конкретный таймстамп."""
    if not target.password:
        raise InvalidArgumentsError(f"Target {target.name!r}: для connection={target.connection} нужен password")

    local = local_dir.rstrip("/") + "/"
    # lftp `mirror` без --reverse — как раз скачивание remote -> local.
    script = (
        _open_script(target)
        + f"mirror --verbose=0 {_lftp_quote(_remote_path(target))} {_lftp_quote(local)}\n"
        + "quit\n"
    )
    _run_lftp(script, target, timeout)
