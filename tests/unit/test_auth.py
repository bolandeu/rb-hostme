"""`hostme auth status` — форма отчёта (стандарт §8) и приоритет env над keychain (§13)."""

import json
from unittest.mock import patch

import keyring.errors
import pytest
from typer.testing import CliRunner

from hostme import config, output
from hostme.cli import _translate_argv, app
from hostme.credentials import manager

runner = CliRunner()

ENTRY_KEYS = {"provider", "required", "fields", "source", "source_ref", "status", "expires_at", "quota", "message"}


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "hostme"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "SERVERS_FILE", config_dir / "servers.yaml")
    monkeypatch.setattr(config, "SITES_FILE", config_dir / "sites.yaml")
    monkeypatch.delenv("HOSTME_DEPLOY_CLIENT_RU_PASSWORD", raising=False)
    yield
    output.set_json_mode(False)


def _status(*args: str):
    result = runner.invoke(app, _translate_argv(["auth", "status", "--json", *args]))
    return result.exit_code, json.loads(result.output)


def _server(tmp_path, key_exists=True):
    key = tmp_path / "id_test"
    if key_exists:
        key.write_text("key")
    return config.Server(name="vps1", host="203.0.113.10", user="root", ssh_key=str(key))


def _target(**overrides):
    fields = {"name": "client.ru", "connection": "sftp", "host": "sftp.host", "user": "u1", "password": "s3cret"}
    fields.update(overrides)
    return config.Target(**fields)


def test_empty_registry_reports_no_credentials_and_exits_zero():
    code, data = _status()
    assert code == 0
    assert data["ok"] is True
    assert data["tool"] == "hostme"
    assert set(data) == {"ok", "tool", "version", "checked_at", "credentials"}
    assert data["credentials"] == []
    assert data["checked_at"].endswith("Z")


def test_shape_without_check(tmp_path):
    config.save_servers([_server(tmp_path)])
    config.save_targets([_target()])
    code, data = _status()
    assert code == 0
    by_provider = {e["provider"]: e for e in data["credentials"]}
    assert set(by_provider) == {"server:vps1", "target:client.ru"}
    for entry in data["credentials"]:
        assert set(entry) == ENTRY_KEYS
        assert entry["status"] == "unchecked"
        assert entry["required"] is True
    assert by_provider["server:vps1"]["source"] == "file"
    target = by_provider["target:client.ru"]
    assert target["source"] == "keychain"
    assert target["source_ref"] == "keychain service hostme:client.ru"
    assert "s3cret" not in json.dumps(data)


def test_env_wins_over_keychain(monkeypatch):
    config.save_targets([_target()])
    monkeypatch.setenv("HOSTME_DEPLOY_CLIENT_RU_PASSWORD", "from-env")
    _, data = _status()
    entry = data["credentials"][0]
    assert entry["source"] == "env"
    assert entry["source_ref"] == "HOSTME_DEPLOY_CLIENT_RU_PASSWORD"
    assert config.load_targets()[0].password == "from-env"


def test_missing_key_and_password_exit_3(tmp_path, fake_keyring):
    config.save_servers([_server(tmp_path, key_exists=False)])
    config.save_targets([_target()])
    fake_keyring.store.clear()
    code, data = _status()
    assert code == 3
    assert data["ok"] is False
    assert data["error"]["code"] == "CREDENTIALS_UNHEALTHY"
    statuses = {e["provider"]: (e["source"], e["status"]) for e in data["credentials"]}
    assert statuses == {"server:vps1": ("missing", "missing"), "target:client.ru": ("missing", "missing")}
    target = next(e for e in data["credentials"] if e["provider"] == "target:client.ru")
    assert target["source_ref"] == "HOSTME_DEPLOY_CLIENT_RU_PASSWORD or keychain service hostme:client.ru"


def test_check_maps_probe_results_and_scrubs_secret(tmp_path):
    config.save_servers([_server(tmp_path)])
    config.save_targets([_target()])
    with (
        patch("hostme.providers.ssh.check_server", return_value=("ok", None)),
        patch("hostme.providers.ftp.check_target", return_value=("invalid", "530 Login incorrect for s3cret")),
    ):
        code, data = _status("--check")
    assert code == 3
    by_provider = {e["provider"]: e for e in data["credentials"]}
    assert by_provider["server:vps1"]["status"] == "ok"
    assert by_provider["target:client.ru"]["status"] == "invalid"
    assert by_provider["target:client.ru"]["message"] == "530 Login incorrect for ***"


def test_provider_filter_and_unknown_provider(tmp_path):
    config.save_servers([_server(tmp_path)])
    config.save_targets([_target()])
    code, data = _status("--provider", "target:client.ru")
    assert code == 0
    assert [e["provider"] for e in data["credentials"]] == ["target:client.ru"]
    code, data = _status("--provider", "nope")
    assert code == 2
    assert data["error"]["code"] == "INVALID_ARGUMENTS"


def test_domain_auth_still_routes_to_http_auth():
    assert _translate_argv(["a.dev", "auth", "--off"]) == ["http-auth", "a.dev", "--off"]
    assert _translate_argv(["auth", "status", "--json"]) == ["--json", "auth", "status"]


# --- headless: без keychain всё работает через env ---------------------------


class _NoKeyring:
    errors = keyring.errors

    def get_password(self, service, username):
        raise keyring.errors.NoKeyringError("no backend")

    def set_password(self, service, username, password):
        raise keyring.errors.NoKeyringError("no backend")

    def delete_password(self, service, username):
        raise keyring.errors.NoKeyringError("no backend")


def test_headless_env_password_needs_no_keychain(monkeypatch):
    monkeypatch.setattr(manager, "keyring", _NoKeyring())
    monkeypatch.setenv("HOSTME_DEPLOY_CLIENT_RU_PASSWORD", "from-env")
    # target add без --password на сервере: пароль из env, keychain не трогается
    config.save_targets([_target(password=manager.get_secret("client.ru"))])
    assert config.load_targets()[0].password == "from-env"
    code, data = _status()
    assert code == 0
    assert data["credentials"][0]["source"] == "env"
    manager.delete_secret("client.ru")  # без хранилища — не ошибка


def test_headless_without_env_reports_missing(monkeypatch):
    config.save_targets([_target()])
    monkeypatch.setattr(manager, "keyring", _NoKeyring())
    assert config.load_targets()[0].password is None
    code, data = _status()
    assert code == 3
    assert data["credentials"][0]["status"] == "missing"
