from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_conclusion_is_built_and_run_as_a_bundled_app():
    dockerfile = (ROOT / "Dockerfile").read_text()
    runner = (ROOT / "scripts" / "run_servers.py").read_text()

    assert "AS conclusion_frontend_builder" in dockerfile
    assert "VITE_API_BASE=/conclusion" in dockerfile
    assert "vendor/conclusion/frontend/dist" in dockerfile
    assert '"CONCLUSION_DATABASE_PATH"' in runner
    assert '"8006"' in runner


def test_conclusion_has_persistent_storage_and_public_route():
    compose = (ROOT / "docker-compose.yml").read_text()
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()

    assert "backend_db:/app/vendor/conclusion/data" in compose
    assert "CONCLUSION_DATABASE_PATH: /app/vendor/conclusion/data/conclusion.sqlite3" in compose
    assert "@conclusion_app path /conclusion /conclusion/*" in caddy
    assert "reverse_proxy backend:8006" in caddy
