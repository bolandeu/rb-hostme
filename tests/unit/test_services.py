from typing import Any
from unittest.mock import patch

import pytest

from hostme.config import BaseDomain, Server, Site, Target
from hostme.core import services
from hostme.core.errors import Aborted, CliError, InvalidArguments


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


def make_server(**overrides) -> Server:
    defaults: dict[str, Any] = {"name": "vps1", "host": "host.example", "user": "root", "ssh_key": "/key"}
    defaults.update(overrides)
    return Server(**defaults)


def make_site(**overrides) -> Site:
    defaults: dict[str, Any] = {"domain": "a.dev", "server": "vps1", "local_path": "/real/site/dist"}
    defaults.update(overrides)
    return Site(**defaults)


# --- confirm_target_action — деплой/teardown/rollback на target (сторонний
# хостинг) обязаны получить явное подтверждение НА КАЖДЫЙ вызов; --json не
# должен давать агенту возможность это подтверждение обойти молча (см. skill
# hostme/SKILL.md).


def test_confirm_target_action_yes_flag_skips_prompt(make_ctx) -> None:
    ctx = make_ctx()
    with patch("hostme.output.typer.confirm") as mock_confirm:
        services.confirm_target_action(ctx, "Деплой x", make_target(), confirm=True)
    mock_confirm.assert_not_called()


def test_confirm_target_action_json_without_yes_raises_instead_of_bypassing(make_ctx) -> None:
    ctx = make_ctx()
    ctx.obj["json"] = True
    with pytest.raises(InvalidArguments, match="--confirm"):
        services.confirm_target_action(ctx, "Деплой x", make_target(), confirm=False)


def test_confirm_target_action_interactive_confirmed_proceeds(make_ctx) -> None:
    ctx = make_ctx()
    with patch("hostme.output.typer.confirm", return_value=True) as mock_confirm:
        services.confirm_target_action(ctx, "Деплой x", make_target(), confirm=False)
    mock_confirm.assert_called_once()


def test_confirm_target_action_interactive_declined_raises_aborted(make_ctx) -> None:
    ctx = make_ctx()
    with (
        patch("hostme.output.typer.confirm", return_value=False),
        pytest.raises(Aborted),
    ):
        services.confirm_target_action(ctx, "Деплой x", make_target(), confirm=False)


# --- maintenance — плейсхолдер "в разработке" вместо содержимого сайта.
# Реестр (local_path) НЕ трогаем — редеплой реальной сборки должен продолжать
# работать как раньше; старое содержимое сохраняется штатным механизмом
# (релиз/target-бэкап) и откатывается через `rollback`.


def test_maintenance_server_site_deploys_placeholder_as_new_release_without_touching_registry(make_ctx) -> None:
    ctx = make_ctx()
    site = make_site(server="vps1")
    server = make_server(name="vps1")
    with (
        patch("hostme.core.services.config.load_sites", return_value=[site]),
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.find_server", return_value=server),
        patch("hostme.core.services.config.save_sites") as mock_save_sites,
        patch("hostme.core.services.webinoly.ensure_releases_layout") as mock_ensure,
        patch("hostme.core.services.webinoly.release_path", return_value="/htdocs/releases/20260101000000"),
        patch("hostme.core.services.rsync_to") as mock_rsync,
        patch("hostme.core.services.webinoly.fix_ownership_path") as mock_chown,
        patch("hostme.core.services.webinoly.switch_release") as mock_switch,
        patch("hostme.core.services.webinoly.prune_releases") as mock_prune,
    ):
        services.set_maintenance(ctx, "a.dev", confirm=True)

    mock_ensure.assert_called_once_with(server, "a.dev")
    mock_rsync.assert_called_once()
    assert mock_rsync.call_args[0][2] == "/htdocs/releases/20260101000000"
    mock_chown.assert_called_once()
    mock_switch.assert_called_once()
    mock_prune.assert_called_once()
    mock_save_sites.assert_not_called()


def test_maintenance_server_site_without_yes_requires_confirmation(make_ctx) -> None:
    ctx = make_ctx()
    # Раньше maintenance на своём сервере не требовал никакого подтверждения
    # вообще — закрытый пробел (см. AskUserQuestion в сессии рефакторинга):
    # теперь own-server ведёт себя так же строго, как target.
    site = make_site(server="vps1")
    server = make_server(name="vps1")
    ctx.obj["json"] = True
    with (
        patch("hostme.core.services.config.load_sites", return_value=[site]),
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.find_server", return_value=server),
        patch("hostme.core.services.webinoly.ensure_releases_layout") as mock_ensure,
        pytest.raises(InvalidArguments, match="--confirm"),
    ):
        services.set_maintenance(ctx, "a.dev", confirm=False)
    mock_ensure.assert_not_called()


