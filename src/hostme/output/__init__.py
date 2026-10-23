"""The output layer every command goes through: global options, the `guard` decorator (JSON envelope, exit codes,
`--dry-run`, confirmation) and the result and error emitters.

Режимы (--json/--quiet/--verbose/--non-interactive/--dry-run) живут в `ctx.obj`:
root-callback кладёт их туда один раз. `_translate_argv` в cli.py выносит эти
флаги из любой позиции в префикс, так что они всегда приходят в root-callback.
Сервисы, которым нужен режим (dry-run превью, гейт подтверждения, прогресс),
получают `ctx` от команды.
"""

from __future__ import annotations

import functools
import logging
import sys
import weakref
from collections.abc import Callable
from typing import ClassVar, NoReturn, cast

import typer
from rich.markup import escape
from typer.core import TyperGroup, TyperOption

from ..core.errors import Aborted, CliError, InvalidArguments
from ..core.version import cli_name
from . import human
from . import json as json_output

__all__ = [
    "ConfirmOption",
    "DryRunOption",
    "JsonOption",
    "NonInteractiveOption",
    "QuietOption",
    "RootGroup",
    "VerboseOption",
    "configure_logging",
    "emit_error",
    "emit_report",
    "emit_success",
    "force_utf8_streams",
    "group",
    "guard",
    "help_if_no_command",
    "human",
    "is_dry_run",
    "is_guarded",
    "is_non_interactive",
    "progress",
    "render_error",
    "require_confirmation",
    "success",
    "vecho",
]

_CLI_NAME = cli_name()
_PACKAGE_NAME = __name__.split(".")[0]
# Click's UsageError (unknown option, missing argument, bad value): recent Typer ships its own copy of Click,
# so it is taken from Typer's BadParameter, never imported from the `click` package.
_UsageError = cast("type[Exception]", typer.BadParameter.__bases__[0])
_GUARDED: weakref.WeakSet[Callable] = weakref.WeakSet()
console = human.console
err_console = human.err_console

# Reusable local options: attach to any command so `<cli> <command> --json`
# works, on top of the global `<cli> --json <command>` handled by guard().
JsonOption = typer.Option(False, "--json", help="Emit machine-readable JSON output.")
QuietOption = typer.Option(False, "--quiet", help="Suppress non-essential output.")
DryRunOption = typer.Option(False, "--dry-run", help="Show what would happen without making changes.")
ConfirmOption = typer.Option(
    False, "--confirm", help="Confirm a destructive action (required together with --non-interactive)."
)
VerboseOption = typer.Option(False, "--verbose", help="Emit extra diagnostic output.")
NonInteractiveOption = typer.Option(False, "--non-interactive", help="Never prompt; fail instead.")


def configure_logging(verbose: bool) -> None:
    """Route `logging` to stderr: DEBUG under --verbose, WARNING otherwise.

    This is the diagnostics channel that also works under --json (stdout
    stays pure data). Library debug output (httpx request lines, keyring
    backend selection, ...) shows up under --verbose for free.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )


def help_if_no_command(ctx: typer.Context) -> None:
    """Print the group's help and exit 0 when it was invoked without a subcommand.

    Click's own no-args handling exits 2 (a usage *error*); a bare
    `<cli>` or `<cli> auth` is a question, not a mistake, so it gets the
    help text and a clean exit instead.
    """
    if ctx.invoked_subcommand is not None:
        return
    # Typer's rich help renders straight to the console and returns "";
    # plain click returns the text — handle both.
    text = ctx.get_help()
    if text:
        typer.echo(text)
    raise typer.Exit()


def group(help_text: str) -> typer.Typer:
    """Create a command group (`<cli> config ...`) with help-on-no-args behavior."""
    app = typer.Typer(help=escape(help_text))  # rich would eat `[...]` in the help text

    @app.callback(invoke_without_command=True)
    def _default(ctx: typer.Context) -> None:
        help_if_no_command(ctx)

    return app


class RootGroup(TyperGroup):
    """The CLI's root group: a usage error (unknown option, missing argument) under --json is the error envelope.

    Click reports a usage error while it parses the arguments, before any
    command runs, so `guard` never sees it. The root's own arguments fail in
    `make_context`, a subcommand's inside `invoke`; both end here.

    An optional part adds its global options (`--project`, `--ai`) to `part_options`
    when it registers; they reach no callback argument (`expose_value=False`).
    """

    part_options: ClassVar[list[TyperOption]] = []

    def __init__(self, *, params=None, **kwargs):
        super().__init__(params=[*(params or []), *self.part_options], **kwargs)

    def make_context(self, info_name, args, parent=None, **extra):
        argv = list(args)  # Click consumes `args` while it parses
        try:
            ctx = super().make_context(info_name, args, parent, **extra)
        except _UsageError as exc:
            _usage_error(exc, argv)
        ctx.meta["argv"] = argv
        return ctx

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except _UsageError as exc:
            _usage_error(exc, ctx.meta["argv"])


def _usage_error(exc: Exception, argv: list[str]) -> NoReturn:
    """Under --json: INVALID_ARGUMENTS on stdout, exit 2. Otherwise Click's own usage message."""
    options = argv[: argv.index("--")] if "--" in argv else argv
    if "--json" not in options:
        raise exc
    error = InvalidArguments(str(exc))
    json_output.emit({"ok": False, "error": error.to_dict()})
    raise typer.Exit(code=error.exit_code)


