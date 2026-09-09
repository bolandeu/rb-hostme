from unittest.mock import patch

import pytest

from hostme import webinoly
from hostme.config import Server
from hostme.ssh import RemoteResult

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
    with patch("hostme.webinoly.run_remote", return_value=ok("/usr/bin/webinoly")):
        assert webinoly.is_installed(SERVER) is True


def test_is_installed_false():
    with patch("hostme.webinoly.run_remote", return_value=fail()):
        assert webinoly.is_installed(SERVER) is False


def test_install_skips_when_already_installed():
    with patch("hostme.webinoly.run_remote", side_effect=[ok(), ok("Webinoly version: 1.21.2")]) as mock_run:
        webinoly.install(SERVER)

    assert mock_run.call_count == 2
    second_call_command = mock_run.call_args_list[1][0][1]
    assert second_call_command == "webinoly -version"


def test_install_runs_installer_when_missing():
    with patch("hostme.webinoly.run_remote", side_effect=[fail(), ok()]) as mock_run:
        webinoly.install(SERVER, mode="-php")

    install_command = mock_run.call_args_list[1][0][1]
    assert "bash weby -php" in install_command
    assert webinoly.INSTALL_URL in install_command


def test_install_raises_on_failure():
    with (
        patch("hostme.webinoly.run_remote", side_effect=[fail(), fail("network unreachable")]),
        pytest.raises(webinoly.WebinolyError, match="network unreachable"),
    ):
        webinoly.install(SERVER)


def test_list_sites_uses_run_remote():
    with patch("hostme.webinoly.run_remote", return_value=ok(LIST_OUTPUT)) as mock_run:
        sites = webinoly.list_sites(SERVER)

    mock_run.assert_called_once_with(SERVER, "sudo site -list")
    assert len(sites) == 3


def test_site_exists_true():
    with patch("hostme.webinoly.run_remote", return_value=ok(LIST_OUTPUT)):
        assert webinoly.site_exists(SERVER, "test1.antagorapp.ru") is True


def test_site_exists_false():
    with patch("hostme.webinoly.run_remote", return_value=ok(EMPTY_LIST_OUTPUT)):
        assert webinoly.site_exists(SERVER, "missing.dev") is False


def test_create_site_html():
    with patch("hostme.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.create_site(SERVER, "a.dev", "html")
    assert mock_run.call_args[0][1] == "sudo site a.dev -html"


def test_create_site_php():
    with patch("hostme.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.create_site(SERVER, "a.dev", "php")
    assert mock_run.call_args[0][1] == "sudo site a.dev -php"


def test_create_site_raises_on_failure():
    with (
        patch("hostme.webinoly.run_remote", return_value=fail("domain taken")),
        pytest.raises(webinoly.WebinolyError, match="domain taken"),
    ):
        webinoly.create_site(SERVER, "a.dev", "html")


def test_enable_ssl_plain():
    with patch("hostme.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.enable_ssl(SERVER, "a.dev")
    assert mock_run.call_args[0][1] == "sudo site a.dev -ssl=on"


def test_enable_ssl_wildcard():
    with patch("hostme.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.enable_ssl(SERVER, "a.dev", wildcard=True)
    assert mock_run.call_args[0][1] == "sudo site a.dev -ssl=on -wildcard"


def test_enable_ssl_add_to_wildcard():
    with patch("hostme.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.enable_ssl(SERVER, "sub.a.dev", add_to_wildcard="a.dev")
    assert mock_run.call_args[0][1] == "sudo site sub.a.dev -ssl=on -add-to-wildcard=a.dev"


def test_enable_ssl_raises_on_failure():
    with (
        patch("hostme.webinoly.run_remote", return_value=fail("dns not ready")),
        pytest.raises(webinoly.WebinolyError, match="dns not ready"),
    ):
        webinoly.enable_ssl(SERVER, "a.dev")


def test_delete_site_default_revokes_ssl():
    with patch("hostme.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.delete_site(SERVER, "a.dev")
    assert mock_run.call_args[0][1] == "sudo site a.dev -delete=force -revoke=on"


def test_delete_site_without_revoke():
    with patch("hostme.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.delete_site(SERVER, "a.dev", revoke_ssl=False)
    assert mock_run.call_args[0][1] == "sudo site a.dev -delete=force -revoke=off"


def test_delete_site_raises_on_failure():
    with (
        patch("hostme.webinoly.run_remote", return_value=fail("not found")),
        pytest.raises(webinoly.WebinolyError, match="not found"),
    ):
        webinoly.delete_site(SERVER, "a.dev")


def test_webroot_path():
    assert webinoly.webroot("example.com") == "/var/www/example.com/htdocs"


def test_fix_ownership():
    with patch("hostme.webinoly.run_remote", return_value=ok()) as mock_run:
        webinoly.fix_ownership(SERVER, "a.dev")
    assert mock_run.call_args[0][1] == "sudo chown -R www-data:www-data /var/www/a.dev/htdocs"


def test_fix_ownership_raises_on_failure():
    with (
        patch("hostme.webinoly.run_remote", return_value=fail("permission denied")),
        pytest.raises(webinoly.WebinolyError, match="permission denied"),
    ):
        webinoly.fix_ownership(SERVER, "a.dev")
