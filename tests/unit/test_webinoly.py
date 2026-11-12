import base64
import shlex
from unittest.mock import patch

import pytest

from hostme.config import Server
from hostme.providers import webinoly
from hostme.providers.ssh import RemoteResult

SERVER = Server(name="vps1", host="1.2.3.4", user="root", ssh_key="~/.ssh/id")


def ok(stdout: str = "") -> RemoteResult:
    return RemoteResult(stdout=stdout, stderr="", returncode=0)


def fail(stderr: str = "boom") -> RemoteResult:
    return RemoteResult(stdout="", stderr=stderr, returncode=1)


LIST_OUTPUT = """
 + antagorapp.ru (HTML)
 + test1.antagorapp.ru (HTML)(SSL)
 + test2.antagorapp.ru (PHP)

Found: 3 sites
"""

EMPTY_LIST_OUTPUT = """

[Empty] No sites were found!
"""


def test_parse_site_list_multiple_sites():
    sites = webinoly.parse_site_list(LIST_OUTPUT)
    assert [s.domain for s in sites] == [
        "antagorapp.ru",
        "test1.antagorapp.ru",
        "test2.antagorapp.ru",
    ]
    assert sites[1].tags == ["HTML", "SSL"]
    assert sites[2].is_php is True
    assert sites[0].is_php is False


def test_parse_site_list_empty():
    assert webinoly.parse_site_list(EMPTY_LIST_OUTPUT) == []


def test_parse_site_list_multiple_adjacent_parens_no_ssl():
    # Реальный формат Webinoly (подтверждено на sites-first-beget, 2026-09-09):
    # "(HTML)(NoSSL)" - отдельные скобки подряд, без запятой между ними.
    output = " + e2edebug2.antagorapp.ru (HTML)(NoSSL) \n\nFound: 1 sites\n"
    sites = webinoly.parse_site_list(output)
    assert len(sites) == 1
    assert sites[0].domain == "e2edebug2.antagorapp.ru"
    assert sites[0].tags == ["HTML", "NoSSL"]
    assert sites[0].has_ssl is False


def test_site_info_has_ssl_default_true_without_nossl_tag():
    site = webinoly.SiteInfo(domain="a.dev", tags=["HTML"])
    assert site.has_ssl is True


def test_site_info_has_ssl_false_with_nossl_tag():
    site = webinoly.SiteInfo(domain="a.dev", tags=["HTML", "NoSSL"])
    assert site.has_ssl is False


def test_is_installed_true():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok("/usr/bin/webinoly")):
        assert webinoly.is_installed(SERVER) is True


def test_is_installed_false():
    with patch("hostme.providers.webinoly.run_remote", return_value=fail()):
        assert webinoly.is_installed(SERVER) is False


def test_install_skips_when_already_installed():
    with patch("hostme.providers.webinoly.run_remote", side_effect=[ok(), ok("Webinoly version: 1.21.2")]) as mock_run:
        webinoly.install(SERVER)

    assert mock_run.call_count == 2
    second_call_command = mock_run.call_args_list[1][0][1]
    assert second_call_command == "webinoly -version"


def test_install_runs_installer_when_missing():
    with patch("hostme.providers.webinoly.run_remote", side_effect=[fail(), ok(), ok("")]) as mock_run:
        webinoly.install(SERVER, mode="-php")

    install_command = mock_run.call_args_list[1][0][1]
    assert "bash weby -php" in install_command
    assert webinoly.INSTALL_URL in install_command


def test_install_reports_success_when_post_condition_holds():
    # Установщик напечатал успех, и все три команды стека на сервере есть.
    with patch("hostme.providers.webinoly.run_remote", side_effect=[fail(), ok("installed successfully"), ok("")]):
        result = webinoly.install(SERVER)

    assert result.ok is True


def test_install_raises_when_webinoly_nginx_and_php_are_absent():
    # Случай сисадмина: webinoly.tar скачался на ~12 KB из 829440 B, tar выдал
    # Unexpected EOF, а weby без set -e всё равно напечатал "installed successfully".
    install_output = ok("installed successfully\napp_purge: command not found")
    with (
        patch(
            "hostme.providers.webinoly.run_remote",
            side_effect=[fail(), install_output, ok("webinoly\nnginx\nphp\n"), ok("")],
        ),
        pytest.raises(webinoly.WebinolyError, match="неполная") as raised,
    ):
        webinoly.install(SERVER)

    message = str(raised.value)
    assert "webinoly, nginx, php" in message
    assert "webinoly.tar" in message
    assert "webinoly -version" in message


