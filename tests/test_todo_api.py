import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import session_scope
from app.main import app


@pytest.fixture(autouse=True)
def _clean_todo_table():
    with session_scope() as session:
        session.query(models.TodoItem).delete()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_todo_crud(client):
    created = client.post(
        "/api/todo/items",
        json={"title": "  Buy milk  ", "notes": " 2L ", "order_index": 2},
    )
    assert created.status_code == 201
    item = created.json()
    item_id = item["id"]
    assert item["title"] == "Buy milk"
    assert item["notes"] == "2L"
    assert item["is_done"] is False

    listed = client.get("/api/todo/items")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    updated = client.put(f"/api/todo/items/{item_id}", json={"is_done": True})
    assert updated.status_code == 200
    assert updated.json()["is_done"] is True

    delete_resp = client.delete(f"/api/todo/items/{item_id}")
    assert delete_resp.status_code == 204

    assert client.get("/api/todo/items").json() == []


def test_todo_not_found(client):
    assert client.put("/api/todo/items/999999", json={"title": "x"}).status_code == 404
    assert client.delete("/api/todo/items/999999").status_code == 404
