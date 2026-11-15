"""Browser and MCP round-trip tests against an isolated Conclusion database."""

import json
import re
from contextlib import contextmanager
from pathlib import Path
import socket
from threading import Thread
from time import monotonic, sleep

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from test_mcp_server import _load_mcp_app
from vendor.conclusion.app.main import FRONTEND_DIST, create_app


@pytest.fixture
def decision_workflow(tmp_path, monkeypatch):
    module = _load_mcp_app(tmp_path, monkeypatch)
    app = create_app(module.CONCLUSION_DATABASE_PATH)
    read = module.provider._issue_tokens("test", ["fengdock:read"], "owner", module.provider.resource_url)
    write = module.provider._issue_tokens("test", module.provider.scopes, "owner", module.provider.resource_url)
    with (
        TestClient(app) as api,
        TestClient(module.app, base_url="https://watch0.top") as mcp,
    ):
        def call(name, arguments, *, read_only=False):
            token = read if read_only else write
            response = mcp.post(
                "/mcp",
                headers={
                    "Authorization": f"Bearer {token.access_token}",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            assert response.status_code == 200, response.text
            return response.json()["result"]

        yield app, api, call


def _example():
    return json.loads(
        (FRONTEND_DIST.parents[1] / "tests/fixtures/celpip-decision.json").read_text(encoding="utf-8")
    )


def _result(response):
    assert not response.get("isError"), response
    return response["structuredContent"]


def _expect_saved(page):
    page.clock.fast_forward(8000)
    expect(page.get_by_role("status").filter(has_text=re.compile(r"^已保存 · v\d+$"))).to_be_visible()


def test_decision_mcp_scopes_errors_and_http_round_trip(decision_workflow):
    _, api, call = decision_workflow
    form = _example()
    denied = call("create_decision", form, read_only=True)
    assert denied["isError"] and "fengdock:write" in denied["content"][0]["text"]

    example = _result(call("create_decision", form))
    ids = {"decision_id": example["id"]}
    url = f"/api/decisions/{example['id']}"
    listed = _result(call("list_decisions", {
        "query": "cec", "status": "Thinking", "limit": 1,
    }, read_only=True))
    assert listed["count"] == 1 and listed["items"][0]["id"] == example["id"]
    assert example == api.get(url).json() == _result(call("get_decision", ids, read_only=True))

    args = {**ids, "expected_version": 1}
    changes = {"title": "CEC 与英语策略", "description": "example"}
    operations = [
        {"op": "add", "id": "branch", "parentId": "draw", "text": "检查进度"},
        {"op": "add", "id": "child", "parentId": "branch", "text": "复查"},
        {"op": "update", "id": "branch", "changes": {"positionX": 100, "positionY": 150}},
    ]
    for name, payload in (
        ("update_decision", {**args, "changes": changes}),
        ("update_decision_tree", {**args, "operations": operations}),
        ("delete_decision", args),
    ):
        denied = call(name, payload, read_only=True)
        assert denied["isError"] and "fengdock:write" in denied["content"][0]["text"]

    updated = _result(call("update_decision", {**args, "changes": changes}))
    assert updated["title"] == changes["title"] and updated["version"] == 2
    stale = call("update_decision_tree", {**args, "operations": operations})
    assert stale["isError"] and "currentVersion=2" in stale["content"][0]["text"]
    batch = _result(call("update_decision_tree", {**args, "expected_version": 2, "operations": operations}))
    assert batch == api.get(url).json() and batch["version"] == 3

    rolled_back = call("update_decision_tree", {
        **args, "expected_version": 3, "operations": [
            {"op": "delete", "id": "pr"},
            {"op": "move", "id": "branch", "parentId": "child"},
        ],
    })
    assert rolled_back["isError"] and "cycle" in rolled_back["content"][0]["text"]
    assert api.get(url).json() == batch
    assert _result(call("delete_decision", {**args, "expected_version": 3}))["deleted"] is True
    assert api.get(url).status_code == 404


@contextmanager
def _serve(app):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
        worker = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        worker.start()
        try:
            deadline = monotonic() + 5
            while not server.started:
                if monotonic() > deadline:
                    raise RuntimeError("Conclusion test server did not start")
                sleep(0.02)
            yield f"http://127.0.0.1:{sock.getsockname()[1]}"
        finally:
            server.should_exit = True
            worker.join(timeout=5)


@pytest.mark.e2e
def test_decision_editor_drag_save_and_mcp_reload(decision_workflow):
    app, api, call = decision_workflow
    index = FRONTEND_DIST / "index.html"
    if not index.exists() or "/conclusion/assets/" not in index.read_text():
        pytest.skip("Build Conclusion with VITE_API_BASE=/conclusion npm run build -- --base=/conclusion/")
    form = _example()
    example = _result(call("create_decision", form))
    ids = {"decision_id": example["id"]}
    full = FastAPI()
    full.mount("/conclusion", app)

    with _serve(full) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.clock.install()
        page.set_default_timeout(10000)
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(f"{url}/conclusion/")
        expect(page.get_by_role("heading", name="最近结论")).to_be_visible()
        page.get_by_role("link", name="Decision Trees").click()
        search = page.get_by_role("textbox", name="搜索决策标题")
        search.fill("not a title")
        expect(page.get_by_text("没有匹配的决策")).to_be_visible()
        search.fill("CEC 抽签")
        page.get_by_role("link", name=form["title"]).click()
        canvas = page.locator(".tree-canvas")

        def card(node_id):
            return page.locator(f'[data-node-id="{node_id}"]')

        def saved_node(state, node_id):
            return next(node for node in state["nodes"] if node["id"] == node_id)

        expect(canvas.get_by_role("button", name="CELPIP", exact=True)).to_be_visible()
        expect(canvas.locator(".vue-flow__edge")).to_have_count(14)
        expect(page.get_by_role("complementary", name="编辑节点")).to_have_count(0)
        expect(canvas).to_have_css("background-image", "none")
        viewport = canvas.locator(".vue-flow__transformationpane")
        before_zoom = viewport.get_attribute("style")
        canvas.get_by_role("button", name="放大").click()
        expect(viewport).not_to_have_attribute("style", before_zoom)
        before_pan = viewport.get_attribute("style")
        pane = canvas.locator(".vue-flow__pane").bounding_box()
        assert pane
        x, y = pane["x"] + 50, pane["y"] + pane["height"] - 70
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 40, y - 20, steps=8)
        page.mouse.up()
        expect(viewport).not_to_have_attribute("style", before_pan)
        canvas.get_by_role("button", name="适应画布").click()
        canvas.get_by_role("button", name="自动布局").click()
        page.clock.fast_forward(8000)
        expect(page.get_by_text("已保存 · v2")).to_be_visible()
        before = _result(call("get_decision", ids))

        label = card("no-draw").get_by_role("button", name="没有 CEC 抽签")
        box = label.bounding_box()
        assert box
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 55, y + 24, steps=12)
        page.mouse.up()
        page.clock.fast_forward(8000)
        expect(page.get_by_text("已保存 · v3")).to_be_visible()
        moved = _result(call("get_decision", ids))
        delta = saved_node(moved, "no-draw")["positionX"] - saved_node(before, "no-draw")["positionX"]
        assert delta > 10
        for node in ("pr", "travel"):
            assert saved_node(moved, node)["positionX"] - saved_node(before, node)["positionX"] == pytest.approx(delta)
        assert saved_node(moved, "no-draw")["parentId"] == "celpip"

        card("no-draw").get_by_role("button", name="拖拽分支").drag_to(card("draw"))
        card("no-draw").get_by_role("button", name="拖拽分支").drag_to(
            card("score"), target_position={"x": 24, "y": 2}
        )
        card("no-draw").get_by_role("button", name="没有 CEC 抽签").click()
        page.keyboard.press("Tab")
        text_input = canvas.get_by_role("textbox", name="节点文字")
        expect(text_input).to_be_focused()
        expect(text_input).to_have_value("")
        text_input.fill("新增中文条件分支")
        text_input.press("Enter")
        new_node = canvas.get_by_role("button", name="新增中文条件分支")
        expect(new_node).to_be_focused()
        page.locator(".decision-node-card", has=page.get_by_role(
            "button", name="新增中文条件分支",
        )).get_by_role("button", name="节点操作").click()
        page.get_by_role("menuitem", name="节点属性").click()
        page.get_by_role("combobox", name="类型").press("Enter")
        page.get_by_role("option", name="Condition", exact=True).click()
        page.get_by_role("button", name="完成").click()
        card("no-draw").get_by_role("button", name="折叠分支").click()
        expect(new_node).to_have_count(0)
        _expect_saved(page)

        state = _result(call("get_decision", ids))
        assert saved_node(state, "no-draw")["parentId"] == "draw"
        assert saved_node(state, "no-draw")["order"] == 0 and saved_node(state, "score")["order"] == 1
        assert saved_node(state, "pr")["parentId"] == "no-draw"
        assert saved_node(state, "no-draw")["collapsed"]
        assert next(node for node in state["nodes"] if node["text"] == "新增中文条件分支")["type"] == "Condition"
        page.reload()
        expect(card("no-draw").get_by_role("button", name="展开分支")).to_be_visible()

        remote = _result(call("update_decision_tree", {
            **ids, "expected_version": state["version"], "operations": [
                {"op": "add", "id": "remote", "parentId": "celpip", "text": "MCP 分支"},
                {"op": "add", "id": "remote-child", "parentId": "remote", "text": "远程下一步"},
                {"op": "move", "id": "pr", "parentId": "remote", "order": 0},
                {"op": "update", "id": "pr", "changes": {"text": "MCP 更新"}},
                {"op": "delete", "id": "mid"},
            ],
        }))
        card("no-draw").get_by_role("button", name="展开分支").click()
        expect(new_node).to_be_visible()
        page.clock.fast_forward(8000)
        expect(page.get_by_text("远端已有新版本")).to_be_visible()
        expect(new_node).to_be_visible()
        page.get_by_role("button", name="应用远端").click()
        page.get_by_role("dialog", name="应用远端版本").get_by_role("button", name="应用远端").click()
        expect(canvas.get_by_role("button", name="MCP 更新")).to_be_visible()
        expect(canvas.get_by_role("button", name="远程下一步")).to_be_visible()
        expect(card("mid-high")).to_have_count(0)
        assert api.get(f"/api/decisions/{example['id']}").json() == remote

        page.get_by_role("link", name="决策列表").click()
        page.get_by_role("button", name="新建决策").click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_role("textbox", name="决策标题").fill("Browser decision")
        page.get_by_role("button", name="创建并打开").click()
        expect(page.get_by_role("heading", name="Browser decision")).to_be_visible()
        root = canvas.get_by_role("button", name="Browser decision")
        root.dblclick()
        expect(text_input).to_be_focused()
        expect(text_input).to_have_value("Browser decision")
        assert text_input.evaluate("el => el.selectionStart === el.value.length && el.selectionEnd === el.value.length")
        text_input.press("Escape")
        expect(root).to_be_focused()
        page.keyboard.press("Tab")
        text_input.fill("Retained child")
        text_input.press("Enter")
        expect(canvas.get_by_role("button", name="Retained child")).to_be_focused()
        page.keyboard.press("Enter")
        expect(text_input).to_be_focused()
        text_input.fill("Removed sibling")
        text_input.press("Enter")
        page.keyboard.press("Delete")
        page.get_by_role("dialog").get_by_role("button", name="删除分支").click()
        _expect_saved(page)
        expect(canvas.get_by_role("button", name="Retained child")).to_be_visible()
        expect(canvas.get_by_role("button", name="Removed sibling")).to_have_count(0)
        page.get_by_role("link", name="决策列表").click()
        row = page.get_by_role("listitem").filter(has_text="Browser decision")
        row.get_by_role("button", name="编辑").click()
        dialog.get_by_role("textbox", name="决策标题").fill("Renamed")
        dialog.get_by_role("textbox", name="背景描述").fill("Sample background")
        dialog.get_by_role("combobox", name="状态").press("Enter")
        page.get_by_role("option", name="Decided", exact=True).click()
        page.get_by_role("button", name="保存", exact=True).click()
        row = page.get_by_role("listitem").filter(has_text="Renamed")
        expect(row.get_by_text("Sample background")).to_be_visible()
        expect(row.get_by_text("Decided")).to_be_visible()
        row.get_by_role("button", name="删除").click()
        page.get_by_role("button", name="删除决策").click()
        expect(row).to_have_count(0)

        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("link", name=form["title"]).click()
        expect(canvas).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page_errors == []
        browser.close()