def test_update_webinoly():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.update_webinoly(SERVER)
    assert mock_run.call_args[0][1] == "sudo webinoly -update"


def test_update_webinoly_raises_on_failure():
    with (
        patch("hostme.providers.webinoly.run_remote", return_value=fail("connection reset")),
        pytest.raises(webinoly.WebinolyError, match="connection reset"),
    ):
        webinoly.update_webinoly(SERVER)


def test_install_raises_on_failure():
    with (
        patch("hostme.providers.webinoly.run_remote", side_effect=[fail(), fail("network unreachable")]),
        pytest.raises(webinoly.WebinolyError, match="network unreachable"),
    ):
        webinoly.install(SERVER)


def test_list_sites_uses_run_remote():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok(LIST_OUTPUT)) as mock_run:
        sites = webinoly.list_sites(SERVER)

    mock_run.assert_called_once_with(SERVER, "sudo site -list")
    assert len(sites) == 3


def test_site_exists_true():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok(LIST_OUTPUT)):
        assert webinoly.site_exists(SERVER, "test1.antagorapp.ru") is True


def test_site_exists_false():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok(EMPTY_LIST_OUTPUT)):
        assert webinoly.site_exists(SERVER, "missing.dev") is False


def test_create_site_html():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.create_site(SERVER, "a.dev", "html")
    assert mock_run.call_args_list[0][0][1] == "sudo site a.dev -html"


def test_create_site_php():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.create_site(SERVER, "a.dev", "php")
    assert mock_run.call_args_list[0][0][1] == "sudo site a.dev -php"


def test_create_site_writes_placeholder_index():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.create_site(SERVER, "a.dev", "html")
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert any("index.html" in cmd for cmd in commands)
    assert any("chown" in cmd for cmd in commands)


def test_create_site_php_placeholder_uses_index_php():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.create_site(SERVER, "a.dev", "php")
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert any("index.php" in cmd for cmd in commands)


def test_create_site_raises_on_failure():
    with (
        patch("hostme.providers.webinoly.run_remote", return_value=fail("domain taken")),
        pytest.raises(webinoly.WebinolyError, match="domain taken"),
    ):
        webinoly.create_site(SERVER, "a.dev", "html")


def test_enable_ssl_plain():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.enable_ssl(SERVER, "a.dev")
    assert mock_run.call_args[0][1] == "sudo site a.dev -ssl=on"


def test_enable_ssl_wildcard():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.enable_ssl(SERVER, "a.dev", wildcard=True)
    assert mock_run.call_args[0][1] == "sudo site a.dev -ssl=on -wildcard"


def test_enable_ssl_add_to_wildcard():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.enable_ssl(SERVER, "sub.a.dev", add_to_wildcard="a.dev")
    assert mock_run.call_args[0][1] == "sudo site sub.a.dev -ssl=on -add-to-wildcard=a.dev"


def test_enable_ssl_raises_on_failure():
    with (
        patch("hostme.providers.webinoly.run_remote", return_value=fail("dns not ready")),
        pytest.raises(webinoly.WebinolyError, match="dns not ready"),
    ):
        webinoly.enable_ssl(SERVER, "a.dev")


def test_delete_site_default_revokes_ssl():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.delete_site(SERVER, "a.dev")
    assert mock_run.call_args[0][1] == "sudo site a.dev -delete=force -revoke=on"


def test_delete_site_without_revoke():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.delete_site(SERVER, "a.dev", revoke_ssl=False)
    assert mock_run.call_args[0][1] == "sudo site a.dev -delete=force -revoke=off"


def test_delete_site_raises_on_failure():
    with (
        patch("hostme.providers.webinoly.run_remote", return_value=fail("not found")),
        pytest.raises(webinoly.WebinolyError, match="not found"),
    ):
        webinoly.delete_site(SERVER, "a.dev")


def test_webroot_path():
    assert webinoly.webroot("example.com") == "/var/www/example.com/htdocs"


def test_fix_ownership():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.fix_ownership(SERVER, "a.dev")
    assert mock_run.call_args[0][1] == "sudo chown -R www-data:www-data /var/www/a.dev/htdocs"


def test_fix_ownership_raises_on_failure():
    with (
        patch("hostme.providers.webinoly.run_remote", return_value=fail("permission denied")),
        pytest.raises(webinoly.WebinolyError, match="permission denied"),
    ):
        webinoly.fix_ownership(SERVER, "a.dev")