def test_maintenance_target_site_requires_confirmation_and_backs_up_first(make_ctx) -> None:
    ctx = make_ctx()
    site = make_site(server="thirdparty")
    target = make_target(name="thirdparty")
    with (
        patch("hostme.core.services.config.load_sites", return_value=[site]),
        patch("hostme.core.services.config.load_servers", return_value=[]),
        patch("hostme.core.services.config.find_server", return_value=None),
        patch("hostme.core.services.config.load_targets", return_value=[target]),
        patch("hostme.core.services.config.find_target", return_value=target),
        patch("hostme.core.services.config.save_sites") as mock_save_sites,
        patch("hostme.output.typer.confirm", return_value=False),
        patch("hostme.core.services._backup_target_before_deploy") as mock_backup,
        patch("hostme.core.services.rsync_to_target") as mock_rsync_target,
        pytest.raises(Aborted),
    ):
        services.set_maintenance(ctx, "a.dev", confirm=False)

    mock_backup.assert_not_called()
    mock_rsync_target.assert_not_called()
    mock_save_sites.assert_not_called()


def test_maintenance_target_site_yes_flag_proceeds_without_prompt(make_ctx) -> None:
    ctx = make_ctx()
    site = make_site(server="thirdparty")
    target = make_target(name="thirdparty")
    with (
        patch("hostme.core.services.config.load_sites", return_value=[site]),
        patch("hostme.core.services.config.load_servers", return_value=[]),
        patch("hostme.core.services.config.find_server", return_value=None),
        patch("hostme.core.services.config.load_targets", return_value=[target]),
        patch("hostme.core.services.config.find_target", return_value=target),
        patch("hostme.core.services.config.save_sites") as mock_save_sites,
        patch("hostme.output.typer.confirm") as mock_confirm,
        patch("hostme.core.services._backup_target_before_deploy") as mock_backup,
        patch("hostme.core.services.rsync_to_target") as mock_rsync_target,
    ):
        services.set_maintenance(ctx, "a.dev", confirm=True)

    mock_confirm.assert_not_called()
    mock_backup.assert_called_once_with(ctx, target)
    mock_rsync_target.assert_called_once()
    mock_save_sites.assert_not_called()


# --- dry-run — деструктивные команды не должны трогать ничего внешнее ---


def test_maintenance_dry_run_does_not_touch_server(make_ctx) -> None:
    ctx = make_ctx()
    site = make_site(server="vps1")
    server = make_server(name="vps1")
    ctx.obj["dry_run"] = True
    with (
        patch("hostme.core.services.config.load_sites", return_value=[site]),
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.find_server", return_value=server),
        patch("hostme.core.services.webinoly.ensure_releases_layout") as mock_ensure,
    ):
        result = services.set_maintenance(ctx, "a.dev", confirm=False)
    mock_ensure.assert_not_called()
    assert result["dry_run"] is True


def test_teardown_dry_run_does_not_touch_server(make_ctx) -> None:
    ctx = make_ctx()
    site = make_site(server="vps1")
    server = make_server(name="vps1")
    ctx.obj["dry_run"] = True
    with (
        patch("hostme.core.services.config.load_sites", return_value=[site]),
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.find_server", return_value=server),
        patch("hostme.core.services.webinoly.delete_site") as mock_delete,
    ):
        result = services.teardown(ctx, "a.dev", confirm=False)
    mock_delete.assert_not_called()
    assert result["dry_run"] is True


# --- teardown/rollback на своём сервере — тот же гейт, что и у target ---


def test_teardown_own_server_json_without_yes_raises_instead_of_bypassing(make_ctx) -> None:
    ctx = make_ctx()
    # Раньше --json на own-server teardown молча обходил подтверждение —
    # закрытый пробел безопасности (см. аудит рефакторинга).
    site = make_site(server="vps1")
    server = make_server(name="vps1")
    ctx.obj["json"] = True
    with (
        patch("hostme.core.services.config.load_sites", return_value=[site]),
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.find_server", return_value=server),
        patch("hostme.core.services.webinoly.delete_site") as mock_delete,
        pytest.raises(InvalidArguments, match="--confirm"),
    ):
        services.teardown(ctx, "a.dev", confirm=False)
    mock_delete.assert_not_called()


def test_teardown_own_server_yes_flag_proceeds(make_ctx) -> None:
    ctx = make_ctx()
    site = make_site(server="vps1")
    server = make_server(name="vps1")
    with (
        patch("hostme.core.services.config.load_sites", return_value=[site]),
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.find_server", return_value=server),
        patch("hostme.core.services.config.save_sites") as mock_save_sites,
        patch("hostme.core.services.webinoly.delete_site") as mock_delete,
    ):
        result = services.teardown(ctx, "a.dev", confirm=True)
    mock_delete.assert_called_once()
    mock_save_sites.assert_called_once()
    assert result["domain"] == "a.dev"


