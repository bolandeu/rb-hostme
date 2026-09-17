from hostme.core.errors import (
    AbortedError,
    HostmeError,
    InvalidArgumentsError,
    ProviderError,
    UnexpectedError,
)


def test_hostme_error_defaults():
    exc = HostmeError("boom")
    assert exc.message == "boom"
    assert exc.code == "ERROR"
    assert exc.exit_code == 1
    assert exc.action is None


def test_hostme_error_with_action():
    exc = HostmeError("boom", action="Попробуй снова.")
    assert exc.action == "Попробуй снова."


def test_invalid_arguments_error_exit_code_two():
    exc = InvalidArgumentsError("плохой флаг")
    assert exc.code == "INVALID_ARGUMENTS"
    assert exc.exit_code == 2
    assert isinstance(exc, HostmeError)


def test_provider_error_exit_code_five_and_names_provider():
    class LftpError(ProviderError):
        provider = "lftp"

    exc = LftpError("упал")
    assert exc.code == "PROVIDER_ERROR"
    assert exc.exit_code == 5
    assert exc.to_dict() == {"code": "PROVIDER_ERROR", "message": "упал", "provider": "lftp"}


def test_aborted_and_unexpected_exit_code_one():
    assert AbortedError("Снос").code == "ABORTED"
    assert AbortedError("Снос").exit_code == 1
    exc = UnexpectedError(KeyError("x"))
    assert exc.code == "UNEXPECTED"
    assert exc.exit_code == 1
    assert "KeyError" in exc.message
    assert "--verbose" in (exc.action or "")


def test_to_dict_includes_action_only_when_set():
    assert HostmeError("boom").to_dict() == {"code": "ERROR", "message": "boom"}
    assert HostmeError("boom", action="fix").to_dict() == {"code": "ERROR", "message": "boom", "action": "fix"}
