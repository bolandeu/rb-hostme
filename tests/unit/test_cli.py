from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from hostme import output
from hostme.cli import (
    _confirm_target_action,
    _translate_argv,
    app,
    main,
    maintenance,
    root,
)
from hostme.config import Server, Site, Target
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


# maintenance — плейсхолдер "в разработке" вместо содержимого сайта, встроенный
# в hostme (не нужно таскать отдельную папку). Реестр (local_path) НЕ трогаем —
# редеплой реальной сборки должен продолжать работать как раньше; старое
# содержимое сохраняется штатным механизмом (релиз/target-бэкап) и откатывается
# через `rollback`.


def make_server(**overrides) -> Server:
    defaults = {"name": "vps1", "host": "host.example", "user": "root", "ssh_key": "/key"}
    defaults.update(overrides)
    return Server(**defaults)


def make_site(**overrides) -> Site:
    defaults = {"domain": "a.dev", "server": "vps1", "local_path": "/real/site/dist"}
    defaults.update(overrides)
    return Site(**defaults)


def test_maintenance_server_site_deploys_placeholder_as_new_release_without_touching_registry() -> None:
    site = make_site(server="vps1")
    server = make_server(name="vps1")
    with (
        patch("hostme.cli.config.load_sites", return_value=[site]),
        patch("hostme.cli.config.load_servers", return_value=[server]),
        patch("hostme.cli.config.find_server", return_value=server),
        patch("hostme.cli.config.save_sites") as mock_save_sites,
        patch("hostme.cli.webinoly.ensure_releases_layout") as mock_ensure,
        patch("hostme.cli.webinoly.release_path", return_value="/htdocs/releases/20260101000000"),
        patch("hostme.cli.rsync_to") as mock_rsync,
        patch("hostme.cli.webinoly.fix_ownership_path") as mock_chown,
        patch("hostme.cli.webinoly.switch_release") as mock_switch,
        patch("hostme.cli.webinoly.prune_releases") as mock_prune,
    ):
        maintenance("a.dev", yes=False)

    mock_ensure.assert_called_once_with(server, "a.dev")
    mock_rsync.assert_called_once()
    assert mock_rsync.call_args[0][2] == "/htdocs/releases/20260101000000"
    mock_chown.assert_called_once()
    mock_switch.assert_called_once()
    mock_prune.assert_called_once()
    mock_save_sites.assert_not_called()


def test_maintenance_target_site_requires_confirmation_and_backs_up_first() -> None:
    site = make_site(server="thirdparty")
    target = make_target(name="thirdparty")
    output.set_json_mode(False)
    with (
        patch("hostme.cli.config.load_sites", return_value=[site]),
        patch("hostme.cli.config.load_servers", return_value=[]),
        patch("hostme.cli.config.find_server", return_value=None),
        patch("hostme.cli.config.load_targets", return_value=[target]),
        patch("hostme.cli.config.find_target", return_value=target),
        patch("hostme.cli.config.save_sites") as mock_save_sites,
        patch("hostme.cli.typer.confirm", return_value=False),
        patch("hostme.cli._backup_target_before_deploy") as mock_backup,
        patch("hostme.cli.rsync_to_target") as mock_rsync_target,
        pytest.raises(typer.Exit),
    ):
        maintenance("a.dev", yes=False)

    mock_backup.assert_not_called()
    mock_rsync_target.assert_not_called()
    mock_save_sites.assert_not_called()


def test_maintenance_target_site_yes_flag_proceeds_without_prompt() -> None:
    site = make_site(server="thirdparty")
    target = make_target(name="thirdparty")
    with (
        patch("hostme.cli.config.load_sites", return_value=[site]),
        patch("hostme.cli.config.load_servers", return_value=[]),
        patch("hostme.cli.config.find_server", return_value=None),
        patch("hostme.cli.config.load_targets", return_value=[target]),
        patch("hostme.cli.config.find_target", return_value=target),
        patch("hostme.cli.config.save_sites") as mock_save_sites,
        patch("hostme.cli.typer.confirm") as mock_confirm,
        patch("hostme.cli._backup_target_before_deploy") as mock_backup,
        patch("hostme.cli.rsync_to_target") as mock_rsync_target,
    ):
        maintenance("a.dev", yes=True)

    mock_confirm.assert_not_called()
    mock_backup.assert_called_once_with(target)
    mock_rsync_target.assert_called_once()
    mock_save_sites.assert_not_called()