def emit_success(ctx: typer.Context, payload: dict, render_human: Callable[[dict], None]) -> None:
    if ctx.obj.get("json"):
        json_output.emit({"ok": True, **payload})
    elif not ctx.obj.get("quiet"):
        render_human(payload)


def emit_report(
    ctx: typer.Context, payload: dict, render_human: Callable[[dict], None], problem: CliError | None
) -> None:
    """Emit a report that is data whether or not it found a problem (e.g. `auth status`).

    No problem: exactly `emit_success`. A problem: the full payload is still
    emitted, plus `ok: false` and the problem as the standard `error` object,
    and the process exits with the problem's exit code.
    """
    if problem is None:
        emit_success(ctx, payload, render_human)
        return
    if ctx.obj.get("json"):
        json_output.emit({"ok": False, "error": problem.to_dict(), **payload})
    else:
        if not ctx.obj.get("quiet"):
            render_human(payload)
        render_error(problem, json_mode=bool(ctx.obj.get("json")))
    raise typer.Exit(code=problem.exit_code)


def render_error(error: CliError, *, json_mode: bool) -> None:
    """Ошибка наружу: JSON-конверт в stdout под --json (один поток для парсинга,
    `ok: false` + exit-код говорят, что это ошибка), иначе человеку в stderr.

    Без ctx: cli.main зовёт её и для ошибки вне команды, где ctx уже нет."""
    if json_mode:
        json_output.emit({"ok": False, "error": error.to_dict()})
    else:
        human.err_console.print(f"[red]✖[/red] {escape(error.message)}")
        if error.action:
            human.err_console.print(f"  [dim]→ {escape(error.action)}[/dim]")


def emit_error(ctx: typer.Context, error: CliError) -> NoReturn:
    render_error(error, json_mode=bool(ctx.obj.get("json")))
    raise typer.Exit(code=error.exit_code)


def success(ctx: typer.Context, message: str, **fields: object) -> None:
    """Частый случай: команда сделала одно действие и сообщает об этом строкой."""
    # escape — message может быть динамическим (домен, путь, чужой вывод)
    # и случайно содержать "[...]", которое Rich принял бы за markup-тег и съел.
    emit_success(
        ctx,
        {"message": message, **fields},
        render_human=lambda d: human.console.print(f"[green]✔[/green] {escape(str(d['message']))}"),
    )


def progress(ctx: typer.Context, message: str) -> None:
    """Промежуточная строка долгой операции («Создаю сайт...», «Заливаю файлы...»).

    Не результат: под --json stdout — ровно один JSON-объект (итог команды),
    поэтому прогресс уходит в stderr простым текстом. Под --quiet — молчим.
    """
    if ctx.obj.get("quiet"):
        return
    if ctx.obj.get("json"):
        human.err_console.print(message, markup=False, highlight=False)
    else:
        human.console.print(escape(message))


