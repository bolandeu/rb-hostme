from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from hostme import output
from hostme.cli import _confirm_target_action, _translate_argv, app, main, root
from hostme.config import Target
from hostme.errors import HostmeError

runner = CliRunner()


def make_target(**overrides) -> Target:
    defaults = {
        "name": "top-ved.ru",
        "connection": "ssh",
        "host": "host.example",
        "user": "u12345",
        "remote_path": "top-ved.ru/public_html",
        "password": "secret",
    }
    defaults.update(overrides)
    return Target(**defaults)


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "hostme" in result.output.lower()


def test_no_command_exits_nonzero() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code != 0


def test_root_callback_sets_json_mode() -> None:
    output.set_json_mode(False)
    root(json_output=True)
    assert output.is_json_mode() is True
    output.set_json_mode(False)


def test_main_catches_hostme_error_and_exits_one() -> None:
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
        ([], []),
        # <domain> <subcommand> -> <subcommand> <domain> (домен первым в реальном вводе)
        (["mydomain.com", "teardown"], ["teardown", "mydomain.com"]),
        (["mydomain.com", "teardown", "--yes"], ["teardown", "mydomain.com", "--yes"]),
        (["mydomain.com", "auth", "--off"], ["auth", "mydomain.com", "--off"]),
        # всё остальное — деплой (путь первым)
        (["./dist"], ["_deploy", "./dist"]),
        (["./dist", "mydomain.com", "--server", "vps1"], ["_deploy", "./dist", "mydomain.com", "--server", "vps1"]),
        # --json — глобальный префикс, должен пережить переписывание
        (["--json", "mydomain.com", "teardown"], ["--json", "teardown", "mydomain.com"]),
        (["--json", "./dist"], ["--json", "_deploy", "./dist"]),
    ],
)
def test_translate_argv(argv: list[str], expected: list[str]) -> None:
    assert _translate_argv(argv) == expected


# _confirm_target_action — деплой/teardown/rollback на target (сторонний хостинг)
# обязаны получить явное подтверждение НА КАЖДЫЙ вызов; --json не должен давать
# агенту возможность это подтверждение обойти молча (см. skill hostme/SKILL.md).


def test_confirm_target_action_yes_flag_skips_prompt() -> None:
    output.set_json_mode(False)
    with patch("hostme.cli.typer.confirm") as mock_confirm:
        _confirm_target_action("Деплой x", make_target(), yes=True)
    mock_confirm.assert_not_called()


def test_confirm_target_action_json_without_yes_raises_instead_of_bypassing() -> None:
    output.set_json_mode(True)
    try:
        with pytest.raises(HostmeError, match="--yes"):
            _confirm_target_action("Деплой x", make_target(), yes=False)
    finally:
        output.set_json_mode(False)


def test_confirm_target_action_interactive_confirmed_proceeds() -> None:
    output.set_json_mode(False)
    with patch("hostme.cli.typer.confirm", return_value=True) as mock_confirm:
        _confirm_target_action("Деплой x", make_target(), yes=False)
    mock_confirm.assert_called_once()


def test_confirm_target_action_interactive_declined_exits() -> None:
    output.set_json_mode(False)
    with (
        patch("hostme.cli.typer.confirm", return_value=False),
        pytest.raises(typer.Exit),
    ):
        _confirm_target_action("Деплой x", make_target(), yes=False)