def test_rollback_own_server_without_yes_requires_confirmation(make_ctx) -> None:
    ctx = make_ctx()
    # Раньше rollback на своём сервере вообще не спрашивал подтверждения.
    site = make_site(server="vps1")
    server = make_server(name="vps1")
    ctx.obj["non_interactive"] = True
    with (
        patch("hostme.core.services.config.load_sites", return_value=[site]),
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.find_server", return_value=server),
        patch("hostme.core.services.webinoly.list_releases", return_value=["r0", "r1"]),
        patch("hostme.core.services.webinoly.current_release", return_value="r1"),
        patch("hostme.core.services.webinoly.switch_release") as mock_switch,
        pytest.raises(InvalidArguments, match="--confirm"),
    ):
        services.rollback(ctx, "a.dev", confirm=False)
    mock_switch.assert_not_called()


# --- remove_domain — парная команда к domain add ---


def test_remove_domain_not_registered_raises() -> None:
    server = make_server(base_domains=[BaseDomain(name="a.dev", default=True)])
    with (
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        pytest.raises(CliError, match="не зарегистрирован"),
    ):
        services.remove_domain("b.dev")


def test_remove_domain_removes_from_server() -> None:
    server = make_server(base_domains=[BaseDomain(name="a.dev", default=True), BaseDomain(name="b.dev")])
    with (
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.save_servers") as mock_save,
    ):
        result = services.remove_domain("b.dev")
    assert result["domain"] == "b.dev"
    assert [d.name for d in server.base_domains] == ["a.dev"]
    mock_save.assert_called_once_with([server])


def test_remove_domain_promotes_new_default_when_default_removed() -> None:
    server = make_server(base_domains=[BaseDomain(name="a.dev", default=True), BaseDomain(name="b.dev")])
    with (
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.save_servers"),
    ):
        services.remove_domain("a.dev")
    assert server.base_domains == [BaseDomain(name="b.dev", default=True)]


# --- require_unique_name — servers.yaml и targets.yaml делят пространство имён ---


def test_require_unique_name_rejects_existing_server() -> None:
    server = make_server(name="vps1")
    with (
        patch("hostme.core.services.config.load_servers", return_value=[server]),
        patch("hostme.core.services.config.load_targets", return_value=[]),
        pytest.raises(CliError, match="сервером"),
    ):
        services.require_unique_name("vps1")


def test_require_unique_name_rejects_existing_target() -> None:
    target = make_target(name="ext1")
    with (
        patch("hostme.core.services.config.load_servers", return_value=[]),
        patch("hostme.core.services.config.load_targets", return_value=[target]),
        pytest.raises(CliError, match="target"),
    ):
        services.require_unique_name("ext1")


# --- doctor — не должен обращаться к удалённым серверам ---


def test_doctor_reports_ok_when_binaries_and_config_present() -> None:
    with (
        patch("hostme.core.services.config.CONFIG_DIR") as mock_dir,
        patch("hostme.core.services.config.load_servers", return_value=[]),
        patch("hostme.core.services.config.load_targets", return_value=[]),
        patch("hostme.core.services.config.load_sites", return_value=[]),
        patch("hostme.core.services.shutil.which", return_value="/usr/bin/tool"),
    ):
        mock_dir.exists.return_value = True
        mock_dir.stat.return_value.st_mode = 0o700
        result = services.run_doctor()
    assert result["healthy"] is True
    names = [c["name"] for c in result["checks"]]
    assert "ssh" in names
    assert "rsync" in names


def test_doctor_fails_when_required_binary_missing() -> None:
    with (
        patch("hostme.core.services.config.CONFIG_DIR") as mock_dir,
        patch("hostme.core.services.config.load_servers", return_value=[]),
        patch("hostme.core.services.config.load_targets", return_value=[]),
        patch("hostme.core.services.config.load_sites", return_value=[]),
        patch("hostme.core.services.shutil.which", return_value=None),
    ):
        mock_dir.exists.return_value = True
        mock_dir.stat.return_value.st_mode = 0o700
        result = services.run_doctor()
    assert result["healthy"] is False


def test_doctor_requires_lftp_only_when_ftp_targets_registered() -> None:
    target = make_target(name="ext1", connection="sftp")
    with (
        patch("hostme.core.services.config.CONFIG_DIR") as mock_dir,
        patch("hostme.core.services.config.load_servers", return_value=[]),
        patch("hostme.core.services.config.load_targets", return_value=[target]),
        patch("hostme.core.services.config.load_sites", return_value=[]),
        patch("hostme.core.services.shutil.which", side_effect=lambda b: None if b == "lftp" else "/usr/bin/" + b),
    ):
        mock_dir.exists.return_value = True
        mock_dir.stat.return_value.st_mode = 0o700
        result = services.run_doctor()
    checks_by_name = {c["name"]: c for c in result["checks"]}
    assert "lftp" in checks_by_name
    assert checks_by_name["lftp"]["status"] == "fail"
    assert result["healthy"] is False