# --- httpauth / redirects: экранирование пароля/аргументов через shlex.quote ---
# критично для безопасности (см. docs/usage/security.md) — регрессия здесь означает
# command injection через --pass/--user/--redirect.


def test_set_http_auth_escapes_credentials():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.set_http_auth(SERVER, "a.dev", "bob", "pass; rm -rf /")
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert len(commands) == 2
    # Ключевая проверка безопасности: shell должен распарсить -add=... как ОДИН
    # аргумент, а не оборвать команду на ";" (это и была бы command injection).
    tokens = shlex.split(commands[0])
    assert tokens == ["sudo", "httpauth", "a.dev", "-add=[bob,pass; rm -rf /]"]
    assert commands[1] == "sudo httpauth a.dev -path=/"


def test_set_http_auth_raises_if_add_fails():
    with (
        patch("hostme.providers.webinoly.run_remote", return_value=fail("invalid option")),
        pytest.raises(webinoly.WebinolyError, match="invalid option"),
    ):
        webinoly.set_http_auth(SERVER, "a.dev", "bob", "secret")


def test_disable_http_auth():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.disable_http_auth(SERVER, "a.dev")
    # -purge не существует у httpauth (см. комментарий в webinoly.py) — реальный
    # флаг -delete, поймано вживую 2026-09-09 на roksdigital.ru.
    assert mock_run.call_args[0][1] == "sudo httpauth a.dev -path=all -delete"


def test_disable_http_auth_shows_real_error_from_stdout():
    # Webinoly пишет [ERROR] в stdout, не stderr — регрессионный тест на баг,
    # который дал пустое сообщение об ошибке при первом реальном вызове.
    with (
        patch(
            "hostme.providers.webinoly.run_remote",
            return_value=RemoteResult(stdout="[ERROR] Please, enter a valid URL path!", stderr="", returncode=1),
        ),
        pytest.raises(webinoly.WebinolyError, match="valid URL path"),
    ):
        webinoly.disable_http_auth(SERVER, "a.dev")


def test_add_redirect():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.add_redirect(SERVER, "a.dev", "/old", "/new")
    command = mock_run.call_args[0][1]
    assert "-from=/old" in command
    assert "-to=/new" in command
    assert "-http-code=302" in command


def test_remove_redirect():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.remove_redirect(SERVER, "a.dev", "/old")
    assert mock_run.call_args[0][1] == "sudo site a.dev -redirection -delete -from=/old"


# --- CORS-сниппет: чистая функция + заливка/reload/откат при поломке ---


def test_render_cors_snippet_contains_pattern_and_no_stray_location():
    snippet = webinoly._render_cors_snippet(["https://a.com", "https://b.com"])
    # origin'ы попадают в regex-паттерн re.escape'нутыми (точка экранирована,
    # см. отдельный тест ниже) — здесь просто проверяем общую структуру сниппета.
    assert "a.com" in snippet.replace("\\.", ".")
    assert "b.com" in snippet.replace("\\.", ".")
    assert "location" not in snippet  # намеренно: не дублировать location / Webinoly
    assert "Access-Control-Allow-Origin" in snippet


def test_render_cors_snippet_escapes_regex_metacharacters():
    # origin с точкой не должен матчить произвольный домен из-за regex-спецсимвола
    snippet = webinoly._render_cors_snippet(["https://a.com"])
    assert r"a\.com" in snippet


def test_set_cors_writes_and_reloads():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.set_cors(SERVER, "a.dev", ["https://a.com"])
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert any("base64" in cmd for cmd in commands)
    assert "sudo nginx -t" in commands
    assert "sudo systemctl reload nginx" in commands


def test_set_cors_empty_origins_removes_snippet():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.set_cors(SERVER, "a.dev", [])
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert any(cmd.startswith("rm -f") for cmd in commands)


def test_set_custom_nginx_snippet_writes_and_reloads():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.set_custom_nginx_snippet(SERVER, "a.dev", "error_page 404 /404.html;")
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert any("base64" in cmd and "hostme-custom-nginx.conf" in cmd for cmd in commands)
    assert "sudo nginx -t" in commands
    assert "sudo systemctl reload nginx" in commands


def test_apply_site_defaults_writes_bundled_snippet_and_reloads():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.apply_site_defaults(SERVER, "a.dev")
    commands = [c[0][1] for c in mock_run.call_args_list]
    write = next(cmd for cmd in commands if "hostme-defaults-nginx.conf" in cmd)
    assert "/var/www/a.dev/" in write
    content = base64.b64decode(write.split()[1]).decode()
    assert "location ^~ /_astro/" in content
    assert "sudo nginx -t" in commands


