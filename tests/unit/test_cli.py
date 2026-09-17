import json
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from hostme import output
from hostme.cli import _translate_argv, app, main
from hostme.core.errors import HostmeError

runner = CliRunner()


def _invoke(argv: list[str]):
    # Через _translate_argv, как main() — тесты видят реальную surge-грамматику.
    return runner.invoke(app, _translate_argv(argv))


@pytest.fixture(autouse=True)
def reset_output_state():
    yield
    output.set_json_mode(False)
    output.set_non_interactive(False)
    output.set_dry_run(False)
    output.set_quiet(False)
    output.set_verbose(False)


def test_help_exits_zero() -> None:
    result = _invoke(["--help"])
    assert result.exit_code == 0
    assert "hostme" in result.output.lower()


def test_bare_cli_prints_help_and_exits_zero() -> None:
    # conventions.md: голый `hostme` — вопрос, не ошибка (Click по умолчанию даёт 2).
    result = _invoke([])
    assert result.exit_code == 0
    assert "hostme" in result.output.lower()
    assert "doctor" in result.output


def test_bare_group_prints_help_and_exits_zero() -> None:
    result = _invoke(["server"])
    assert result.exit_code == 0
    assert "add" in result.output and "list" in result.output


def test_version_flag() -> None:
    result = _invoke(["--version"])
    assert result.exit_code == 0
    assert result.output.strip() != ""


def test_ai_flag_prints_bundled_skill() -> None:
    result = _invoke(["--ai"])
    assert result.exit_code == 0
    assert "name: hostme" in result.output


def test_root_callback_sets_output_state() -> None:
    _invoke(["--json", "--non-interactive", "--dry-run", "--quiet", "--verbose", "server", "list"])
    assert output.is_json_mode() is True
    assert output.is_non_interactive() is True
    assert output.is_dry_run() is True
    assert output.is_quiet() is True
    assert output.is_verbose() is True


def test_guarded_command_emits_json_error_envelope_on_stdout() -> None:
    with patch("hostme.commands.site.services.teardown", side_effect=HostmeError("сломалось", action="почини")):
        result = _invoke(["--json", "a.dev", "teardown", "--confirm"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data == {"ok": False, "error": {"code": "ERROR", "message": "сломалось", "action": "почини"}}


def test_guarded_command_maps_unknown_exception_to_unexpected() -> None:
    with patch("hostme.commands.doctor.services.run_doctor", side_effect=RuntimeError("boom")):
        result = _invoke(["--json", "doctor"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "UNEXPECTED"


def test_main_catches_hostme_error_and_exits_with_its_code() -> None:
    with (
        patch("hostme.cli.app", side_effect=HostmeError("boom")),
        pytest.raises((SystemExit, typer.Exit)) as exc_info,
    ):
        main()
    code = getattr(exc_info.value, "exit_code", None) or getattr(exc_info.value, "code", None)
    assert code == 1


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
        (["--version"], ["--version"]),
        ([], []),
        # <domain> <subcommand> -> <subcommand> <domain> (домен первым в реальном вводе)
        (["mydomain.com", "teardown"], ["teardown", "mydomain.com"]),
        (["mydomain.com", "teardown", "--yes"], ["teardown", "mydomain.com", "--yes"]),
        (["mydomain.com", "auth", "--off"], ["auth", "mydomain.com", "--off"]),
        # `hostme teardown --help` — справка по teardown, не деплой папки "teardown"
        (["teardown", "--help"], ["teardown", "--help"]),
        (["rollback", "-h"], ["rollback", "-h"]),
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
        # --json/--non-interactive/--dry-run должны работать и ПОСЛЕ команды
        # (conventions.md cli-builder: агент не обязан знать, что это позиционный
        # флаг) — вынимаются из любой позиции и переносятся в префикс.
        (["doctor", "--json"], ["--json", "doctor"]),
        (["help", "--json"], ["--json", "help"]),
        (["server", "list", "--json"], ["--json", "server", "list"]),
        (["mydomain.com", "teardown", "--yes", "--json"], ["--json", "teardown", "mydomain.com", "--yes"]),
        (["./dist", "--json"], ["--json", "_deploy", "./dist"]),
        (["./dist", "--quiet", "--verbose"], ["--quiet", "--verbose", "_deploy", "./dist"]),
    ],
)
def test_translate_argv(argv: list[str], expected: list[str]) -> None:
    assert _translate_argv(argv) == expected
