from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_json_viewer_get_returns_page():
    response = client.get("/tools/json-viewer")
    assert response.status_code == 200
    body = response.text
    assert "JSON 预览工具" in body
    assert "id=\"json-input\"" in body
    assert "static/tools/json-viewer/app.js" in body


def test_json_viewer_head_returns_ok():
    response = client.head("/tools/json-viewer")
    assert response.status_code == 200
    assert response.text == ""


def test_homepage_links_json_tool():
    response = client.get("/")
    assert response.status_code == 200
    assert "/tools/json-viewer" in response.text
