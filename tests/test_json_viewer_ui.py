import hashlib
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from app.main import app
from app.database import session_scope
from app import models

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8123
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
SAMPLE_WATCH_URL = "https://www.loblaws.ca/en/lactose-free-2-dairy-product/p/20077874001_EA?source=nspt"
GITHUB_URL = "https://github.com/L1nwatch"
NOTION_URL = "https://watch0.notion.site/"
ANKI_URL = "https://anki.watch0.top/"


@pytest.fixture(scope="session", autouse=True)
def _launch_server():
    """Launch the FastAPI app with uvicorn in a background thread for UI tests."""
    config = uvicorn.Config(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="uvicorn-test-server", daemon=True)
    thread.start()

    timeout = time.time() + 10
    while not server.started:
        if time.time() > timeout:
            raise RuntimeError("Timed out waiting for uvicorn server to start")
        time.sleep(0.05)

    yield

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        yield context
        context.close()
        browser.close()


@pytest.fixture()
def page(browser_context):
    page = browser_context.new_page()
    yield page
    page.close()


def _seed_loblaws_watch() -> None:
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        session.query(models.LoblawsWatch).delete()
        session.add_all(
            [
                models.LoblawsWatch(
                    url=SAMPLE_WATCH_URL,
                    product_code="20077874001_EA",
                    store_id="1032",
                    name="Natrel Lactose Free 2%",
                    brand="Natrel",
                    image_url="https://example.com/sample.png",
                    current_price=6.75,
                    price_unit="ea",
                    regular_price=7.14,
                    sale_text="SAVE $0.39",
                    sale_expiry=datetime(2025, 12, 3, tzinfo=timezone.utc),
                    stock_status="IN_STOCK",
                    last_checked_at=now,
                    last_change_at=now,
                ),
                models.LoblawsWatch(
                    url="https://www.loblaws.ca/en/lactose-free-2-dairy-product/p/20077874001_EA",
                    product_code="20077874001_EA",
                    store_id="1032",
                    name="Natrel Lactose Free 2%",
                    brand="Natrel",
                    image_url="https://example.com/sample.png",
                    current_price=6.99,
                    price_unit="ea",
                    regular_price=7.14,
                    sale_text=None,
                    sale_expiry=None,
                    stock_status="IN_STOCK",
                    last_checked_at=now,
                    last_change_at=now,
                ),
            ]
        )


def _seed_links_for_home() -> None:
    with session_scope() as session:
        session.query(models.Link).delete()
        now = datetime.now(timezone.utc)
        session.add_all(
            [
                models.Link(
                    title="GitHub",
                    description="",
                    url=GITHUB_URL,
                    category="intense-work",
                    color_class="intense-work",
                    order_index=0,
                    click_count=150,
                    last_clicked_at=now - timedelta(days=5),
                ),
                models.Link(
                    title="Notion",
                    description="",
                    url=NOTION_URL,
                    category="intense-work",
                    color_class="intense-work",
                    order_index=1,
                    click_count=10,
                    last_clicked_at=now - timedelta(days=10),
                ),
                models.Link(
                    title="Anki",
                    description="",
                    url=ANKI_URL,
                    category="intense-work",
                    color_class="intense-work",
                    order_index=2,
                    click_count=320,
                    last_clicked_at=now - timedelta(hours=1),
                ),
            ]
        )


@pytest.mark.e2e
def test_json_viewer_modal_hidden_and_render(page):
    page.goto(f"{BASE_URL}/tools/json-viewer", wait_until="networkidle")

    is_hidden = page.eval_on_selector("#modal", "el => el.hasAttribute('hidden')")
    assert is_hidden, "Modal dialog should be hidden on initial load"

    textarea_content = page.input_value("#json-input")
    assert textarea_content == "", "Textarea should start empty"

    sample_data = '{"message": "hello", "items": [1, 2]}'
    page.fill("#json-input", sample_data)
    page.wait_for_function(
        """() => { const tree = document.querySelector('#preview-tree'); return tree && tree.textContent.includes('"message"'); }"""
    )

    tree_text = page.inner_text("#preview-tree")
    assert "message" in tree_text and "items" in tree_text

    long_message = "x" * 140 + "\\nnext line of data"
    page.fill("#json-input", sample_data.replace("hello", long_message))
    page.wait_for_selector(".json-node__expand")

    page.locator(".json-node__expand").first.click()
    modal_visible = page.eval_on_selector("#modal", "el => !el.hasAttribute('hidden')")
    assert modal_visible, "Modal should open after clicking expand"

    modal_text = page.inner_text("#modal-content")
    assert "xxxxxxxx" in modal_text
    assert "next line of data" in modal_text
    assert "\\n" not in modal_text
    assert "\n" in modal_text

    page.click(".fd-modal__close")
    is_hidden_again = page.eval_on_selector("#modal", "el => el.hasAttribute('hidden')")
    assert is_hidden_again


