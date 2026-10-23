"""The root Typer app: global options, the command groups and the optional commands a generated package has, wired
together, and the console-script entry point.
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.markup import escape as rich_escape

from . import config, output
from .commands import auth, doctor, domain, server, site, target
from .commands import help as help_cmd
from .core.errors import CliError
from .core.version import DEV_VERSION, installed_version, optional_module, package_summary

_PACKAGE_NAME = __name__.split(".")[0]
# Optional parts (copier questions, dropped by _exclude): each one ships a module that registers its
# commands and global options. Probed at runtime, so this file needs no template logic.
PARTS = ("project", "skill", "describe", "db")

# Форма команд копирует surge.sh (AGENTS.md): `hostme <path> [domain]` для деплоя,
# `hostme <domain> <subcommand>` для управления — без промежуточных слов вроде "deploy".
# Typer/Click умеет только статическое дерево подкоманд, поэтому реальный argv
# переписывается в explicit-подкоманды (_translate_argv) до того, как его увидит Typer.
_TOP_LEVEL_COMMANDS = {
    "auth",
    "server",
    "domain",
    "target",
    "skill",
    "describe",
    "list",
    "open",
    "doctor",
    "help",
    "--ai",
    "--version",
    "--help",
    "-h",
}
_DOMAIN_SUBCOMMANDS = {"teardown", "config", "auth", "ssl", "debug", "revs", "rollback", "rollfore", "maintenance"}
# `auth` занят дважды: `hostme auth status` — отчёт о доступах (стандарт §8, одинаковый
# у всех tools), `hostme <domain> auth` — HTTP Basic Auth сайта. Доменная форма
# уходит во внутреннее имя команды.
_DOMAIN_SUBCOMMAND_TARGETS = {"auth": "http-auth"}
# Глобальные флаги — только на уровне root-callback (Typer не даёт их объявить
# и там, и на каждой команде одновременно без дублирования на 15+ функций), но
# агент не обязан помнить, что они идут именно ДО команды — conventions.md
# (cli-builder) требует, чтобы `<cli> <command> --json` работало наравне с
# `<cli> --json <command>`. Раз argv и так целиком переписывается под
# surge-грамматику ниже, тут же вынимаем эти флаги из ЛЮБОЙ позиции и
# перекладываем в префикс — не только с начала, как раньше.
_GLOBAL_PREFIX_FLAGS = {"--json", "--non-interactive", "--dry-run", "--quiet", "--verbose"}


def _translate_argv(argv: list[str]) -> list[str]:
    prefix: list[str] = [a for a in argv if a in _GLOBAL_PREFIX_FLAGS]
    args = [a for a in argv if a not in _GLOBAL_PREFIX_FLAGS]

    if not args or args[0] in _TOP_LEVEL_COMMANDS:
        return prefix + args

    if len(args) >= 2 and args[1] in _DOMAIN_SUBCOMMANDS:
        domain, subcmd, *rest = args
        return [*prefix, _DOMAIN_SUBCOMMAND_TARGETS.get(subcmd, subcmd), domain, *rest]

    # `hostme teardown --help` — просьба о справке по teardown, а не деплой папки
    # с именем "teardown" (иначе показывалась бы справка деплоя, сбивая с толку).
    if args[0] in _DOMAIN_SUBCOMMANDS and (len(args) == 1 or args[1] in ("-h", "--help")):
        return prefix + args

    return [*prefix, "_deploy", *args]


# Голый `hostme` — точка входа для человека и агента: имя + версия + описание,
# затем команды с первой строкой docstring. Без no_args_is_help (он выходит с
# кодом 2) — main_options() ниже печатает справку и выходит с 0 (conventions.md).
app = typer.Typer(
    cls=output.RootGroup,  # a usage error under --json is the error envelope
    name="hostme",
    help=f"hostme {installed_version() or DEV_VERSION} — {package_summary() or 'деплой сайтов на свои VPS.'}",
    epilog=rich_escape(help_cmd.GRAMMAR_NOTE),
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

app.add_typer(server.app, name="server")
app.add_typer(domain.app, name="domain")
app.add_typer(target.app, name="target")
app.add_typer(auth.app, name="auth")

app.command("_deploy", hidden=True)(site.deploy)
app.command("list")(site.list_)
app.command("open")(site.open_)
app.command("revs")(site.revs)
app.command("rollback")(site.rollback)
app.command("rollfore")(site.rollfore)
app.command("maintenance")(site.maintenance)
app.command("teardown")(site.teardown)
app.command("http-auth")(site.auth)
app.command("config")(site.site_config)
app.command("debug")(site.debug)
app.command("doctor")(doctor.doctor)
app.command("help")(help_cmd.help_cmd)
for part in PARTS:
    if module := optional_module(f"{_PACKAGE_NAME}.commands.{part}"):
        module.register(app)


def _version_callback(value: bool) -> None:
    if not value:
        return
    typer.echo(installed_version() or DEV_VERSION)
    raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_options(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Машиночитаемый вывод (для агентов).")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="Не печатать необязательный человеческий вывод.")] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Диагностика в stderr: какие ssh/rsync/lftp-команды реально запускаются.")
    ] = False,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Никогда не спрашивать подтверждение интерактивно.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Показать, что сделала бы деструктивная команда, ничего не меняя.")
    ] = False,
    version: Annotated[
        bool, typer.Option("--version", callback=_version_callback, is_eager=True, help="Показать версию и выйти.")
    ] = False,
) -> None:
    ctx.ensure_object(dict)  # a part's global option (--project) may have put its value here already
    ctx.obj["json"] = json_output
    ctx.obj["quiet"] = quiet
    ctx.obj["verbose"] = verbose
    ctx.obj["non_interactive"] = non_interactive
    ctx.obj["dry_run"] = dry_run
    output.configure_logging(verbose)
    _migrate_legacy_data()
    output.help_if_no_command(ctx)


def _migrate_legacy_data() -> None:
    """До v0.4.0 состояние (sites.yaml, target-backups) лежало в ~/.config/hostme;
    переносим один раз и сообщаем в stderr (stdout занят --json)."""
    moved = config.migrate_legacy_data()
    for line in moved:
        output.human.err_console.print(f"hostme: данные перенесены (стандарт §13): {rich_escape(line)}")


def main() -> None:
    output.force_utf8_streams()
    # Команды уже под output.guard; это страховка для ошибок в самом
    # root-callback (например, не перенеслись данные в _migrate_legacy_data).
    # Здесь мы уже вне Typer — typer.Exit никто не поймает, поэтому sys.exit.
    argv = _translate_argv(sys.argv[1:])
    json_mode = "--json" in argv
    try:
        app(args=argv)
    except CliError as exc:
        output.render_error(exc, json_mode=json_mode)
        sys.exit(exc.exit_code)
    except Exception as exc:  # noqa: BLE001 — не даём агенту голый трейсбек
        error = CliError(
            "UNEXPECTED",
            f"{type(exc).__name__}: {exc}",
            action="Повтори с --verbose, чтобы увидеть трейсбек; если повторяется — сообщи вместе с ним.",
        )
        output.render_error(error, json_mode=json_mode)
        sys.exit(error.exit_code)


if __name__ == "__main__":
    main()
