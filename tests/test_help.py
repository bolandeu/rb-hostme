"""The --help contract: every command's help is complete, and any change to it shows up in review.

Help text is rendered from command docstrings and `typer.Option`/`Argument`
`help=` strings — it's the documentation agents and humans read, so it's
tested like an API:

- contract tests: every command (walked from the app's registry, so a new
  command is covered automatically) has a docstring with an
  `Example: hostme ...` line that reaches the command, every parameter has non-empty help,
  every group has a description;
- snapshots: `<command> --help` is stored in tests/snapshots/help/<command>.txt
  (syrupy). A changed help text fails until the snapshot is refreshed with
  `uv run pytest --snapshot-update`, which puts the new text in the diff.
  A new command fails until its snapshot exists; a removed one leaves an
  orphan file that fails too.
"""

from __future__ import annotations

import inspect
import shlex
import typing
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import typer
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode
from typer.models import ParameterInfo
from typer.testing import CliRunner

from hostme import output
from hostme.cli import _translate_argv, app

CLI = "hostme"
SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / "help"
# Fixed width and no colour so the rendering doesn't depend on the terminal running the tests.
HELP_ENV = {"COLUMNS": "100", "NO_COLOR": "1", "TERM": "dumb"}


def _commands(group: typer.Typer, prefix: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Callable]]:
    for info in group.registered_commands:
        assert info.callback is not None
        name = info.name or getattr(info.callback, "__name__", "").replace("_", "-")
        yield (*prefix, name), info.callback
    for sub in group.registered_groups:
        assert sub.name is not None and sub.typer_instance is not None
        yield from _commands(sub.typer_instance, (*prefix, sub.name))


def _groups(group: typer.Typer, prefix: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], typer.Typer]]:
    for sub in group.registered_groups:
        assert sub.name is not None and sub.typer_instance is not None
        yield (*prefix, sub.name), sub.typer_instance
        yield from _groups(sub.typer_instance, (*prefix, sub.name))


COMMANDS = dict(_commands(app))
GROUPS = dict(_groups(app))
HELP_PAGES = sorted([*COMMANDS, *GROUPS])


def _slug(path: tuple[str, ...]) -> str:
    return "-".join(path)


def _render_help(path: tuple[str, ...]) -> str:
    result = CliRunner().invoke(app, [*path, "--help"], env=HELP_ENV, prog_name=CLI)
    assert result.exit_code == 0, result.output
    # Trailing padding isn't content; keeping it out keeps the diffs readable.
    return "\n".join(line.rstrip() for line in result.output.splitlines()) + "\n"


class HelpSnapshot(SingleFileSnapshotExtension):
    """One plain-text file per help page: tests/snapshots/help/<command>.txt."""

    _write_mode = WriteMode.TEXT
    file_extension = "txt"

    @classmethod
    def dirname(cls, *, test_location) -> str:
        return str(SNAPSHOT_DIR)

    @classmethod
    def get_snapshot_name(cls, *, test_location, index=0) -> str:
        return str(index)


@pytest.mark.parametrize("path", HELP_PAGES, ids=_slug)
def test_help_snapshot(path: tuple[str, ...], snapshot) -> None:
    assert _render_help(path) == snapshot(extension_class=HelpSnapshot, name=_slug(path))


def test_no_orphan_help_snapshots() -> None:
    stored = {p.stem for p in SNAPSHOT_DIR.glob("*.txt")}
    expected = {_slug(path) for path in HELP_PAGES}
    assert stored <= expected, f"snapshots for commands that no longer exist: {sorted(stored - expected)}"


def _example_reaches(line: str, path: tuple[str, ...]) -> bool:
    """`Example: hostme ...` после surge-перевода argv (cli._translate_argv) попадает в команду `path`.

    У hostme домен/путь идут первыми (`hostme a.dev teardown`), поэтому пример
    сверяется не подстрокой `hostme teardown`, а тем, куда его реально направит CLI.
    """
    argv = shlex.split(line.removeprefix("Example:").strip())
    if not argv or argv[0] != CLI:
        return False
    translated = [a for a in _translate_argv(argv[1:]) if not a.startswith("--") or a in ("--help", "-h")]
    return tuple(translated[: len(path)]) == path


@pytest.mark.parametrize("path", sorted(COMMANDS), ids=_slug)
def test_command_docstring_has_summary_and_example(path: tuple[str, ...]) -> None:
    doc = inspect.getdoc(COMMANDS[path]) or ""
    assert doc.strip(), f"`{_slug(path)}` has no docstring — it is the command's --help text"
    examples = [line for line in doc.splitlines() if line.startswith("Example:")]
    assert any(_example_reaches(line, path) for line in examples), (
        f"`{_slug(path)}` docstring needs an `Example: {CLI} ...` line that runs this command"
    )


@pytest.mark.parametrize("path", sorted(COMMANDS), ids=_slug)
def test_every_command_is_guarded(path: tuple[str, ...]) -> None:
    # output.guard gives the JSON error envelope and keeps [brackets] in help.
    assert output.is_guarded(COMMANDS[path]), f"`{_slug(path)}` must be wrapped in @output.guard"


@pytest.mark.parametrize("path", sorted(COMMANDS), ids=_slug)
def test_every_parameter_has_help(path: tuple[str, ...]) -> None:
    callback = inspect.unwrap(COMMANDS[path])
    hints = typing.get_type_hints(callback, include_extras=True)
    for name, param in inspect.signature(callback).parameters.items():
        hint = hints.get(name)
        if hint is typer.Context:
            continue
        infos = [m for m in getattr(hint, "__metadata__", ()) if isinstance(m, ParameterInfo)]
        if isinstance(param.default, ParameterInfo):
            infos.append(param.default)
        assert infos, f"`{_slug(path)}` parameter `{name}` must be a typer.Option/Argument with help="
        assert all((info.help or "").strip() for info in infos), f"`{_slug(path)}` parameter `{name}` has no help"


@pytest.mark.parametrize("path", sorted(GROUPS), ids=_slug)
def test_every_group_has_help(path: tuple[str, ...]) -> None:
    assert (GROUPS[path].info.help or "").strip(), f"group `{_slug(path)}` has no description"


def test_help_keeps_brackets() -> None:
    """Typer renders help as rich markup, which drops `[...]`; output.guard escapes docstrings."""

    def cmd(ctx: typer.Context) -> None:
        """Declared in [[tool.rb.external]], see [x].

        Example: hostme cmd
        """

    probe = typer.Typer()
    probe.command("cmd")(output.guard(cmd))
    probe.command("other")(output.guard(cmd))
    result = CliRunner().invoke(probe, ["cmd", "--help"], env=HELP_ENV)
    assert "[[tool.rb.external]], see [x]." in result.output
