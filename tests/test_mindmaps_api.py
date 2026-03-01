import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import session_scope
from app import models


@pytest.fixture(autouse=True)
def _clean_mindmaps_table():
    with session_scope() as session:
        session.query(models.MindMapDoc).delete()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_mindmaps_crud_and_conflict_paths(client):
    create = client.post(
        "/mindmaps/",
        json={"title": "  Team Plan  ", "data": {"root": {"text": "Start"}}},
    )
    assert create.status_code == 201
    created = create.json()
    doc_id = created["id"]
    assert created["title"] == "Team Plan"
    assert created["version"] == 1

    listed = client.get("/mindmaps/")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == doc_id

    fetched = client.get(f"/mindmaps/{doc_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["root"]["text"] == "Start"

    conflict = client.put(
        f"/mindmaps/{doc_id}",
        json={"title": "Updated", "data": {"root": {"text": "Changed"}}, "expected_version": 999},
    )
    assert conflict.status_code == 409
    assert conflict.json()["message"] == "Version conflict"

    updated = client.put(
        f"/mindmaps/{doc_id}",
        json={"title": "Updated", "data": {"root": {"text": "Changed"}}, "expected_version": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated"
    assert updated.json()["version"] == 2

    deleted = client.delete(f"/mindmaps/{doc_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/mindmaps/{doc_id}")
    assert missing.status_code == 404


def test_mindmaps_not_found_paths(client):
    assert client.get("/mindmaps/999999").status_code == 404
    assert client.put("/mindmaps/999999", json={"title": "x"}).status_code == 404
    assert client.delete("/mindmaps/999999").status_code == 404
