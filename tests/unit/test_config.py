import pytest

from hostme import config


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

    with pytest.raises(config.ConfigError):
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
        ("под_проект  42", "под-проект-42"),
        ("___", "site"),
    ],
)
def test_slugify(raw, expected):
    assert config.slugify(raw) == expected


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