@pytest.mark.e2e
def test_loblaws_board_and_manage_views(page):
    os.environ.pop("PRIVATE_PAGE_PASSWORD_HASH", None)
    _seed_loblaws_watch()

    page.goto(f"{BASE_URL}/board", wait_until="domcontentloaded")
    page.wait_for_selector(".watch-card__title")

    titles = page.locator(".watch-card__title").all_inner_texts()
    assert any("Natrel" in title for title in titles)
    assert page.locator(".watch-card__title").count() == 1
    sale_text = page.locator(".watch-card__sale").first.inner_text()
    assert "SAVE" in sale_text

    assert page.locator(".board-header__manage").is_visible()
    assert page.locator(".watch-card__action--delete").count() == 0

    hash_value = hashlib.sha256(b"secret").hexdigest()
    os.environ["PRIVATE_PAGE_PASSWORD_HASH"] = hash_value

    page.goto(f"{BASE_URL}/board/manage?token={hash_value}", wait_until="domcontentloaded")
    page.wait_for_selector("#watch-form")

    assert page.locator("#watch-form").is_visible()
    assert page.locator(".watch-card__action--delete").count() >= 1
    assert page.locator(".watch-card__title").count() == 2

    with session_scope() as session:
        session.query(models.LoblawsWatch).delete()
    os.environ.pop("PRIVATE_PAGE_PASSWORD_HASH", None)


@pytest.mark.e2e
def test_homepage_click_ordering(page):
    _seed_links_for_home()

    try:
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        page.wait_for_selector('.periodic-table .periodic-element')

        page.wait_for_function(
            """
            () => {
              const first = document.querySelector('.periodic-table .periodic-element');
              if (!first) return false;
              const desc = first.querySelector('.description');
              return desc && desc.textContent.trim() === 'Anki' && first.dataset.clickCount === '320';
            }
            """,
            timeout=5000,
        )

        top_titles = page.locator('.periodic-table .periodic-element .description').all_inner_texts()
        assert top_titles[0] == 'Anki'
        assert top_titles[1] == 'GitHub'
        assert 'Notion' in top_titles[:3]

        first_hidden_value = page.eval_on_selector(
            '.periodic-table .periodic-element .card-click-count', 'el => el.value'
        )
        assert first_hidden_value == '320'

        first_last_click = page.eval_on_selector(
            '.periodic-table .periodic-element', 'el => el.dataset.lastClick'
        )
        assert first_last_click, "Expected last click timestamp to be present on top card"
    finally:
        with session_scope() as session:
            session.query(models.Link).delete()


@pytest.mark.e2e
def test_homepage_click_persists_to_database(page):
    with session_scope() as session:
        session.query(models.Link).delete()

    try:
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        page.wait_for_selector('.periodic-table .periodic-element')

        page.wait_for_timeout(500)
        first_title_before = page.locator('.periodic-table .periodic-element .description').first.inner_text()
        assert first_title_before != 'Anki'

        page.locator('.periodic-element .description', has_text='Anki').click()

        page.wait_for_function(
            """
            () => {
              const first = document.querySelector('.periodic-table .periodic-element');
              if (!first) return false;
              const desc = first.querySelector('.description');
              return desc && desc.textContent.trim() === 'Anki';
            }
            """,
            timeout=5000,
        )

        page.wait_for_timeout(500)

        page.reload(wait_until='domcontentloaded')
        page.wait_for_selector('.periodic-table .periodic-element')
        page.wait_for_function(
            """
            () => {
              const first = document.querySelector('.periodic-table .periodic-element');
              if (!first) return false;
              const desc = first.querySelector('.description');
              return desc && desc.textContent.trim() === 'Anki';
            }
            """,
            timeout=5000,
        )

        with session_scope() as session:
            link = session.query(models.Link).filter_by(url=ANKI_URL).one_or_none()
            assert link is not None, "Expected Anki link to be created in the database"
            assert link.click_count >= 1
    finally:
        with session_scope() as session:
            session.query(models.Link).delete()
