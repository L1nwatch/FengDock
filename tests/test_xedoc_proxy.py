from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_xedoc_routes_ui_api_and_keeper_to_their_services():
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()

    assert "@keeper path /keeper /keeper/*" in caddy
    assert "reverse_proxy cpa-usage-keeper:8080" in caddy
    assert "@cli_proxy_backend path /v0/management" in caddy
    assert "/v0/resource/*" in caddy
    assert "/v1/*" in caddy
    assert "reverse_proxy cli-proxy-api:8317" in caddy
    assert "reverse_proxy cli-proxy-management-center:80" in caddy


def test_deploy_connects_all_xedoc_containers_to_caddy_network():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()

    assert "for container in cli-proxy-management-center cli-proxy-api cpa-usage-keeper" in workflow
    assert 'docker network connect fengdock_fengdock "$container"' in workflow
