import pytest

from hostme import config
from hostme.core.errors import InvalidArgumentsError


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "hostme"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "SERVERS_FILE", config_dir / "servers.yaml")
    monkeypatch.setattr(config, "SITES_FILE", config_dir / "sites.yaml")
    return config_dir


def make_server(name="vps1", default=False, base_domains=None):
    return config.Server(
        name=name,
        host="1.2.3.4",
        user="root",
        ssh_key="~/.ssh/id",
        default=default,
        base_domains=base_domains or [],
    )


def test_load_servers_missing_file_returns_empty():
    assert config.load_servers() == []


def test_save_and_load_servers_roundtrip():
    domain = config.BaseDomain(name="example.dev", default=True)
    server = make_server(default=True, base_domains=[domain])
    config.save_servers([server])

    loaded = config.load_servers()

    assert len(loaded) == 1
    assert loaded[0].name == "vps1"
    assert loaded[0].default is True
    assert loaded[0].base_domains[0].name == "example.dev"
    assert loaded[0].base_domains[0].default is True


def test_servers_file_has_restrictive_permissions():
    config.save_servers([make_server()])
    mode = config.SERVERS_FILE.stat().st_mode & 0o777
    assert mode == 0o600


# --- Target: делит servers.yaml с Server ("servers:"/"targets:" — соседние
# ключи одного файла) — критично, чтобы save_servers/save_targets не затирали
# друг друга (реальный риск, раз это один файл, а не раздельные).


def make_target(**overrides):
    defaults = {
        "name": "ext1",
        "connection": "sftp",
        "host": "host.example",
        "user": "u12345",
        "remote_path": "/www",
        "password": "s3cr3t",
    }
    defaults.update(overrides)
    return config.Target(**defaults)


def test_save_and_load_targets_roundtrip():
    config.save_targets([make_target()])
    loaded = config.load_targets()
    assert len(loaded) == 1
    assert loaded[0].name == "ext1"
    assert loaded[0].connection == "sftp"
    assert loaded[0].password == "s3cr3t"
    assert loaded[0].remote_path == "/www"


def test_save_targets_does_not_wipe_existing_servers():
    config.save_servers([make_server()])
    config.save_targets([make_target()])
    assert len(config.load_servers()) == 1
    assert len(config.load_targets()) == 1


def test_save_servers_does_not_wipe_existing_targets():
    config.save_targets([make_target()])
    config.save_servers([make_server()])
    assert len(config.load_targets()) == 1
    assert len(config.load_servers()) == 1


def test_find_target():
    targets = [make_target(name="a"), make_target(name="b")]
    assert config.find_target(targets, "b") is targets[1]
    assert config.find_target(targets, "missing") is None


def test_find_server():
    servers = [make_server("vps1"), make_server("vps2")]
    assert config.find_server(servers, "vps2").name == "vps2"
    assert config.find_server(servers, "missing") is None


def test_default_server_prefers_flagged_default():
    servers = [make_server("vps1"), make_server("vps2", default=True)]
    assert config.default_server(servers).name == "vps2"


def test_default_server_falls_back_to_first_when_none_flagged():
    servers = [make_server("vps1"), make_server("vps2")]
    assert config.default_server(servers).name == "vps1"


def test_default_server_empty_list():
    assert config.default_server([]) is None


def test_default_base_domain_returns_first_registered():
    servers = [
        make_server("vps1", base_domains=[config.BaseDomain("old.dev", default=False)]),
        make_server(
            "vps2",
            base_domains=[
                config.BaseDomain("first.dev", default=True),
                config.BaseDomain("second.dev", default=False),
            ],
        ),
    ]
    result = config.default_base_domain(servers)
    assert result is not None
    server, base_domain = result
    assert server.name == "vps2"
    assert base_domain.name == "first.dev"


def test_default_base_domain_none_when_nothing_flagged():
    servers = [make_server("vps1", base_domains=[config.BaseDomain("x.dev")])]
    assert config.default_base_domain(servers) is None


def test_resolve_server_for_domain_exact_and_subdomain_match():
    server = make_server(base_domains=[config.BaseDomain("example.dev", default=True)])
    servers = [server]

    assert config.resolve_server_for_domain(servers, "example.dev") is server
    assert config.resolve_server_for_domain(servers, "blog.example.dev") is server
    assert config.resolve_server_for_domain(servers, "other.com") is None


def test_check_collision_allows_same_local_path(tmp_path):
    site_path = tmp_path / "myproject"
    site_path.mkdir()
    sites = [
        config.Site(domain="a.dev", server="vps1", local_path=str(site_path)),
    ]
    config.check_collision(sites, "a.dev", str(site_path))


def test_check_collision_rejects_different_local_path(tmp_path):
    existing_path = tmp_path / "existing"
    existing_path.mkdir()
    new_path = tmp_path / "new"
    new_path.mkdir()
    sites = [
        config.Site(domain="a.dev", server="vps1", local_path=str(existing_path)),
    ]

    with pytest.raises(InvalidArgumentsError):
        config.check_collision(sites, "a.dev", str(new_path))