@pytest.mark.e2e
def test_inline_autosave_queues_text_while_a_write_is_in_flight(decision_workflow):
    app, api, _ = decision_workflow
    index = FRONTEND_DIST / "index.html"
    if not index.exists() or "/conclusion/assets/" not in index.read_text():
        pytest.skip("Build Conclusion with VITE_API_BASE=/conclusion npm run build -- --base=/conclusion/")
    record = api.post("/api/decisions", json={"title": "Autosave race"}).json()
    decision_id = record["id"]
    full = FastAPI()
    full.mount("/conclusion", app)

    with _serve(full) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.clock.install()
        page.set_default_timeout(10000)
        page.goto(f"{url}/conclusion/decision-trees/{decision_id}")
        label = page.get_by_role("button", name="Autosave race")
        text = page.get_by_role("textbox", name="节点文字")
        label.press("F2")
        expect(text).to_be_focused()

        blocked = []
        page.route(f"**/api/decisions/{decision_id}/tree", lambda route: blocked.append(route), times=1)
        with page.expect_request(lambda request: request.method == "PATCH"):
            text.fill("First edit")
            page.clock.fast_forward(8000)
        expect(page.get_by_role("status")).to_contain_text("正在保存")
        text.press("Shift+Enter")
        page.keyboard.insert_text("补充中文")
        text.dispatch_event("keydown", {"key": "Enter", "isComposing": True})
        expect(text).to_be_focused()
        expect(text).to_have_value("First edit\n补充中文")
        assert len(blocked) == 1
        blocked.pop().continue_()

        page.clock.fast_forward(8000)
        expect(page.get_by_role("status")).to_have_text("已保存 · v3")
        expect(text).to_be_focused()
        expect(text).to_have_value("First edit\n补充中文")
        saved = api.get(f"/api/decisions/{decision_id}").json()
        assert saved["nodes"][0]["text"] == "First edit\n补充中文"
        text.press("Escape")
        expect(label).to_be_focused()
        page.clock.fast_forward(8000)
        expect(page.get_by_role("status")).to_have_text("已保存 · v4")
        assert api.get(f"/api/decisions/{decision_id}").json()["nodes"][0]["text"] == "Autosave race"

        label.dblclick()
        text.fill("Saved before navigation")
        page.get_by_role("link", name="决策列表").click()
        page.get_by_role("link", name="Autosave race").click()
        expect(page.get_by_role("button", name="Saved before navigation")).to_be_visible()
        browser.close()