def test_set_custom_nginx_snippet_empty_removes():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.set_custom_nginx_snippet(SERVER, "a.dev", "")
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert any(cmd.startswith("rm -f") and "hostme-custom-nginx.conf" in cmd for cmd in commands)


def test_set_custom_nginx_snippet_rolls_back_on_nginx_test_failure():
    with (
        patch("hostme.providers.webinoly.run_remote", side_effect=[ok(), fail("syntax error"), ok()]) as mock_run,
        pytest.raises(webinoly.WebinolyError, match="syntax error"),
    ):
        webinoly.set_custom_nginx_snippet(SERVER, "a.dev", "garbage {{{")
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert commands[-1].startswith("rm -f")


def test_set_cors_rolls_back_snippet_when_nginx_test_fails():
    # write ok, nginx -t fails -> должен откатить (rm -f) и не звать reload
    with (
        patch(
            "hostme.providers.webinoly.run_remote",
            side_effect=[ok(), fail("syntax error"), ok()],
        ) as mock_run,
        pytest.raises(webinoly.WebinolyError, match="syntax error"),
    ):
        webinoly.set_cors(SERVER, "a.dev", ["https://a.com"])
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert commands[-1].startswith("rm -f")  # откат сниппета
    assert "sudo systemctl reload nginx" not in commands  # reload не звался


# --- releases/rollback: конструирование команд + парсинг ls/readlink ---


def test_ensure_releases_layout_chowns_releases_dir():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.ensure_releases_layout(SERVER, "a.dev")
    command = mock_run.call_args[0][1]
    assert "mkdir -p releases" in command
    assert "chown www-data:www-data releases" in command


def test_switch_release_swaps_symlink_and_reloads():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.switch_release(SERVER, "a.dev", "20260101000000")
    commands = [c[0][1] for c in mock_run.call_args_list]
    assert any("ln -sfn releases/20260101000000" in cmd for cmd in commands)
    assert "sudo nginx -t" in commands
    assert "sudo systemctl reload nginx" in commands


def test_list_releases_parses_and_sorts():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok("20260101000000\n20260102000000\n")):
        releases = webinoly.list_releases(SERVER, "a.dev")
    assert releases == ["20260101000000", "20260102000000"]


def test_list_releases_empty():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok("")):
        assert webinoly.list_releases(SERVER, "a.dev") == []


def test_current_release_parses_symlink_target():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok("releases/20260101000000\n")):
        assert webinoly.current_release(SERVER, "a.dev") == "20260101000000"


def test_current_release_none_when_not_a_symlink():
    with patch("hostme.providers.webinoly.run_remote", return_value=fail("not a symlink")):
        assert webinoly.current_release(SERVER, "a.dev") is None


def test_prune_releases_noop_when_under_limit():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok("a\nb\n")) as mock_run:
        result = webinoly.prune_releases(SERVER, "a.dev", keep=5)
    assert result is None
    mock_run.assert_called_once()  # только list_releases, rm не звался


def test_prune_releases_never_removes_current_even_if_old():
    # r0..r6 (7 штук), keep=5 -> кандидаты на удаление: r0, r1 (releases[:-5]).
    # current — намеренно r0 (симулирует rollback на старый релиз): должен
    # уцелеть, несмотря на то что он старше "keep", а r1 — реально удалиться.
    releases_output = "\n".join(f"r{i}" for i in range(7)) + "\n"
    with patch(
        "hostme.providers.webinoly.run_remote",
        side_effect=[ok(releases_output), ok("r0"), ok()],  # list, readlink(current=r0), rm
    ) as mock_run:
        webinoly.prune_releases(SERVER, "a.dev", keep=5)
    rm_command = mock_run.call_args_list[-1][0][1]
    assert "r0" not in rm_command
    assert "r1" in rm_command


# --- логи: обязательный timeout-враппер (у Webinoly `log` стримит бесконечно) ---


def test_tail_log_wraps_with_timeout():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok("log line\n")) as mock_run:
        result = webinoly.tail_log(SERVER, "a.dev", lines=25)
    command = mock_run.call_args[0][1]
    assert command.startswith("sudo timeout")
    assert "-lines=25" in command
    assert result == "log line\n"


def test_tail_log_error_flag():
    with patch("hostme.providers.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.tail_log(SERVER, "a.dev", error=True)
    assert "-error" in mock_run.call_args[0][1]
