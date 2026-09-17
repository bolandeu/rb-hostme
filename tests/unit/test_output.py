import json
from unittest.mock import patch

import pytest

from hostme import output
from hostme.core.errors import AbortedError, HostmeError, InvalidArgumentsError


@pytest.fixture(autouse=True)
def reset_state():
    output.set_json_mode(False)
    output.set_non_interactive(False)
    output.set_dry_run(False)
    yield
    output.set_json_mode(False)
    output.set_non_interactive(False)
    output.set_dry_run(False)


def test_success_plain_text(capsys):
    output.success("done")
    captured = capsys.readouterr()
    assert "done" in captured.out


def test_success_json(capsys):
    output.set_json_mode(True)
    output.success("done", domain="a.dev")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data == {"ok": True, "message": "done", "domain": "a.dev"}


def test_info_plain_text(capsys):
    output.info("hello")
    captured = capsys.readouterr()
    assert "hello" in captured.out


def test_error_plain_text_exits_with_code_from_error(capsys):
    with pytest.raises(SystemExit) as exc_info:
        output.error(HostmeError("bad thing"))
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "bad thing" in captured.err


def test_error_from_plain_string_defaults_to_generic_error(capsys):
    with pytest.raises(SystemExit) as exc_info:
        output.error("bad thing")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "bad thing" in captured.err


def test_error_json_uses_conventions_envelope(capsys):
    output.set_json_mode(True)
    with pytest.raises(SystemExit) as exc_info:
        output.error(HostmeError("bad thing"))
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    data = json.loads(captured.err)
    assert data == {"ok": False, "error": {"code": "ERROR", "message": "bad thing"}}


def test_error_json_includes_code_and_action_for_subclasses(capsys):
    output.set_json_mode(True)
    exc = InvalidArgumentsError("--connection должен быть ssh/ftp/sftp", action="Повтори с корректным значением.")
    with pytest.raises(SystemExit) as exc_info:
        output.error(exc)
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    data = json.loads(captured.err)
    assert data == {
        "ok": False,
        "error": {
            "code": "INVALID_ARGUMENTS",
            "message": "--connection должен быть ssh/ftp/sftp",
            "action": "Повтори с корректным значением.",
        },
    }


def test_json_mode_toggle():
    assert output.is_json_mode() is False
    output.set_json_mode(True)
    assert output.is_json_mode() is True


def test_non_interactive_toggle():
    assert output.is_non_interactive() is False
    output.set_non_interactive(True)
    assert output.is_non_interactive() is True


def test_json_mode_implies_non_interactive():
    # --json подразумевает агента на другом конце — как и --non-interactive,
    # не должно виснуть на typer.confirm() без stdin.
    output.set_json_mode(True)
    assert output.is_non_interactive() is True


def test_dry_run_toggle():
    assert output.is_dry_run() is False
    output.set_dry_run(True)
    assert output.is_dry_run() is True


# --- require_confirmation — единый гейт для деструктивных команд ---


def test_require_confirmation_yes_skips_prompt():
    with patch("hostme.output.typer.confirm") as mock_confirm:
        output.require_confirmation("Снести сайт a.dev", yes=True)
    mock_confirm.assert_not_called()


def test_require_confirmation_json_without_yes_raises_instead_of_bypassing():
    output.set_json_mode(True)
    with pytest.raises(InvalidArgumentsError, match="--yes"):
        output.require_confirmation("Снести сайт a.dev", yes=False)


def test_require_confirmation_non_interactive_without_yes_raises():
    output.set_non_interactive(True)
    with pytest.raises(InvalidArgumentsError, match="--yes"):
        output.require_confirmation("Снести сайт a.dev", yes=False)


def test_require_confirmation_interactive_confirmed_proceeds():
    with patch("hostme.output.typer.confirm", return_value=True) as mock_confirm:
        output.require_confirmation("Снести сайт a.dev", yes=False)
    mock_confirm.assert_called_once()


def test_require_confirmation_interactive_declined_raises_aborted():
    with (
        patch("hostme.output.typer.confirm", return_value=False),
        pytest.raises(AbortedError),
    ):
        output.require_confirmation("Снести сайт a.dev", yes=False)
