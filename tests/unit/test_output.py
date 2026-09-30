import json
from unittest.mock import patch

import pytest
import typer

from hostme import output
from hostme.core.errors import AbortedError, HostmeError, InvalidArgumentsError


@pytest.fixture(autouse=True)
def reset_state():
    output.set_json_mode(False)
    output.set_non_interactive(False)
    output.set_dry_run(False)
    output.set_quiet(False)
    output.set_verbose(False)
    yield
    output.set_json_mode(False)
    output.set_non_interactive(False)
    output.set_dry_run(False)
    output.set_quiet(False)
    output.set_verbose(False)


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


def test_error_plain_text_goes_to_stderr_with_code_from_error(capsys):
    with pytest.raises(typer.Exit) as exc_info:
        output.emit_error(HostmeError("bad thing", action="сделай так"))
    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bad thing" in captured.err
    assert "сделай так" in captured.err


def test_error_json_uses_conventions_envelope_on_stdout(capsys):
    # conventions.md: под --json конверт ошибки — в stdout (один поток для
    # парсинга), ok:false + exit-код говорят, что это ошибка.
    output.set_json_mode(True)
    with pytest.raises(typer.Exit) as exc_info:
        output.emit_error(HostmeError("bad thing"))
    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data == {"ok": False, "error": {"code": "ERROR", "message": "bad thing"}}


def test_error_json_includes_code_and_action_for_subclasses(capsys):
    output.set_json_mode(True)
    exc = InvalidArgumentsError("--connection должен быть ssh/ftp/sftp", action="Повтори с корректным значением.")
    with pytest.raises(typer.Exit) as exc_info:
        output.emit_error(exc)
    assert exc_info.value.exit_code == 2
    captured = capsys.readouterr()
    data = json.loads(captured.out)
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


def test_quiet_suppresses_human_but_not_json(capsys):
    output.set_quiet(True)
    output.success("тихо", domain="a.dev")
    assert capsys.readouterr().out == ""
    output.set_json_mode(True)
    output.success("тихо", domain="a.dev")
    assert json.loads(capsys.readouterr().out)["domain"] == "a.dev"
    output.set_quiet(False)


def test_json_success_is_single_line_and_keeps_unicode(capsys):
    output.set_json_mode(True)
    output.success("Готово: " + "x" * 300, path="/очень/длинный/путь")
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert "Готово" in out  # ensure_ascii=False


# --- guard — любая команда либо отдаёт результат, либо конверт ошибки ---


def test_guard_maps_hostme_error_to_its_exit_code(capsys):
    @output.guard
    def cmd():
        raise InvalidArgumentsError("плохо")

    with pytest.raises(typer.Exit) as exc_info:
        cmd()
    assert exc_info.value.exit_code == 2
    assert "плохо" in capsys.readouterr().err


def test_guard_turns_unknown_exception_into_unexpected_envelope(capsys):
    output.set_json_mode(True)

    @output.guard
    def cmd():
        raise KeyError("boom")

    with pytest.raises(typer.Exit) as exc_info:
        cmd()
    assert exc_info.value.exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["error"]["code"] == "UNEXPECTED"
    assert "KeyError" in data["error"]["message"]
    assert "--verbose" in data["error"]["action"]


def test_guard_passes_controlled_exit_through():
    @output.guard
    def cmd():
        raise typer.Exit(code=0)

    with pytest.raises(typer.Exit) as exc_info:
        cmd()
    assert exc_info.value.exit_code == 0


def test_guard_returns_value_on_success():
    @output.guard
    def cmd():
        return 42

    assert cmd() == 42


# --- require_confirmation — единый гейт для деструктивных команд ---


def test_require_confirmation_yes_skips_prompt():
    with patch("hostme.output.typer.confirm") as mock_confirm:
        output.require_confirmation("Снести сайт a.dev", confirm=True)
    mock_confirm.assert_not_called()


def test_require_confirmation_json_without_yes_raises_instead_of_bypassing():
    output.set_json_mode(True)
    with pytest.raises(InvalidArgumentsError, match="--confirm"):
        output.require_confirmation("Снести сайт a.dev", confirm=False)


def test_require_confirmation_non_interactive_without_yes_raises():
    output.set_non_interactive(True)
    with pytest.raises(InvalidArgumentsError, match="--confirm"):
        output.require_confirmation("Снести сайт a.dev", confirm=False)


def test_require_confirmation_without_tty_raises_instead_of_prompting(monkeypatch):
    # Сервер: cron/systemd/doppler run — stdin не терминал, спрашивать некого.
    monkeypatch.setattr(output, "_stdin_is_tty", lambda: False)
    with patch("hostme.output.typer.confirm") as mock_confirm, pytest.raises(InvalidArgumentsError, match="без TTY"):
        output.require_confirmation("Снести сайт a.dev", confirm=False)
    mock_confirm.assert_not_called()


def test_require_confirmation_interactive_confirmed_proceeds():
    with patch("hostme.output.typer.confirm", return_value=True) as mock_confirm:
        output.require_confirmation("Снести сайт a.dev", confirm=False)
    mock_confirm.assert_called_once()


def test_require_confirmation_interactive_declined_raises_aborted():
    with (
        patch("hostme.output.typer.confirm", return_value=False),
        pytest.raises(AbortedError),
    ):
        output.require_confirmation("Снести сайт a.dev", confirm=False)
