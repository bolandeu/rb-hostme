"""Файлы на сторонний хостинг (Target с connection=ftp/sftp) через lftp — заливка
целиком или никак: новая версия едет в соседнюю staging-папку, а на живой путь её
подменяет пара rename'ов в той же родительской папке. Прерванная или упавшая
заливка оставляет живой путь прежним, а не смешанным из старых и новых файлов.
Скрипт lftp идёт на stdin, поэтому пароль не виден в `ps aux`. Решение и причины —
docs/adr/0010-target-deploy-swaps-by-rename.md."""

from __future__ import annotations

import logging
import subprocess

from hostme.config import Target
from hostme.core.errors import InvalidArguments, ProviderError

DEFAULT_TIMEOUT = 300
# Соседние с живым каталогом папки заливки: rename на стороне хостинга работает
# только внутри одной родительской папки (и обычно только в одной файловой системе).
STAGING_SUFFIX = ".hostme-staging"
OLD_SUFFIX = ".hostme-old"
_log = logging.getLogger(__name__)

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
    # Скрипт целиком не логируем — в нём `open -u user,password`.
    _log.debug("lftp %s@%s (%s), %d строк скрипта", target.user, target.host, target.connection, script.count("\n"))
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
    # Время файла — метка сборки, а не момент заливки: берём mtime из MDTM сервера
    # и ставим его через SITE UTIME. Без этого mirror проставляет дату заливки.
    return (
        "set sftp:auto-confirm yes\n"
        "set ssl:verify-certificate no\n"
        "set ftp:use-mdtm yes\n"
        "set ftp:use-site-utime2 yes\n"
        f"open -u {target.user},{target.password} {target.connection}://{target.host}\n"
    )

def _script(target: Target, *commands: str) -> str:
    return _open_script(target) + "".join(command + "\n" for command in commands) + "quit\n"

def _swap_paths(target: Target) -> tuple[str, str, str]:
    """(staging, live, old) — три пути в одной родительской папке; live — сам
    remote_path. Корень аккаунта как remote_path не годится: его нельзя переименовать."""
    live = _remote_path(target).rstrip("/")
    if not live:
        raise InvalidArguments(
            f"Target {target.name!r}: remote_path указывает на корень аккаунта, а подмена требует каталог "
            "(например, 'public_html' или '/www/site')"
        )
    return live + STAGING_SUFFIX, live, live + OLD_SUFFIX

def _rename(source: str, destination: str, target: Target, timeout: int) -> bool:
    """`mv` в lftp внутри одной родительской папки — rename на сервере, не копия.
    False — команда не прошла; для живого каталога это значит «его ещё нет»."""
    try:
        _run_lftp(_script(target, f"mv {_lftp_quote(source)} {_lftp_quote(destination)}"), target, timeout)
    except FtpError as exc:
        _log.debug("lftp %s: mv %s -> %s не прошёл: %s", target.name, source, destination, exc)
        return False
    return True

def _swap(staging: str, live: str, old: str, target: Target, timeout: int) -> None:
    """live -> old, затем staging -> live. Если второй rename не прошёл, возвращаем
    old на место live: посетитель видит либо прежний сайт, либо новый, но не пустоту."""
    live_moved = _rename(live, old, target, timeout)
    if not _rename(staging, live, target, timeout):
        if live_moved:
            _rename(old, live, target, timeout)
        raise FtpError(f"lftp на {target.name}: не удалось подменить {live}, прежние файлы возвращены на место")
    if live_moved:
        try:
            _run_lftp(_script(target, f"rm -r -f {_lftp_quote(old)}"), target, timeout)
        except FtpError as exc:
            # Сайт уже новый; остаток уберёт начало следующего деплоя.
            _log.warning("lftp %s: не удалось удалить %s: %s", target.name, old, exc)

def mirror_to(local_path: str, target: Target, timeout: int = DEFAULT_TIMEOUT) -> None:
    """Заливка на Target с connection=ftp/sftp через lftp (та же `mirror --reverse
    --delete`, что уже используется в существующих Makefile-пайплайнах для таких
    хостингов — не изобретаем новый подход, переиспользуем проверенный).

    Заливка идёт в staging-папку рядом с живым каталогом, живой каталог меняется
    только после успешной заливки — парой rename'ов. Упавшая заливка не меняет
    ничего, что видит посетитель.

    Логин/пароль идут в lftp через сценарий на stdin (`open -u user,pass`), а не
    аргументом командной строки (`-u user,pass` в argv) — иначе пароль был бы
    виден в `ps aux` всем локальным пользователям машины.
    """
    if not target.password:
        raise InvalidArguments(f"Target {target.name!r}: для connection={target.connection} нужен password")

    staging, live, old = _swap_paths(target)
    local = local_path.rstrip("/") + "/"
    _run_lftp(
        _script(
            target,
            # Остатки прошлых неудачных попыток: их место занимает эта заливка.
            f"rm -r -f {_lftp_quote(old)}",
            f"rm -r -f {_lftp_quote(staging)}",
            f"mirror --reverse --delete --verbose=0 {_lftp_quote(local)} {_lftp_quote(staging)}",
        ),
        target,
        timeout,
    )
    _swap(staging, live, old, target, timeout)

def mirror_from(target: Target, local_dir: str, timeout: int = DEFAULT_TIMEOUT) -> None:
    """Скачивает текущее содержимое remote_path в local_dir — бэкап перед деплоем
    на Target (см. cli._backup_target_before_deploy), не rollback как таковой.
    Без --delete: local_dir — свежая пустая директория под конкретный таймстамп."""
    if not target.password:
        raise InvalidArguments(f"Target {target.name!r}: для connection={target.connection} нужен password")

    local = local_dir.rstrip("/") + "/"
    # lftp `mirror` без --reverse — как раз скачивание remote -> local.
    script = _script(target, f"mirror --verbose=0 {_lftp_quote(_remote_path(target))} {_lftp_quote(local)}")
    _run_lftp(script, target, timeout)

def check_target(target: Target, timeout: float) -> tuple[str, str | None]:
    """Логин + листинг remote_path — дешёвая read-only проверка для `hostme auth status --check`."""
    if not target.password:
        return "invalid", f"для connection={target.connection} нужен password"
    script = (
        f"set net:timeout {int(timeout)}\nset net:max-retries 1\nset net:reconnect-interval-base 1\n"
        + _script(target, f"cls -1 {_lftp_quote(_remote_path(target))}")
    )
    _log.debug("lftp %s@%s (%s): проверка доступа", target.user, target.host, target.connection)
    try:
        proc = subprocess.run(["lftp"], input=script, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return "unreachable", f"нет ответа за {timeout:.0f}с"
    except FileNotFoundError:
        return "unreachable", "`lftp` не найден в PATH"
    if proc.returncode == 0:
        return "ok", None
    text = (proc.stderr or proc.stdout).strip()
    last = text.splitlines()[-1] if text else f"lftp завершился с кодом {proc.returncode}"
    if any(marker in text.lower() for marker in ("login failed", "login incorrect", "530", "authentication failed")):
        return "invalid", last
    return "unreachable", last
