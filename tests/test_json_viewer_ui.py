import threading
import time

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from app.main import app

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8123
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"


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

    page.fill("#json-input", sample_data.replace("hello", "x" * 220))
    page.wait_for_selector(".json-node__expand")

    page.locator(".json-node__expand").first.click()
    modal_visible = page.eval_on_selector("#modal", "el => !el.hasAttribute('hidden')")
    assert modal_visible, "Modal should open after clicking expand"

    modal_text = page.inner_text("#modal-content")
    assert "xxxxxxxx" in modal_text

    page.click(".fd-modal__close")
    is_hidden_again = page.eval_on_selector("#modal", "el => el.hasAttribute('hidden')")
    assert is_hidden_again
