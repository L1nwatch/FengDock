from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_xedoc_routes_ui_api_and_keeper_to_their_services():
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()

    assert "@keeper path /keeper /keeper/*" in caddy
    assert "reverse_proxy cpa-usage-keeper:8080" in caddy
    backend_matchers = [
        line.split()[2:]
        for line in caddy.splitlines()
        if line.strip().startswith("@cli_proxy_backend path ")
    ]
    assert len(backend_matchers) == 2
    required_paths = {
        "/v8/management",
        "/v8/management/*",
        "/v0/management",
        "/v0/management/*",
        "/v0/resource",
        "/v0/resource/*",
        "/v1",
        "/v1/*",
    }
    for paths in backend_matchers:
        assert required_paths <= set(paths)
    assert "reverse_proxy cli-proxy-api:8317" in caddy
    assert "reverse_proxy cli-proxy-management-center:80" in caddy


def test_deploy_connects_all_xedoc_containers_to_caddy_network():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()

    assert "for container in cli-proxy-management-center cli-proxy-api cpa-usage-keeper" in workflow
    assert 'docker network connect fengdock_fengdock "$container"' in workflow
