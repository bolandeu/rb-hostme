from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.markup import escape as rich_escape

from hostme import output
from hostme.commands import doctor, domain, server, site, skill, target
from hostme.commands import help as help_cmd
from hostme.core.errors import HostmeError, UnexpectedError
from hostme.core.version import DEV_VERSION, installed_version, package_summary
from hostme.data import load_skill_doc

# Форма команд копирует surge.sh (AGENTS.md): `hostme <path> [domain]` для деплоя,
# `hostme <domain> <subcommand>` для управления — без промежуточных слов вроде "deploy".
# Typer/Click умеет только статическое дерево подкоманд, поэтому реальный argv
# переписывается в explicit-подкоманды (_translate_argv) до того, как его увидит Typer.
_TOP_LEVEL_COMMANDS = {
    "server", "domain", "target", "skill", "list", "open", "doctor", "help", "--ai", "--version", "--help", "-h",
}
_DOMAIN_SUBCOMMANDS = {"teardown", "config", "auth", "ssl", "debug", "revs", "rollback", "rollfore", "maintenance"}
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
        return prefix + [subcmd, domain, *rest]

    # `hostme teardown --help` — просьба о справке по teardown, а не деплой папки
    # с именем "teardown" (иначе показывалась бы справка деплоя, сбивая с толку).
    if args[0] in _DOMAIN_SUBCOMMANDS and (len(args) == 1 or args[1] in ("-h", "--help")):
        return prefix + args

    return prefix + ["_deploy", *args]

# Голый `hostme` — точка входа для человека и агента: имя + версия + описание,
# затем команды с первой строкой docstring. Без no_args_is_help (он выходит с
# кодом 2) — root() ниже печатает справку и выходит с 0 (conventions.md).
app = typer.Typer(
    name="hostme",
    help=f"hostme {installed_version() or DEV_VERSION} — {package_summary() or 'деплой сайтов на свои VPS.'}",
    epilog=rich_escape(help_cmd.GRAMMAR_NOTE),
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

app.add_typer(server.app, name="server")
app.add_typer(domain.app, name="domain")
app.add_typer(target.app, name="target")
app.add_typer(skill.app, name="skill")

app.command("_deploy", hidden=True)(site.deploy)
app.command("list")(site.list_)
app.command("open")(site.open_)
app.command("revs")(site.revs)
app.command("rollback")(site.rollback)
app.command("rollfore")(site.rollfore)
app.command("maintenance")(site.maintenance)
app.command("teardown")(site.teardown)
app.command("auth")(site.auth)
app.command("config")(site.site_config)
app.command("debug")(site.debug)
app.command("doctor")(doctor.doctor)
app.command("help")(help_cmd.help_cmd)


def _version_callback(value: bool) -> None:
    if not value:
        return
    typer.echo(installed_version() or DEV_VERSION)
    raise typer.Exit()


def _ai_callback(value: bool) -> None:
    """Встроенный SKILL.md в stdout — для агента, который может запускать CLI,
    но не может читать файлы с диска (sandbox, remote exec)."""
    if not value:
        return
    typer.echo(load_skill_doc())
    raise typer.Exit()


@app.callback()
def root(
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
    ai: Annotated[
        bool,
        typer.Option(
            "--ai",
            callback=_ai_callback,
            is_eager=True,
            help="Напечатать встроенный SKILL.md (для агента без доступа к файлам на диске) и выйти.",
        ),
    ] = False,
) -> None:
    output.set_json_mode(json_output)
    output.set_quiet(quiet)
    output.set_verbose(verbose)
    output.set_non_interactive(non_interactive)
    output.set_dry_run(dry_run)
    output.configure_logging(verbose)
    output.help_if_no_command(ctx)


def main() -> None:
    # Команды уже под output.guard; это страховка для ошибок в самом
    # root-callback (например, не прочитался bundled SKILL.md для --ai).
    try:
        app(args=_translate_argv(sys.argv[1:]))
    except HostmeError as exc:
        output.emit_error(exc)
    except Exception as exc:  # noqa: BLE001 — не даём агенту голый трейсбек
        output.emit_error(UnexpectedError(exc))


if __name__ == "__main__":
    main()