@pytest.mark.e2e
def test_growing_a_branch_keeps_it_apart_and_shares_one_connector(decision_workflow):
    app, api, _ = decision_workflow
    index = FRONTEND_DIST / "index.html"
    if not index.exists() or "/conclusion/assets/" not in index.read_text():
        pytest.skip("Build Conclusion with VITE_API_BASE=/conclusion npm run build -- --base=/conclusion/")
    seed = [
        ("root", None, 0, 0, 0),
        ("a", "root", 0, 298, 0),
        ("a1", "a", 0, 596, 0),
        ("a2", "a", 1, 596, 277),
        ("b", "root", 1, 298, 92),
        ("b1", "b", 0, 596, 92),
        ("b2", "b", 1, 596, 184),
    ]
    record = api.post("/api/decisions", json={
        "title": "Layout regression",
        "nodes": [
            {"id": key, "parentId": parent, "order": order, "text": key,
             "positionX": x, "positionY": y}
            for key, parent, order, x, y in seed
        ],
    }).json()
    decision_id = record["id"]
    full = FastAPI()
    full.mount("/conclusion", app)

    with _serve(full) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.clock.install()
        page.set_default_timeout(10000)
        page.goto(f"{url}/conclusion/decision-trees/{decision_id}")

        def card(label):
            return page.locator(".decision-node-card", has=page.get_by_role(
                "button", name=label, exact=True,
            ))

        def bounds(label):
            box = card(label).bounding_box()
            assert box
            return box["y"], box["y"] + box["height"]

        def center(label):
            top, bottom = bounds(label)
            return (top + bottom) / 2

        def root_connector(child_id):
            return page.locator(f'[aria-label="Edge from root to {child_id}"] .vue-flow__edge-path')

        expect(card("a2")).to_be_visible()
        expect(root_connector("b")).to_have_attribute("d", re.compile(r"^M .* H .* V .* H .*"))
        assert bounds("a2")[1] < bounds("b1")[0]
        assert center("root") == pytest.approx((center("a") + center("b")) / 2, abs=1)
        assert api.get(f"/api/decisions/{decision_id}").json()["version"] == 1

        junctions = [
            re.search(r" H ([^ ]+) V ", root_connector(child).get_attribute("d")).group(1)
            for child in ("a", "b")
        ]
        assert junctions[0] == junctions[1]

        children = ["A 的第三个子节点", "A 的第四个子节点 " + "可以换行的长文字" * 7]
        field = page.get_by_role("textbox", name="节点文字")
        for label in children:
            page.get_by_role("button", name="a", exact=True).click()
            page.keyboard.press("Tab")
            expect(field).to_be_focused()
            field.fill(label)
            field.press("Enter")
        _expect_saved(page)

        for _ in range(2):
            for label in children:
                expect(card(label)).to_be_visible()
                assert bounds(label)[1] < bounds("b1")[0]
            assert center("a") == pytest.approx((center("a1") + center(children[-1])) / 2, abs=1)
            assert center("root") == pytest.approx((center("a") + center("b")) / 2, abs=1)
            record = api.get(f"/api/decisions/{decision_id}").json()
            assert all(node["parentId"] == "a" for node in record["nodes"] if node["text"] in children)
            page.reload()
        browser.close()


