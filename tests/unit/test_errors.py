from hostme.errors import ConfirmationRequiredError, HostmeError, InvalidArgumentsError


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


def test_confirmation_required_error_exit_code_two():
    exc = ConfirmationRequiredError("нужен --yes")
    assert exc.code == "CONFIRMATION_REQUIRED"
    assert exc.exit_code == 2
    assert isinstance(exc, HostmeError)
