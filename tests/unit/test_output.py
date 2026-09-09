import json

import pytest

from hostme import output


@pytest.fixture(autouse=True)
def reset_json_mode():
    output.set_json_mode(False)
    yield
    output.set_json_mode(False)


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


def test_error_plain_text_exits_one(capsys):
    with pytest.raises(SystemExit) as exc_info:
        output.error("bad thing")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "bad thing" in captured.err


def test_error_json_exits_one(capsys):
    output.set_json_mode(True)
    with pytest.raises(SystemExit) as exc_info:
        output.error("bad thing", domain="a.dev")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    data = json.loads(captured.err)
    assert data == {"ok": False, "error": "bad thing", "domain": "a.dev"}


def test_json_mode_toggle():
    assert output.is_json_mode() is False
    output.set_json_mode(True)
    assert output.is_json_mode() is True