@pytest.mark.e2e
def test_autosave_batches_edits_and_limits_continuous_wait(decision_workflow):
    app, api, _ = decision_workflow
    index = FRONTEND_DIST / "index.html"
    if not index.exists() or "/conclusion/assets/" not in index.read_text():
        pytest.skip("Build Conclusion with VITE_API_BASE=/conclusion npm run build -- --base=/conclusion/")
    record = api.post("/api/decisions", json={
        "title": "Autosave cadence",
        "nodes": [{"id": "root", "text": "Start", "positionX": 0, "positionY": 0}],
    }).json()
    decision_id = record["id"]
    full = FastAPI()
    full.mount("/conclusion", app)

    def latest():
        return api.get(f"/api/decisions/{decision_id}").json()

    with _serve(full) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.clock.install()
        page.goto(f"{url}/conclusion/decision-trees/{decision_id}")
        status = page.get_by_role("status")
        text = page.get_by_role("textbox", name="节点文字")
        page.get_by_role("button", name="Start", exact=True).press("F2")
        text.fill("First draft")
        page.clock.fast_forward(4000)
        text.fill("Final draft")
        page.clock.fast_forward(6000)
        expect(status).to_contain_text("等待自动保存")
        assert latest()["version"] == 1
        page.clock.fast_forward(2000)
        expect(status).to_have_text("已保存 · v2")
        assert latest()["nodes"][0]["text"] == "Final draft"

        text.press("Enter")
        label = page.get_by_role("button", name="Final draft", exact=True)
        label.press("F2")
        text.fill("Discard this edit")
        text.press("Escape")
        page.clock.fast_forward(8000)
        expect(status).to_have_text("已保存 · v2")

        label.press("F2")
        text.fill("Continuing edit 0")
        for index in range(1, 5):
            page.clock.fast_forward(6000)
            text.fill(f"Continuing edit {index}")
        page.clock.fast_forward(3000)
        assert latest()["version"] == 2
        page.clock.fast_forward(3000)
        expect(status).to_have_text("已保存 · v3")
        assert latest()["nodes"][0]["text"] == "Continuing edit 4"

        page.clock.fast_forward(60000)
        assert latest()["version"] == 3
        browser.close()


