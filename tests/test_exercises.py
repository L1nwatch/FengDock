from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_exercises_get_returns_app():
    response = client.get("/exercises/")

    assert response.status_code == 200
    body = response.text
    assert "每日腰背训练" in body
    assert 'id="start-button"' in body
    assert 'id="feedback-form"' in body
    assert 'name="feedback" value="good"' in body
    assert 'name="feedback" value="bad"' in body
    assert 'name="effort"' not in body
    assert 'name="symptom"' not in body
    assert "/static/exercises/app.js" in body


def test_exercises_head_returns_ok():
    response = client.head("/exercises/")

    assert response.status_code == 200
    assert response.text == ""


def test_legacy_exercises_route_redirects_to_namespace():
    response = client.get("/tools/exercises", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "/exercises/"
