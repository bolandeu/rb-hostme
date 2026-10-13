"""Единственная точка вывода hostme: человеку (rich, stdout/stderr) или агенту (--json).

Режимы (--json/--quiet/--verbose/--non-interactive/--dry-run) хранятся здесь как
состояние процесса, а не прокидываются через ctx: `_translate_argv` в cli.py и так
переписывает argv и выносит эти флаги в префикс, так что root-callback выставляет
их один раз до любой команды, а сервисы (dry-run превью, гейт подтверждения)
спрашивают их напрямую.
"""

from __future__ import annotations

import functools
import logging
import sys
import weakref
from collections.abc import Callable
from typing import NoReturn

import typer
from rich.markup import escape as rich_escape

from hostme.core.errors import (
    AbortedError,
    HostmeError,
    InvalidArgumentsError,
    UnexpectedError,
)
from hostme.output import human
from hostme.output import json as json_output

console = human.console
_GUARDED: weakref.WeakSet[Callable] = weakref.WeakSet()
err_console = human.err_console

_json_mode = False
_non_interactive = False
_dry_run = False
_quiet = False
_verbose = False


def set_json_mode(enabled: bool) -> None:
    global _json_mode
    _json_mode = enabled


def is_json_mode() -> bool:
    return _json_mode


def set_non_interactive(enabled: bool) -> None:
    global _non_interactive
    _non_interactive = enabled


def is_non_interactive() -> bool:
    # --json подразумевает неинтерактивный вызов (агент), даже без явного
    # --non-interactive — иначе typer.confirm() ниже повис бы на stdin,
    # который агент не читает.
    return _non_interactive or _json_mode


def set_dry_run(enabled: bool) -> None:
    global _dry_run
    _dry_run = enabled


def is_dry_run() -> bool:
    return _dry_run


def set_quiet(enabled: bool) -> None:
    global _quiet
    _quiet = enabled


def is_quiet() -> bool:
    return _quiet


def set_verbose(enabled: bool) -> None:
    global _verbose
    _verbose = enabled


def is_verbose() -> bool:
    return _verbose


def configure_logging(verbose: bool) -> None:
    """`logging` → stderr: DEBUG под --verbose, иначе WARNING и выше.

    Это канал диагностики, который работает и под --json (stdout остаётся
    чистыми данными): провайдеры пишут сюда, какую именно команду ssh/rsync/
    lftp они запускают.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )


# --- справка вместо usage-ошибки ------------------------------------------------


def help_if_no_command(ctx: typer.Context) -> None:
    """Голый `hostme` / `hostme server` — вопрос, а не ошибка: справка и exit 0.

    Click по умолчанию отвечает «Missing command» с кодом 2 — неверно для CLI,
    который агент изучает, тыкая в него без контекста (conventions.md).
    """
    if ctx.invoked_subcommand is not None:
        return
    # Typer с rich печатает справку сам и возвращает "" — plain click вернёт текст.
    text = ctx.get_help()
    if text:
        typer.echo(text)
    raise typer.Exit()


def group(help_text: str) -> typer.Typer:
    """Группа команд (`hostme server ...`) с поведением «без подкоманды — справка, exit 0»."""
    app = typer.Typer(help=help_text)

    @app.callback(invoke_without_command=True)
    def _default(ctx: typer.Context) -> None:
        help_if_no_command(ctx)

    return app


# --- вывод результата ---------------------------------------------------------


def emit_success(payload: dict, render_human: Callable[[dict], None]) -> None:
    """Один результат — два представления: JSON-конверт под --json, иначе render_human.

    render_human получает тот же payload, что уйдёт в JSON — так человеческий
    и машинный вывод не могут разойтись по содержанию, только по форме.
    """
    if _json_mode:
        json_output.emit({"ok": True, **payload})
    elif not _quiet:
        render_human(payload)


def emit_report(payload: dict, render_human: Callable[[dict], None], problem: HostmeError | None) -> None:
    """Отчёт, который остаётся данными и при найденной проблеме (`auth status`).

    Без проблемы — ровно emit_success. С проблемой — тот же payload целиком плюс
    `ok: false` и стандартный объект `error`, и выход с кодом ошибки.
    """
    if problem is None:
        emit_success(payload, render_human)
        return
    if _json_mode:
        json_output.emit({"ok": False, **payload, "error": problem.to_dict()})
        raise typer.Exit(code=problem.exit_code)
    if not _quiet:
        render_human(payload)
    emit_error(problem)


def success(message: str, **fields: object) -> None:
    """Частый случай: команда сделала одно действие и сообщает об этом строкой."""
    # rich_escape — message может быть динамическим (домен, путь, чужой вывод)
    # и случайно содержать "[...]", которое Rich принял бы за markup-тег и съел.
    emit_success(
        {"message": message, **fields},
        render_human=lambda d: console.print(f"[green]✔[/green] {rich_escape(str(d['message']))}"),
    )


def progress(message: str) -> None:
    """Промежуточная строка долгой операции («Создаю сайт...», «Заливаю файлы...»).

    Не результат: под --json stdout — ровно один JSON-объект (итог команды),
    поэтому прогресс уходит в stderr простым текстом. Под --quiet — молчим.
    """
    if _quiet:
        return
    if _json_mode:
        err_console.print(message, markup=False, highlight=False)
    else:
        console.print(rich_escape(message))


def vecho(message: str) -> None:
    """Строка прогресса для человека — только под --verbose и только не в --json.

    Для диагностики, которая нужна и --json-вызывающему (в stderr), — `logging`,
    см. configure_logging.
    """
    if _verbose and not _json_mode and not _quiet:
        err_console.print(f"[dim]{rich_escape(message)}[/dim]")


def render_error(exc: HostmeError) -> None:
    """Ошибка наружу: JSON-конверт в stdout под --json (один поток для парсинга,
    `ok: false` + exit-код говорят, что это ошибка), иначе человеку в stderr."""
    if _json_mode:
        json_output.emit({"ok": False, "error": exc.to_dict()})
    else:
        err_console.print(f"[red]✖[/red] {rich_escape(exc.message)}")
        if exc.action:
            err_console.print(f"  [dim]→ {rich_escape(exc.action)}[/dim]")


def emit_error(exc: HostmeError) -> NoReturn:
    """render_error + выход с кодом ошибки — для кода внутри Typer-команды
    (typer.Exit там перехватывает сам Typer). Вне приложения — cli.main —
    зовёт render_error и sys.exit сам."""
    render_error(exc)
    raise typer.Exit(code=exc.exit_code)


def force_utf8_streams() -> None:
    """stdout/stderr → UTF-8, если ОС выбрала что-то другое.

    Поймано CI на Windows: при перенаправлении вывода в pipe (ровно случай агента,
    который парсит --json) Python берёт локальную кодировку (cp1252), и первый же
    символ вне неё («≡», кириллица) роняет команду с UnicodeEncodeError. В
    интерактивной консоли Windows и на POSIX это no-op.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None and (stream.encoding or "").lower().replace("-", "") != "utf8":
            reconfigure(encoding="utf-8")