@pytest.mark.e2e
def test_applying_local_checks_the_confirmed_remote_version(decision_workflow):
    app, api, _ = decision_workflow
    index = FRONTEND_DIST / "index.html"
    if not index.exists() or "/conclusion/assets/" not in index.read_text():
        pytest.skip("Build Conclusion with VITE_API_BASE=/conclusion npm run build -- --base=/conclusion/")
    record = api.post("/api/decisions", json={
        "title": "Conflict test",
        "nodes": [{"id": "root", "text": "Start", "positionX": 0, "positionY": 0}],
    }).json()
    decision_id = record["id"]
    path = f"/api/decisions/{decision_id}"
    full = FastAPI()
    full.mount("/conclusion", app)

    with _serve(full) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        local = browser.new_page(accept_downloads=True)
        remote = browser.new_page()
        for page in (local, remote):
            page.clock.install()
            page.goto(f"{url}/conclusion/decision-trees/{decision_id}")
            expect(page.get_by_role("button", name="Start", exact=True)).to_be_visible()

        def edit_root(page, old, new):
            page.get_by_role("button", name=old, exact=True).press("F2")
            editor = page.get_by_role("textbox", name="节点文字")
            editor.fill(new)
            editor.press("Enter")
            page.clock.fast_forward(8000)

        edit_root(remote, "Start", "Remote edit")
        expect(remote.get_by_role("status")).to_have_text("已保存 · v2")
        edit_root(local, "Start", "Local edit")
        expect(local.get_by_text("远端 v2", exact=False)).to_be_visible()
        expect(local.get_by_role("button", name="Local edit")).to_be_visible()

        apply_local = local.locator(".conflict-actions").get_by_role("button", name="应用本地")
        apply_local.click()
        dialog = local.get_by_role("dialog", name="应用本地版本")
        expect(dialog).to_contain_text("覆盖远端 v2")
        edit_root(remote, "Remote edit", "Newer remote edit")
        expect(remote.get_by_role("status")).to_have_text("已保存 · v3")
        with local.expect_download() as first_backup:
            dialog.get_by_role("button", name="应用本地").click()
        assert first_backup.value.suggested_filename == f"decision-{decision_id}-remote-v2.json"
        expect(local.get_by_text("远端 v3", exact=False)).to_be_visible()
        expect(dialog).to_be_hidden()
        assert api.get(path).json()["nodes"][0]["text"] == "Newer remote edit"

        apply_local.click()
        expect(dialog).to_contain_text("覆盖远端 v3")
        with local.expect_download() as latest_backup:
            dialog.get_by_role("button", name="应用本地").click()
        backup = json.loads(Path(latest_backup.value.path()).read_text(encoding="utf-8"))
        assert backup["version"] == 3 and backup["nodes"][0]["text"] == "Newer remote edit"
        expect(local.get_by_role("status")).to_have_text("已保存 · v4")
        assert api.get(path).json()["nodes"][0]["text"] == "Local edit"
        browser.close()