_LOCAL_FLAG_TO_CTX_KEY = {
    "json_output": "json",
    "quiet": "quiet",
    "verbose": "verbose",
    "non_interactive": "non_interactive",
    "dry_run": "dry_run",
}


def is_dry_run(ctx: typer.Context) -> bool:
    return bool(ctx.obj.get("dry_run"))


def is_non_interactive(ctx: typer.Context) -> bool:
    # --json подразумевает неинтерактивный вызов (агент), даже без явного
    # --non-interactive — иначе typer.confirm() повис бы на stdin,
    # который агент не читает.
    return bool(ctx.obj.get("non_interactive") or ctx.obj.get("json"))


def vecho(ctx: typer.Context, message: str) -> None:
    """Print a progress line for a human, only under --verbose and only in human mode.

    For diagnostics that should also reach --json callers (on stderr), use
    `logging.getLogger(__name__).debug(...)` instead — see configure_logging.
    """
    if ctx.obj.get("verbose") and not ctx.obj.get("json") and not ctx.obj.get("quiet"):
        human.err_console.print(f"[dim]{escape(message)}[/dim]")


def _stdin_is_tty() -> bool:
    # Без TTY (cron, systemd, `doppler run` на сервере) спрашивать некого —
    # typer.confirm() там либо упал бы на EOF, либо повис на открытом pipe.
    return sys.stdin is not None and sys.stdin.isatty()


def require_confirmation(ctx: typer.Context, description: str, confirm: bool) -> None:
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
    if is_non_interactive(ctx) or not _stdin_is_tty():
        raise InvalidArguments(
            f"{description} требует явного --confirm в неинтерактивном режиме (--json/--non-interactive/без TTY)",
            action="Повтори с --confirm (или --yes), если это осознанное решение.",
        )
    if not typer.confirm(f"{description}. Продолжить?"):
        raise Aborted(description)


def guard(func: Callable) -> Callable:
    """Route any error raised by a command through emit_error.

    Expected failures (`CliError`) are reported with their own code and
    exit status. Anything else — a bug, a library exception nobody mapped
    yet — becomes an `UNEXPECTED` error (exit 1) so a `--json` caller still
    gets a parseable envelope; the traceback goes to stderr under
    --verbose. Also merges any command-local --json/--quiet/--verbose/
    --non-interactive option into ctx.obj, so both `<cli> --json status`
    and `<cli> status --json` work the same way.
    """

    @functools.wraps(func)
    def wrapper(ctx: typer.Context, *args, **kwargs):
        for flag_name, obj_key in _LOCAL_FLAG_TO_CTX_KEY.items():
            if kwargs.get(flag_name):
                ctx.obj[obj_key] = True
        try:
            return func(ctx, *args, **kwargs)
        except CliError as exc:
            emit_error(ctx, exc)
        except typer.Exit, typer.Abort:
            raise  # already a controlled exit — don't wrap it
        except Exception as exc:  # noqa: BLE001 — в этом и смысл guard: агент не должен увидеть трейсбек
            if ctx.obj.get("verbose"):
                human.err_console.print_exception()
            emit_error(
                ctx,
                CliError(
                    "UNEXPECTED",
                    f"{type(exc).__name__}: {exc}",
                    action="Повтори с --verbose, чтобы увидеть трейсбек; если повторяется — сообщи вместе с ним.",
                ),
            )

    # Docstrings are the --help text; `{cli}` in their `Example:` lines becomes
    # this CLI's name and `{package}` the package's (the project folder's name),
    # so template-born commands need no Jinja rendering.
    # Escaped because Typer renders help as rich markup, which silently drops
    # anything in brackets (`[[tool.rb.external]]`, `[x]`).
    doc = (func.__doc__ or "").replace("{cli}", _CLI_NAME).replace("{package}", _PACKAGE_NAME)
    wrapper.__doc__ = escape(doc) or None
    _GUARDED.add(wrapper)
    return wrapper


def is_guarded(func: Callable) -> bool:
    """Whether `func` is an `output.guard` wrapper — tests/test_help.py requires it of every command."""
    return func in _GUARDED


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