# --- гейт деструктивных команд ------------------------------------------------


def _stdin_is_tty() -> bool:
    # Без TTY (cron, systemd, `doppler run` на сервере) спрашивать некого —
    # typer.confirm() там либо упал бы на EOF, либо повис на открытом pipe.
    return sys.stdin is not None and sys.stdin.isatty()


def require_confirmation(description: str, confirm: bool) -> None:
    """Единый гейт подтверждения для деструктивных команд (teardown/rollback/
    maintenance — свой сервер и target одинаково, раздел 10 architecture.md).

    Вызывать непосредственно перед самим действием — после dry-run-ветки, не до.
    --confirm (алиас --yes/-y) закрывает вопрос сразу. Иначе в неинтерактивном
    режиме (--json и/или --non-interactive, или stdin не терминал) требуем явный --confirm отдельной
    ошибкой — не проходим молча и не зависаем на typer.confirm() без stdin.
    В интерактивном терминале — обычный запрос да/нет; «нет» → ABORTED.
    """
    if confirm:
        return
    if is_non_interactive() or not _stdin_is_tty():
        raise InvalidArgumentsError(
            f"{description} требует явного --confirm в неинтерактивном режиме (--json/--non-interactive/без TTY)",
            action="Повтори с --confirm (или --yes), если это осознанное решение.",
        )
    if not typer.confirm(f"{description}. Продолжить?"):
        raise AbortedError(description)


# --- guard: любая команда — либо результат, либо конверт ошибки ---------------


def guard(func: Callable) -> Callable:
    """Оборачивает команду: HostmeError → emit_error со своим кодом; любое другое
    исключение → UNEXPECTED (exit 1), чтобы --json-вызывающий всё равно получил
    конверт, а не трейсбек. Сам трейсбек — в stderr под --verbose."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HostmeError as exc:
            emit_error(exc)
        except typer.Exit, typer.Abort:
            raise  # уже контролируемый выход — не заворачиваем
        except Exception as exc:  # noqa: BLE001 — в этом и смысл guard: агент не должен увидеть трейсбек
            if _verbose:
                err_console.print_exception()
            emit_error(UnexpectedError(exc))

    # Docstring = --help (стандарт §7). Typer рендерит его как rich-markup, а тот
    # молча съедает всё в квадратных скобках — `[domain]`, `[--confirm]`.
    wrapper.__doc__ = rich_escape(func.__doc__ or "") or None
    _GUARDED.add(wrapper)
    return wrapper


def is_guarded(func: Callable) -> bool:
    """Обёрнута ли функция в `output.guard` — tests/test_help.py требует этого от каждой команды."""
    return func in _GUARDED
