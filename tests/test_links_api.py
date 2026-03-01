import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import session_scope
from app import models


@pytest.fixture(autouse=True)
def _clean_links_table():
    with session_scope() as session:
        session.query(models.Link).delete()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_links_crud_and_click_branches(client):
    created = client.post(
        "/links/",
        json={
            "title": "GitHub",
            "description": "Code host",
            "url": "https://github.com",
            "category": "dev",
            "color_class": "intense-work",
            "order_index": 1,
            "is_active": True,
        },
    )
    assert created.status_code == 201
    link_id = created.json()["id"]

    listed = client.get("/links/?ordering=order")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    got = client.get(f"/links/{link_id}")
    assert got.status_code == 200
    assert got.json()["title"] == "GitHub"

    clicked_existing = client.post("/links/click", json={"url": "https://github.com/"})
    assert clicked_existing.status_code == 204

    updated = client.put(f"/links/{link_id}", json={"is_active": False})
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    # Without include_inactive, the now-inactive link is filtered out.
    active_only = client.get("/links/")
    assert active_only.status_code == 200
    assert active_only.json() == []

    with_inactive = client.get("/links/?include_inactive=true&ordering=clicks&limit=10")
    assert with_inactive.status_code == 200
    assert len(with_inactive.json()) == 1

    # Unknown URL without metadata should no-op.
    clicked_unknown = client.post("/links/click", json={"url": "https://example.com/new"})
    assert clicked_unknown.status_code == 204

    # Unknown URL with metadata creates then records click.
    clicked_new = client.post(
        "/links/click",
        json={
            "url": "https://example.com/new",
            "title": "Example",
            "category": "misc",
            "description": "new link",
            "order_index": 3,
        },
    )
    assert clicked_new.status_code == 204
    all_links = client.get("/links/?include_inactive=true")
    assert len(all_links.json()) == 2

    deleted = client.delete(f"/links/{link_id}")
    assert deleted.status_code == 204
    assert client.get(f"/links/{link_id}").status_code == 404


def test_links_not_found_branches(client):
    assert client.put("/links/999999", json={"title": "x"}).status_code == 404
    assert client.delete("/links/999999").status_code == 404
