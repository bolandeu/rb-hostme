from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hostme import output
from hostme.cli import _translate_argv, app, main, root
from hostme.errors import HostmeError

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "hostme" in result.output.lower()


def test_no_command_exits_nonzero() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code != 0


def test_root_callback_sets_json_mode() -> None:
    output.set_json_mode(False)
    root(json_output=True, non_interactive=False, dry_run=False)
    assert output.is_json_mode() is True
    output.set_json_mode(False)


def test_root_callback_sets_non_interactive_and_dry_run() -> None:
    root(json_output=False, non_interactive=True, dry_run=True)
    assert output.is_non_interactive() is True
    assert output.is_dry_run() is True
    output.set_non_interactive(False)
    output.set_dry_run(False)


def test_main_catches_hostme_error_and_exits_with_its_code() -> None:
    with (
        patch("hostme.cli.app", side_effect=HostmeError("boom")),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 1


# _translate_argv — вся surge-style грамматика (домен/путь первым, без слова
# "deploy") держится на этой функции; регрессия здесь молча ломает весь CLI.
@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        # управляющие подкоманды — как есть, без переписывания
        (["server", "list"], ["server", "list"]),
        (["domain", "add", "vps1", "a.dev"], ["domain", "add", "vps1", "a.dev"]),
        (["list"], ["list"]),
        (["doctor"], ["doctor"]),
        ([], []),
        # <domain> <subcommand> -> <subcommand> <domain> (домен первым в реальном вводе)
        (["mydomain.com", "teardown"], ["teardown", "mydomain.com"]),
        (["mydomain.com", "teardown", "--yes"], ["teardown", "mydomain.com", "--yes"]),
        (["mydomain.com", "auth", "--off"], ["auth", "mydomain.com", "--off"]),
        # всё остальное — деплой (путь первым)
        (["./dist"], ["_deploy", "./dist"]),
        (["./dist", "mydomain.com", "--server", "vps1"], ["_deploy", "./dist", "mydomain.com", "--server", "vps1"]),
        # глобальные флаги-префиксы (в любом порядке между собой) должны пережить переписывание
        (["--json", "mydomain.com", "teardown"], ["--json", "teardown", "mydomain.com"]),
        (["--json", "./dist"], ["--json", "_deploy", "./dist"]),
        (["--non-interactive", "mydomain.com", "teardown"], ["--non-interactive", "teardown", "mydomain.com"]),
        (["--dry-run", "mydomain.com", "rollback"], ["--dry-run", "rollback", "mydomain.com"]),
        (
            ["--json", "--non-interactive", "mydomain.com", "teardown", "--yes"],
            ["--json", "--non-interactive", "teardown", "mydomain.com", "--yes"],
        ),
    ],
)
def test_translate_argv(argv: list[str], expected: list[str]) -> None:
    assert _translate_argv(argv) == expected
