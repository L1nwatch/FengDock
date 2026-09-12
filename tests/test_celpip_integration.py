from pathlib import Path


def test_review_api_is_forwarded_to_celpip():
    caddy = (Path(__file__).resolve().parents[1] / "deploy" / "Caddyfile").read_text()
    matcher = next(line for line in caddy.splitlines() if "@celpip_api path" in line)
    assert "/api/reviews" in matcher.split()
