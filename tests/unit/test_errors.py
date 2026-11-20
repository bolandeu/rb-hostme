from rb_hostme.core.errors import (
    Aborted,
    CliError,
    InvalidArguments,
    ProviderError,
    StateError,
)


def test_state_error_defaults():
    exc = StateError("boom")
    assert exc.message == "boom"
    assert exc.code == "ERROR"
    assert exc.exit_code == 1
    assert exc.action is None


def test_state_error_with_action():
    exc = StateError("boom", action="Попробуй снова.")
    assert exc.action == "Попробуй снова."


def test_invalid_arguments_error_exit_code_two():
    exc = InvalidArguments("плохой флаг")
    assert exc.code == "INVALID_ARGUMENTS"
    assert exc.exit_code == 2
    assert isinstance(exc, CliError)


def test_provider_error_exit_code_five_and_names_provider():
    class LftpError(ProviderError):
        provider = "lftp"

    exc = LftpError("упал")
    assert exc.code == "PROVIDER_ERROR"
    assert exc.exit_code == 5
    assert exc.to_dict() == {"code": "PROVIDER_ERROR", "message": "упал", "provider": "lftp"}


def test_aborted_exit_code_one():
    # UNEXPECTED больше не отдельный класс: его строит output.guard (test_output.py, guard-тесты).
    assert Aborted("Снос").code == "ABORTED"
    assert Aborted("Снос").exit_code == 1


def test_to_dict_includes_action_only_when_set():
    assert StateError("boom").to_dict() == {"code": "ERROR", "message": "boom"}
    assert StateError("boom", action="fix").to_dict() == {"code": "ERROR", "message": "boom", "action": "fix"}
