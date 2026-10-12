import re
from pathlib import Path


def test_review_api_is_forwarded_to_celpip():
    caddy = (Path(__file__).resolve().parents[1] / "deploy" / "Caddyfile").read_text()
    matcher = next(line for line in caddy.splitlines() if "@celpip_api path" in line)
    assert "/api/reviews" in matcher.split()


def test_frontend_api_routes_are_forwarded_to_celpip():
    root = Path(__file__).resolve().parents[1]
    frontend = (root / "vendor" / "celpip-exam-simulation" / "webapp" / "app.js").read_text()
    api_paths = set(re.findall(r"fetch\([\"'`](/api/[^\"'`?]+)", frontend))
    assert api_paths, "No CELPIP frontend API requests found"

    caddy = (root / "deploy" / "Caddyfile").read_text()
    matcher = next(line for line in caddy.splitlines() if "@celpip_api path" in line)
    missing_paths = api_paths - set(matcher.split()[2:])
    assert not missing_paths, f"CELPIP API routes missing from Caddy: {sorted(missing_paths)}"
