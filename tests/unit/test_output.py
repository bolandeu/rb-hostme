import json
from unittest.mock import patch

import pytest
import typer

from hostme import output
from hostme.core.errors import Aborted, InvalidArguments, StateError


def test_success_plain_text(capsys, make_ctx):
    ctx = make_ctx()
    output.success(ctx, "done")
    captured = capsys.readouterr()
    assert "done" in captured.out


def test_success_json(capsys, make_ctx):
    ctx = make_ctx()
    ctx.obj["json"] = True
    output.success(ctx, "done", domain="a.dev")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data == {"ok": True, "message": "done", "domain": "a.dev"}


def test_progress_plain_text(capsys, make_ctx):
    ctx = make_ctx()
    output.progress(ctx, "hello")
    captured = capsys.readouterr()
    assert "hello" in captured.out


def test_progress_json_keeps_stdout_single_object(capsys, make_ctx):
    ctx = make_ctx()
    # --json: stdout — ровно один объект (итог), прогресс — в stderr.
    ctx.obj["json"] = True
    output.progress(ctx, "Заливаю файлы...")
    output.success(ctx, "done")
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"ok": True, "message": "done"}
    assert "Заливаю файлы..." in captured.err


def test_error_plain_text_goes_to_stderr_with_code_from_error(capsys, make_ctx):
    ctx = make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        output.emit_error(ctx, StateError("bad thing", action="сделай так"))
    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bad thing" in captured.err
    assert "сделай так" in captured.err


def test_error_json_uses_conventions_envelope_on_stdout(capsys, make_ctx):
    ctx = make_ctx()
    # conventions.md: под --json конверт ошибки — в stdout (один поток для
    # парсинга), ok:false + exit-код говорят, что это ошибка.
    ctx.obj["json"] = True
    with pytest.raises(typer.Exit) as exc_info:
        output.emit_error(ctx, StateError("bad thing"))
    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data == {"ok": False, "error": {"code": "ERROR", "message": "bad thing"}}


def test_error_json_includes_code_and_action_for_subclasses(capsys, make_ctx):
    ctx = make_ctx()
    ctx.obj["json"] = True
    exc = InvalidArguments("--connection должен быть ssh/ftp/sftp", action="Повтори с корректным значением.")
    with pytest.raises(typer.Exit) as exc_info:
        output.emit_error(ctx, exc)
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


def test_non_interactive_toggle(make_ctx):
    ctx = make_ctx()
    assert output.is_non_interactive(ctx) is False
    ctx.obj["non_interactive"] = True
    assert output.is_non_interactive(ctx) is True


def test_json_mode_implies_non_interactive(make_ctx):
    ctx = make_ctx()
    # --json подразумевает агента на другом конце — как и --non-interactive,
    # не должно виснуть на typer.confirm() без stdin.
    ctx.obj["json"] = True
    assert output.is_non_interactive(ctx) is True


def test_dry_run_toggle(make_ctx):
    ctx = make_ctx()
    assert output.is_dry_run(ctx) is False
    ctx.obj["dry_run"] = True
    assert output.is_dry_run(ctx) is True


def test_quiet_suppresses_human_but_not_json(capsys, make_ctx):
    ctx = make_ctx()
    ctx.obj["quiet"] = True
    output.success(ctx, "тихо", domain="a.dev")
    assert capsys.readouterr().out == ""
    ctx.obj["json"] = True
    output.success(ctx, "тихо", domain="a.dev")
    assert json.loads(capsys.readouterr().out)["domain"] == "a.dev"
    ctx.obj["quiet"] = False


def test_json_success_is_single_line_and_keeps_unicode(capsys, make_ctx):
    ctx = make_ctx()
    ctx.obj["json"] = True
    output.success(ctx, "Готово: " + "x" * 300, path="/очень/длинный/путь")
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert "Готово" in out  # ensure_ascii=False


# --- guard — любая команда либо отдаёт результат, либо конверт ошибки ---


def test_guard_maps_hostme_error_to_its_exit_code(capsys, make_ctx):
    ctx = make_ctx()

    @output.guard
    def cmd(ctx):
        raise InvalidArguments("плохо")

    with pytest.raises(typer.Exit) as exc_info:
        cmd(ctx)
    assert exc_info.value.exit_code == 2
    assert "плохо" in capsys.readouterr().err


def test_guard_turns_unknown_exception_into_unexpected_envelope(capsys, make_ctx):
    ctx = make_ctx()
    ctx.obj["json"] = True

    @output.guard
    def cmd(ctx):
        raise KeyError("boom")

    with pytest.raises(typer.Exit) as exc_info:
        cmd(ctx)
    assert exc_info.value.exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["error"]["code"] == "UNEXPECTED"
    assert "KeyError" in data["error"]["message"]
    assert "--verbose" in data["error"]["action"]


def test_guard_passes_controlled_exit_through(make_ctx):
    ctx = make_ctx()

    @output.guard
    def cmd(ctx):
        raise typer.Exit(code=0)

    with pytest.raises(typer.Exit) as exc_info:
        cmd(ctx)
    assert exc_info.value.exit_code == 0


def test_guard_returns_value_on_success(make_ctx):
    ctx = make_ctx()

    @output.guard
    def cmd(ctx):
        return 42

    assert cmd(ctx) == 42


# --- require_confirmation — единый гейт для деструктивных команд ---


def test_require_confirmation_yes_skips_prompt(make_ctx):
    ctx = make_ctx()
    with patch("hostme.output.typer.confirm") as mock_confirm:
        output.require_confirmation(ctx, "Снести сайт a.dev", confirm=True)
    mock_confirm.assert_not_called()


def test_require_confirmation_json_without_yes_raises_instead_of_bypassing(make_ctx):
    ctx = make_ctx()
    ctx.obj["json"] = True
    with pytest.raises(InvalidArguments, match="--confirm"):
        output.require_confirmation(ctx, "Снести сайт a.dev", confirm=False)


def test_require_confirmation_non_interactive_without_yes_raises(make_ctx):
    ctx = make_ctx()
    ctx.obj["non_interactive"] = True
    with pytest.raises(InvalidArguments, match="--confirm"):
        output.require_confirmation(ctx, "Снести сайт a.dev", confirm=False)


def test_require_confirmation_without_tty_raises_instead_of_prompting(monkeypatch, make_ctx):
    ctx = make_ctx()
    # Сервер: cron/systemd/doppler run — stdin не терминал, спрашивать некого.
    monkeypatch.setattr(output, "_stdin_is_tty", lambda: False)
    with patch("hostme.output.typer.confirm") as mock_confirm, pytest.raises(InvalidArguments, match="без TTY"):
        output.require_confirmation(ctx, "Снести сайт a.dev", confirm=False)
    mock_confirm.assert_not_called()


def test_require_confirmation_interactive_confirmed_proceeds(make_ctx):
    ctx = make_ctx()
    with patch("hostme.output.typer.confirm", return_value=True) as mock_confirm:
        output.require_confirmation(ctx, "Снести сайт a.dev", confirm=False)
    mock_confirm.assert_called_once()


def test_require_confirmation_interactive_declined_raises_aborted(make_ctx):
    ctx = make_ctx()
    with (
        patch("hostme.output.typer.confirm", return_value=False),
        pytest.raises(Aborted),
    ):
        output.require_confirmation(ctx, "Снести сайт a.dev", confirm=False)
