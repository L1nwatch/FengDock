import asyncio
from datetime import datetime

import hashlib
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import loblaws
from app.database import session_scope
from app import models

SAMPLE_URL = "https://www.loblaws.ca/en/lactose-free-2-dairy-product/p/20077874001_EA?source=nspt"

SAMPLE_PAYLOAD_V1 = {
    "code": "20077874001_EA",
    "name": "Lactose Free 2% Dairy Product",
    "brand": "Natrel",
    "imageAssets": [
        {
            "largeUrl": "https://example.com/image.png",
        }
    ],
    "offers": [
        {
            "price": {
                "value": 6.75,
                "unit": "ea",
                "quantity": 1,
                "type": "SPECIAL",
                "expiryDate": "2025-12-03T00:00",
            },
            "wasPrice": {
                "value": 7.14,
                "unit": "ea",
                "quantity": 1,
                "type": "WAS",
            },
            "badges": {
                "dealBadge": {
                    "type": "SALE",
                    "text": "SAVE $0.39",
                    "expiryDate": "2025-12-03T00:00:00Z",
                    "name": "SALE",
                }
            },
            "stockStatus": "IN_STOCK",
        }
    ],
}

SAMPLE_PAYLOAD_V2 = {
    **SAMPLE_PAYLOAD_V1,
    "offers": [
        {
            **SAMPLE_PAYLOAD_V1["offers"][0],
            "price": {
                **SAMPLE_PAYLOAD_V1["offers"][0]["price"],
                "value": 6.25,
            },
            "badges": {
                "dealBadge": {
                    "type": "SALE",
                    "text": "SAVE $0.89",
                    "expiryDate": "2025-12-10T00:00:00Z",
                    "name": "SALE",
                }
            },
        }
    ],
}


@pytest.fixture(autouse=True)
def _clean_loblaws_table():
    with session_scope() as session:
        session.query(models.LoblawsWatch).delete()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clear_manage_env(monkeypatch):
    monkeypatch.delenv("PRIVATE_PAGE_PASSWORD_HASH", raising=False)


def _install_fake_payload(monkeypatch, payloads):
    async def _fake_fetch(product_code: str, *, store_id=None, client=None):
        try:
            return payloads.pop(0)
        except IndexError:  # pragma: no cover - defensive
            return SAMPLE_PAYLOAD_V1

    monkeypatch.setattr(loblaws, "fetch_product_payload", _fake_fetch)


def test_create_watch_populates_fields(client, monkeypatch):
    _install_fake_payload(monkeypatch, [SAMPLE_PAYLOAD_V1.copy()])

    response = client.post("/loblaws/watches", json={"url": SAMPLE_URL})
    assert response.status_code == 201
    body = response.json()
    assert body["product_code"] == "20077874001_EA"
    assert body["sale_text"] == "SAVE $0.39"
    assert body["current_price"] == 6.75
    assert body["image_url"] == "https://example.com/image.png"

    list_response = client.get("/loblaws/watches")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert items[0]["sale_text"] == "SAVE $0.39"


def test_refresh_watch_updates_sale(monkeypatch, client):
    _install_fake_payload(monkeypatch, [SAMPLE_PAYLOAD_V1.copy(), SAMPLE_PAYLOAD_V2.copy()])

    create_response = client.post("/loblaws/watches", json={"url": SAMPLE_URL})
    watch_id = create_response.json()["id"]

    refresh_response = client.post(f"/loblaws/watches/{watch_id}/refresh")
    assert refresh_response.status_code == 200
    data = refresh_response.json()
    assert data["sale_text"] == "SAVE $0.89"
    assert data["current_price"] == 6.25
    assert data["sale_expiry"].startswith("2025-12-10")


def test_board_pages_render(client):
    board = client.get("/board")
    assert board.status_code == 200
    assert "管理页面" in board.text
    assert "watch-card__action--delete" not in board.text

    manage = client.get("/board/manage")
    assert manage.status_code == 200
    assert "watch-card__action--delete" in manage.text
    assert "watch-form" in manage.text


def test_manage_requires_token_when_configured(client, monkeypatch):
    hash_value = hashlib.sha256(b"secret").hexdigest()
    monkeypatch.setenv("PRIVATE_PAGE_PASSWORD_HASH", hash_value)

    unauthorized = client.get("/board/manage")
    assert unauthorized.status_code == 401

    authorized = client.get("/board/manage", params={"token": "secret"})
    assert authorized.status_code == 200

    monkeypatch.delenv("PRIVATE_PAGE_PASSWORD_HASH", raising=False)