def test_check_collision_no_existing_site_is_noop(tmp_path):
    config.check_collision([], "a.dev", str(tmp_path))


def test_save_and_load_sites_roundtrip(tmp_path):
    site = config.Site(
        domain="blog.example.dev",
        server="vps1",
        local_path=str(tmp_path),
        php=True,
        deployed_at="2026-09-08T12:00:00",
    )
    config.save_sites([site])

    loaded = config.load_sites()

    assert len(loaded) == 1
    assert loaded[0].domain == "blog.example.dev"
    assert loaded[0].php is True
    assert loaded[0].deployed_at == "2026-09-08T12:00:00"


def test_ensure_config_dir_created_on_first_save(isolated_config):
    assert not isolated_config.exists()
    config.save_servers([make_server()])
    assert isolated_config.exists()
    assert (isolated_config.stat().st_mode & 0o777) == 0o700


def test_resolve_server_prefers_explicit_flag():
    vps1, vps2 = make_server("vps1"), make_server("vps2")
    servers = [vps1, vps2]
    assert config.resolve_server(servers, [], "any.dev", explicit_server="vps2") is vps2


def test_resolve_server_uses_known_site_domain_before_base_domains():
    vps1 = make_server("vps1", base_domains=[config.BaseDomain("shared.dev", default=True)])
    vps2 = make_server("vps2")
    servers = [vps1, vps2]
    sites = [config.Site(domain="already.shared.dev", server="vps2", local_path="/tmp/x")]

    result = config.resolve_server(servers, sites, "already.shared.dev")

    assert result is vps2


def test_resolve_server_falls_back_to_base_domain_suffix_match():
    vps1 = make_server("vps1", base_domains=[config.BaseDomain("shared.dev", default=True)])
    result = config.resolve_server([vps1], [], "new.shared.dev")
    assert result is vps1


def test_resolve_server_returns_none_when_nothing_matches():
    assert config.resolve_server([make_server()], [], "unrelated.com") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("my-landing", "my-landing"),
        ("My Landing!", "my-landing"),
        ("под_проект  42", "xn----42-p4dh9a2acgdm3a"),
        ("___", "site"),
    ],
)
def test_slugify(raw, expected):
    assert config.slugify(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),  # ASCII — без изменений
        ("растаможка-авто.рф", "xn----7sbaabmy6aqugnooj.xn--p1ai"),  # весь домен, включая TLD
    ],
)
def test_normalize_domain(raw, expected):
    assert config.normalize_domain(raw) == expected


def test_default_domain_combines_folder_name_and_first_base_domain(tmp_path):
    project = tmp_path / "my-landing"
    project.mkdir()
    servers = [
        make_server("vps1", base_domains=[config.BaseDomain("example.dev", default=True)])
    ]

    assert config.default_domain(str(project), servers) == "my-landing.example.dev"


def test_default_domain_none_without_default_base_domain(tmp_path):
    assert config.default_domain(str(tmp_path), [make_server()]) is None


def test_load_sites_follows_include(isolated_config):
    isolated_config.mkdir(parents=True, exist_ok=True)
    included = isolated_config / "sites.d" / "personal.yaml"
    included.parent.mkdir(parents=True, exist_ok=True)
    included.write_text(
        "sites:\n"
        "  - domain: personal.dev\n"
        "    server: vps1\n"
        "    local_path: /tmp/personal\n"
    )
    config.SITES_FILE.write_text("include:\n  - sites.d/personal.yaml\nsites: []\n")

    loaded = config.load_sites()

    assert len(loaded) == 1
    assert loaded[0].domain == "personal.dev"


def test_save_sites_writes_back_to_originating_include_file(isolated_config):
    # Раздел 2.5 TODO: сайт, прочитанный из sites.d/*.yaml, должен обновляться
    # там же, а не переезжать в главный sites.yaml при первом же save_sites().
    isolated_config.mkdir(parents=True, exist_ok=True)
    included = isolated_config / "sites.d" / "personal.yaml"
    included.parent.mkdir(parents=True, exist_ok=True)
    included.write_text(
        "sites:\n  - domain: personal.dev\n    server: vps1\n    local_path: /tmp/personal\n"
    )
    config.SITES_FILE.write_text("include:\n  - sites.d/personal.yaml\nsites: []\n")

    sites = config.load_sites()
    sites[0].deployed_at = "2026-09-09T00:00:00+00:00"
    config.save_sites(sites)

    assert config.load_sites()[0].deployed_at == "2026-09-09T00:00:00+00:00"
    main_data = config.SITES_FILE.read_text()
    assert "personal.dev" not in main_data  # не продублировалось в главный файл
    assert "sites.d/personal.yaml" in main_data  # include-ссылка сохранилась
